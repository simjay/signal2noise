from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


def _load_rows(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    with p.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _to_float(values: list[str]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def _fit_lognormal(samples: list[float]) -> dict[str, float]:
    positive = [max(1e-9, x) for x in samples if x > 0]
    if not positive:
        return {"kind": "fixed", "value": 1.0}
    logs = [math.log(x) for x in positive]
    mean = statistics.fmean(logs)
    sigma = statistics.pstdev(logs) if len(logs) > 1 else 0.1
    return {"kind": "lognormal", "mean": mean, "sigma": sigma}


def calibrate_from_csv(path: str | Path) -> dict[str, Any]:
    rows = _load_rows(path)

    fix_times = _to_float([r.get("fix_time", "") for r in rows])
    reopen_flags = _to_float([r.get("rework", "") for r in rows])
    cascade_sizes = _to_float([r.get("cascade_size", "") for r in rows])
    post_done_change = _to_float([r.get("post_done_change", "") for r in rows])

    rework_rate = statistics.fmean(reopen_flags) if reopen_flags else 0.08
    mean_cascade = statistics.fmean(cascade_sizes) if cascade_sizes else 1.0
    p_change = statistics.fmean(post_done_change) if post_done_change else min(0.5, rework_rate * 0.5)

    base_propagation = min(0.95, max(0.05, mean_cascade / (mean_cascade + 2.0)))

    calibrated = {
        "task_effort_distribution": _fit_lognormal(fix_times) if fix_times else {"kind": "lognormal", "mean": 2.0, "sigma": 0.3},
        "agent_distributions": {
            "defect_rate": {"kind": "fixed", "value": max(0.001, min(0.9, rework_rate))}
        },
        "propagation": {"base_propagation": base_propagation, "p_change": max(0.0, min(1.0, p_change))},
        "calibration_summary": {
            "n_rows": len(rows),
            "mean_fix_time": statistics.fmean(fix_times) if fix_times else None,
            "mean_rework_rate": rework_rate,
            "mean_post_done_change": p_change,
            "mean_cascade_size": mean_cascade,
        },
    }
    return calibrated


def write_calibrated(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
