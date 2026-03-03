"""Metrics: snapshot collection, efficiency computation, phase detection."""

from signal2noise.metrics.collectors import TickCollector
from signal2noise.metrics.efficiency import (
    compute_efficiency_ratio,
    compute_rework_adjusted_efficiency,
    compute_rework_cost,
    compute_task_score,
)
from signal2noise.metrics.phase import compute_phase_derivative, find_critical_tau, summarise_sweep
from signal2noise.metrics.summary import aggregate_summary

__all__ = [
    "TickCollector",
    "aggregate_summary",
    "compute_efficiency_ratio",
    "compute_phase_derivative",
    "compute_rework_adjusted_efficiency",
    "compute_rework_cost",
    "compute_task_score",
    "find_critical_tau",
    "summarise_sweep",
]
