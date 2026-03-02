from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: set[str] = set()
        for r in rows:
            keys.update(r.keys())
        fieldnames = sorted(keys)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_events(path: str | Path, events: list[dict[str, Any]]) -> None:
    _write_csv(Path(path), events, fieldnames=["run_id", "t", "event_type", "task_id", "agent_id", "mode", "meta_json"])


def write_runs_summary(path: str | Path, rows: list[dict[str, Any]]) -> None:
    _write_csv(Path(path), rows)


def write_cascades(path: str | Path, rows: list[dict[str, Any]]) -> None:
    _write_csv(Path(path), rows, fieldnames=["run_id", "t", "root_task_id", "mode", "size", "policy", "coupling_strength"])


def write_timeseries(path: str | Path, rows: list[dict[str, Any]]) -> None:
    _write_csv(
        Path(path),
        rows,
        fieldnames=[
            "run_id",
            "policy",
            "t",
            "mode",
            "rework_events",
            "signal_events",
            "noise_events",
            "demand",
            "supply",
            "gap",
            "high_need",
            "escalated",
            "false_alarm",
            "missed_escalation",
            "tasks_done",
        ],
    )
