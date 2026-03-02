from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

import statistics


def mean_ci(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = float(statistics.fmean(values))
    if len(values) <= 1:
        return mean, 0.0
    std = float(statistics.stdev(values))
    ci = 1.96 * std / math.sqrt(len(values))
    return mean, ci


def _rate(values: list[float], threshold: float) -> float:
    if not values:
        return 0.0
    return float(sum(1 for v in values if v >= threshold) / len(values))


def _tail_mean(values: list[float], top_fraction: float = 0.10) -> float:
    if not values:
        return 0.0
    k = max(1, int(math.ceil(len(values) * top_fraction)))
    desc = sorted(values, reverse=True)
    return float(statistics.fmean(desc[:k]))


def aggregate_by_policy(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        grouped[str(row["policy"])].append(row)

    metric_keys = [
        "total_rework_events",
        "avg_cascade_size",
        "max_cascade_size",
        "makespan",
        "tasks_completed",
        "coordination_cost",
        "sync_minutes",
        "messages_sent",
        "test_pass_rate",
        "quality_score",
        "efficiency",
    ]

    out: list[dict[str, Any]] = []
    for policy, rows in grouped.items():
        agg: dict[str, Any] = {"policy": policy, "n_runs": len(rows)}
        for mk in metric_keys:
            vals = [float(r.get(mk, 0.0)) for r in rows]
            m, ci = mean_ci(vals)
            agg[f"{mk}_mean"] = m
            agg[f"{mk}_ci95"] = ci

        rework_vals = [float(r.get("total_rework_events", 0.0)) for r in rows]
        max_cascade_vals = [float(r.get("max_cascade_size", 0.0)) for r in rows]
        quality_vals = [float(r.get("quality_score", 0.0)) for r in rows]

        agg["bad_run_rate_rework_ge_8"] = _rate(rework_vals, 8.0)
        agg["bad_run_rate_cascade_ge_1"] = _rate(max_cascade_vals, 1.0)
        agg["bad_run_rate_cascade_ge_2"] = _rate(max_cascade_vals, 2.0)
        agg["bad_run_rate_quality_lt_0_9"] = float(
            sum(1 for v in quality_vals if v < 0.9) / len(quality_vals) if quality_vals else 0.0
        )
        agg["tail10_total_rework_events_mean"] = _tail_mean(rework_vals, top_fraction=0.10)
        agg["tail10_max_cascade_size_mean"] = _tail_mean(max_cascade_vals, top_fraction=0.10)
        out.append(agg)
    return out


def build_phase_diagram(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, str], list[dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        key = (float(row.get("coupling_strength", 0.0)), str(row["policy"]))
        grouped[key].append(row)

    out: list[dict[str, Any]] = []
    for (coupling, policy), rows in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        rework_vals = [float(r.get("total_rework_events", 0.0)) for r in rows]
        max_cascade_vals = [float(r.get("max_cascade_size", 0.0)) for r in rows]
        out.append(
            {
                "coupling": coupling,
                "policy": policy,
                "avg_cascade_size": float(statistics.fmean([r.get("avg_cascade_size", 0.0) for r in rows])),
                "avg_rework": float(statistics.fmean([r.get("total_rework_events", 0.0) for r in rows])),
                "efficiency": float(statistics.fmean([r.get("efficiency", 0.0) for r in rows])),
                "bad_run_rate_rework_ge_8": _rate(rework_vals, 8.0),
                "bad_run_rate_cascade_ge_1": _rate(max_cascade_vals, 1.0),
                "tail10_total_rework_events_mean": _tail_mean(rework_vals, top_fraction=0.10),
                "tail10_max_cascade_size_mean": _tail_mean(max_cascade_vals, top_fraction=0.10),
            }
        )
    return out


def cascade_histogram(cascade_rows: list[dict[str, Any]], bins: list[int] | None = None) -> list[dict[str, Any]]:
    if bins is None:
        bins = [0, 1, 2, 3, 5, 8, 13, 21, 34, 55]

    def to_bin(size: int) -> str:
        for i in range(len(bins) - 1):
            if bins[i] <= size < bins[i + 1]:
                return f"[{bins[i]},{bins[i+1]})"
        return f"[{bins[-1]},inf)"

    ctr: Counter[tuple[str, str]] = Counter()
    for row in cascade_rows:
        policy = str(row.get("policy", "unknown"))
        size = int(row.get("size", 0))
        ctr[(policy, to_bin(size))] += 1

    out = [
        {"policy": pol, "bin": b, "count": c}
        for (pol, b), c in sorted(ctr.items(), key=lambda x: (x[0][0], x[0][1]))
    ]
    return out
