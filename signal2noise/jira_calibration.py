from __future__ import annotations

import csv
import json
import math
import re
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from signal2noise.calibration import calibrate_from_csv

INSERT_RE = re.compile(r"^INSERT INTO ([a-zA-Z0-9_]+) \((.*?)\) VALUES \((.*)\);$", re.DOTALL)
DONE_STATUSES = {"resolved", "closed", "done"}
POST_DONE_CHANGE_FIELDS = {"status", "resolution", "summary", "description"}


@dataclass
class IssueMeta:
    project: str
    created: datetime | None
    resolved: datetime | None
    updated: datetime | None


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        # Keep parser resilient to odd legacy timestamp strings.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue
    return None


def _split_values(values_text: str) -> list[str]:
    values: list[str] = []
    token: list[str] = []
    in_quote = False
    i = 0
    n = len(values_text)
    while i < n:
        ch = values_text[i]
        if ch == "'":
            token.append(ch)
            if in_quote:
                if i + 1 < n and values_text[i + 1] == "'":
                    token.append("'")
                    i += 2
                    continue
                in_quote = False
            else:
                in_quote = True
            i += 1
            continue
        if ch == "," and not in_quote:
            values.append("".join(token).strip())
            token = []
            i += 1
            continue
        token.append(ch)
        i += 1
    values.append("".join(token).strip())
    return values


def _decode_sql_literal(token: str) -> str | None:
    t = token.strip()
    if t.upper() == "NULL":
        return None
    if len(t) >= 2 and t[0] == "'" and t[-1] == "'":
        return t[1:-1].replace("''", "'")
    return t


def _iter_target_statements(sql_path: Path, targets: set[str]) -> Iterable[tuple[str, list[str], list[str | None]]]:
    prefixes = tuple(f"INSERT INTO {t} " for t in targets)
    with sql_path.open("r", encoding="utf-8", errors="replace") as f:
        collecting = False
        buf: list[str] = []
        in_quote = False
        for line in f:
            if not collecting:
                if line.startswith(prefixes):
                    collecting = True
                    buf = []
                    in_quote = False
                else:
                    continue

            # Continue collecting until we reach a semicolon outside SQL quotes.
            current: list[str] = []
            i = 0
            n = len(line)
            stmt_done = False
            while i < n:
                ch = line[i]
                current.append(ch)
                if ch == "'":
                    if in_quote and i + 1 < n and line[i + 1] == "'":
                        current.append("'")
                        i += 2
                        continue
                    in_quote = not in_quote
                elif ch == ";" and not in_quote:
                    stmt_done = True
                    i += 1
                    break
                i += 1
            buf.append("".join(current))
            if not stmt_done:
                continue

            stmt = "".join(buf).strip()
            collecting = False
            m = INSERT_RE.match(stmt)
            if not m:
                continue
            table = m.group(1)
            if table not in targets:
                continue
            cols = [c.strip() for c in m.group(2).split(",")]
            raw_values = _split_values(m.group(3))
            values = [_decode_sql_literal(v) for v in raw_values]
            if len(cols) != len(values):
                continue
            yield table, cols, values


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["root_issue_id", "root_event_time", "fix_time", "rework", "cascade_size", "post_done_change"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = int(math.ceil(q * len(xs))) - 1
    idx = max(0, min(idx, len(xs) - 1))
    return float(xs[idx])


def derive_from_jira_sql(
    sql_path: str | Path,
    out_csv: str | Path,
    out_stats_json: str | Path,
    out_summary_md: str | Path,
    window_days: int = 3,
) -> dict[str, Any]:
    sql = Path(sql_path)
    out_csv_path = Path(out_csv)
    out_stats_path = Path(out_stats_json)
    out_summary_path = Path(out_summary_md)

    issue_meta: dict[int, IssueMeta] = {}
    latest_seen: datetime | None = None

    # Pass 1: issue report metadata (created/resolved/project).
    for table, cols, values in _iter_target_statements(sql, {"jira_issue_report"}):
        row = dict(zip(cols, values))
        try:
            issue_id = int(str(row.get("id") or "").strip())
        except ValueError:
            continue
        created = _parse_dt(row.get("created"))
        resolved = _parse_dt(row.get("resolved"))
        updated = _parse_dt(row.get("updated"))
        project = (row.get("project_name") or row.get("project") or "UNKNOWN").strip()
        issue_meta[issue_id] = IssueMeta(project=project, created=created, resolved=resolved, updated=updated)
        for dt in (created, resolved, updated):
            if dt is not None and (latest_seen is None or dt > latest_seen):
                latest_seen = dt

    # Pass 2: changelog-derived post-resolution changes and reopen proxies.
    first_post_done: dict[int, datetime] = {}
    first_reopen: dict[int, datetime] = {}
    last_change: dict[int, datetime] = {}

    for table, cols, values in _iter_target_statements(sql, {"jira_issue_changelog_item"}):
        row = dict(zip(cols, values))
        dt = _parse_dt(row.get("date"))
        if dt is None:
            continue
        if latest_seen is None or dt > latest_seen:
            latest_seen = dt

        try:
            issue_id = int(str(row.get("issue_report_id") or "").strip())
        except ValueError:
            continue
        meta = issue_meta.get(issue_id)
        if meta is None:
            continue
        prev_last = last_change.get(issue_id)
        if prev_last is None or dt > prev_last:
            last_change[issue_id] = dt

        if meta.resolved is None or dt <= meta.resolved:
            continue

        field_name = (row.get("field_name") or "").strip().lower()
        new_value = (row.get("new_value") or "").strip().lower()
        if field_name in POST_DONE_CHANGE_FIELDS:
            prev_post = first_post_done.get(issue_id)
            if prev_post is None or dt < prev_post:
                first_post_done[issue_id] = dt
        if field_name == "status" and new_value and new_value not in DONE_STATUSES:
            prev_reopen = first_reopen.get(issue_id)
            if prev_reopen is None or dt < prev_reopen:
                first_reopen[issue_id] = dt

    reopen_by_project: dict[str, list[float]] = {}
    for issue_id, dt in first_reopen.items():
        project = issue_meta.get(issue_id).project if issue_id in issue_meta else "UNKNOWN"
        reopen_by_project.setdefault(project, []).append(dt.timestamp())
    for vals in reopen_by_project.values():
        vals.sort()

    rows: list[dict[str, Any]] = []
    fix_times: list[float] = []
    cascade_sizes: list[float] = []
    rework_flags: list[int] = []
    post_done_flags: list[int] = []

    delta = timedelta(days=window_days).total_seconds()
    resolved_count = 0
    active_done_days = 0.0
    post_done_count = 0

    for issue_id, meta in issue_meta.items():
        if meta.resolved is None:
            continue
        resolved_count += 1

        fix_time = None
        if meta.created is not None:
            diff = (meta.resolved - meta.created).total_seconds() / 86400.0
            if diff >= 0:
                fix_time = diff
                fix_times.append(diff)

        post_done_change = 1 if issue_id in first_post_done else 0
        rework = 1 if issue_id in first_reopen else 0
        post_done_flags.append(post_done_change)
        rework_flags.append(rework)
        if post_done_change:
            post_done_count += 1

        root_dt = first_post_done.get(issue_id)
        if root_dt is None:
            root_dt = meta.resolved
        root_ts = root_dt.timestamp()

        cascade_size = 0
        if issue_id in first_post_done:
            events = reopen_by_project.get(meta.project, [])
            left = bisect_right(events, root_ts)
            right = bisect_right(events, root_ts + delta)
            cascade_size = max(0, right - left)
            own_reopen = first_reopen.get(issue_id)
            if own_reopen is not None:
                own_ts = own_reopen.timestamp()
                if root_ts < own_ts <= root_ts + delta and cascade_size > 0:
                    cascade_size -= 1

        cascade_sizes.append(float(cascade_size))
        rows.append(
            {
                "root_issue_id": issue_id,
                "root_event_time": root_dt.isoformat(sep=" "),
                "fix_time": "" if fix_time is None else f"{fix_time:.6f}",
                "rework": rework,
                "cascade_size": cascade_size,
                "post_done_change": post_done_change,
            }
        )

        end_dt = last_change.get(issue_id)
        if end_dt is None:
            end_dt = meta.updated or meta.resolved
        if end_dt < meta.resolved:
            end_dt = meta.resolved
        active_done_days += max(1.0, (end_dt - meta.resolved).total_seconds() / 86400.0)

    _write_csv(out_csv_path, rows)
    calibrated = calibrate_from_csv(out_csv_path)

    rework_rate = statistics.fmean(rework_flags) if rework_flags else 0.0
    post_done_rate = statistics.fmean(post_done_flags) if post_done_flags else 0.0
    mean_cascade = statistics.fmean(cascade_sizes) if cascade_sizes else 0.0
    p_change_per_day = post_done_count / active_done_days if active_done_days > 0 else 0.0

    calibrated_propagation = dict(calibrated.get("propagation", {}))
    calibrated_propagation["p_change"] = max(0.0, min(1.0, p_change_per_day))
    calibrated["propagation"] = calibrated_propagation

    stats = {
        "source_sql": str(sql),
        "window_days": window_days,
        "n_issues_total": len(issue_meta),
        "n_issues_resolved": resolved_count,
        "n_rows_written": len(rows),
        "mean_fix_time_days": statistics.fmean(fix_times) if fix_times else 0.0,
        "rework_rate": rework_rate,
        "post_done_change_rate": post_done_rate,
        "p_change_per_day": p_change_per_day,
        "cascade_mean": mean_cascade,
        "cascade_p90": _quantile(cascade_sizes, 0.90),
        "cascade_p95": _quantile(cascade_sizes, 0.95),
        "latest_seen_timestamp": latest_seen.isoformat(sep=" ") if latest_seen else None,
        "calibrated_params": calibrated,
    }

    out_stats_path.parent.mkdir(parents=True, exist_ok=True)
    out_stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True), encoding="utf-8")

    summary_lines = [
        "# Jira Calibration Summary",
        "",
        f"- Source SQL: `{sql}`",
        f"- Resolved issues analyzed: {resolved_count}",
        f"- Mean fix time (days): {stats['mean_fix_time_days']:.3f}",
        f"- Rework rate (reopened after done): {rework_rate:.4f}",
        f"- Post-done change rate: {post_done_rate:.4f}",
        f"- p_change/day (proxy): {p_change_per_day:.6f}",
        f"- Cascade size proxy mean: {mean_cascade:.3f}",
        f"- Cascade size proxy p90/p95: {stats['cascade_p90']:.3f} / {stats['cascade_p95']:.3f}",
        "",
        "Proxy definition used:",
        f"- Root event: first post-resolution change where field is one of {sorted(POST_DONE_CHANGE_FIELDS)}.",
        f"- Cascade size: count of other issues in same project with a reopen event within {window_days} days of root event.",
    ]
    out_summary_path.parent.mkdir(parents=True, exist_ok=True)
    out_summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return stats
