"""RunSummary aggregation helpers."""

from __future__ import annotations

import math

import numpy as np

from signal2noise.core.types import RunSummary


def aggregate_summary(runs: list[RunSummary]) -> dict:
    """Compute aggregate statistics across multiple RunSummary objects.

    Parameters
    ----------
    runs:
        List of run results (e.g. from repeated simulations of the same
        configuration).

    Returns
    -------
    dict
        Keys include ``{metric}_mean``, ``{metric}_std``, ``{metric}_ci95``
        for each primary and secondary metric.
    """
    if not runs:
        return {}

    def _stats(values: list[float]) -> dict:
        arr = np.array(values, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        n = len(arr)
        ci95 = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
        return {"mean": mean, "std": std, "ci95": ci95}

    metrics = {
        "ticket_bounce_rate": [r.ticket_bounce_rate for r in runs],
        "efficiency_ratio": [r.efficiency_ratio for r in runs],
        "rework_adjusted_eta": [r.rework_adjusted_eta for r in runs],
        "total_rework_cost": [r.total_rework_cost for r in runs],
        "task_score": [r.task_score for r in runs],
        "total_coordination_cost": [r.total_coordination_cost for r in runs],
        "time_to_completion": [float(r.time_to_completion) for r in runs],
        "throughput": [r.throughput for r in runs],
        "cognitive_load_variance": [r.cognitive_load_variance for r in runs],
        "mean_rework_cascade_depth": [r.mean_rework_cascade_depth for r in runs],
        "channel_utilization_ratio": [r.channel_utilization_ratio for r in runs],
        "demand_supply_ratio_mean": [r.demand_supply_ratio_mean for r in runs],
    }

    result: dict = {"n_runs": len(runs)}
    for metric_name, values in metrics.items():
        stats = _stats(values)
        result[f"{metric_name}_mean"] = stats["mean"]
        result[f"{metric_name}_std"] = stats["std"]
        result[f"{metric_name}_ci95"] = stats["ci95"]
    return result
