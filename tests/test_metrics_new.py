"""Tests for the new signal2noise.metrics.* subpackage (spec-compliant API)."""

from __future__ import annotations

import numpy as np
import pytest

from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import RunSummary, TaskStatus, TickSnapshot
from signal2noise.metrics.collectors import TickCollector
from signal2noise.metrics.efficiency import compute_efficiency_ratio, compute_task_score
from signal2noise.metrics.phase import compute_phase_derivative, find_critical_tau, summarise_sweep
from signal2noise.metrics.summary import aggregate_summary

# ---------------------------------------------------------------------------
# TickCollector
# ---------------------------------------------------------------------------

def _snap(tick: int, sync_active: bool = False) -> TickSnapshot:
    return TickSnapshot(
        tick=tick,
        rework_rate=0.0,
        new_demand=1,
        rework_demand=0,
        total_demand=1,
        sync_active=sync_active,
        tasks_done=tick,
        tasks_total=10,
        agent_states={},
        agent_cognitive_loads={},
        sync_minutes_this_tick=float(2) if sync_active else 0.0,
        async_messages_this_tick=0,
    )

def test_collector_empty_initially():
    c = TickCollector()
    assert len(c) == 0
    assert c.snapshots == []

def test_collector_records_and_retrieves():
    c = TickCollector()
    for i in range(5):
        c.record(_snap(i))
    assert len(c) == 5
    assert c.snapshots[0].tick == 0
    assert c.snapshots[4].tick == 4

def test_collector_snapshots_property_returns_copy():
    c = TickCollector()
    c.record(_snap(0))
    snaps = c.snapshots
    snaps.clear()
    assert len(c) == 1  # internal state not affected

# ---------------------------------------------------------------------------
# compute_task_score
# ---------------------------------------------------------------------------

def _graph(n: int = 5, all_done: bool = False, rework: list[int] | None = None) -> TaskGraph:
    rng = np.random.default_rng(0)
    g = TaskGraph.linear(n_tasks=n, rng=rng)
    if all_done:
        for i, task in enumerate(g.tasks.values()):
            task.status = TaskStatus.DONE
            task.rework_count = rework[i] if rework else 0
    return g

def test_score_zero_nothing_done():
    assert compute_task_score(_graph(5)) == 0.0

def test_score_100_all_done_clean():
    score = compute_task_score(_graph(5, all_done=True, rework=[0] * 5))
    assert abs(score - 100.0) < 0.01

def test_score_lower_with_rework():
    clean = compute_task_score(_graph(5, all_done=True, rework=[0] * 5))
    dirty = compute_task_score(_graph(5, all_done=True, rework=[2, 1, 0, 3, 0]))
    assert clean > dirty

def test_score_in_range():
    score = compute_task_score(_graph(10, all_done=True))
    assert 0.0 <= score <= 100.0

# ---------------------------------------------------------------------------
# compute_efficiency_ratio
# ---------------------------------------------------------------------------

def test_eta_positive():
    _, eta = compute_efficiency_ratio(_graph(5, all_done=True), t_cost=10.0)
    assert eta > 0.0

def test_eta_decreases_with_cost():
    g = _graph(5, all_done=True)
    _, eta_cheap = compute_efficiency_ratio(g, t_cost=1.0)
    _, eta_expensive = compute_efficiency_ratio(g, t_cost=1000.0)
    assert eta_cheap > eta_expensive

def test_eta_no_div_by_zero():
    _, eta = compute_efficiency_ratio(_graph(5, all_done=True), t_cost=0.0)
    assert eta > 0.0 and np.isfinite(eta)

# ---------------------------------------------------------------------------
# Phase transition
# ---------------------------------------------------------------------------

def test_derivative_length():
    data = compute_phase_derivative([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, 2.0])
    assert len(data) == 4

def test_derivative_endpoints_are_zero():
    data = compute_phase_derivative([0.1, 0.2, 0.3], [1.0, 2.0, 3.0])
    assert data[0]["deta_dtau"] == 0.0
    assert data[-1]["deta_dtau"] == 0.0

def test_derivative_mismatch_raises():
    with pytest.raises(ValueError):
        compute_phase_derivative([0.1, 0.2], [1.0])

def test_critical_tau_at_peak():
    # tau=0.2 has the unambiguous maximum derivative (50 vs 10 elsewhere).
    # etas: 1, 1, 6, 6.5, 7 → deriv at 0.2 = (6-1)/(0.3-0.1) = 25
    #                           deriv at 0.3 = (6.5-1)/(0.4-0.2) = 27.5 → largest at 0.3
    data = compute_phase_derivative(
        [0.1, 0.2, 0.3, 0.4, 0.5],
        [1.0, 1.0, 6.0, 6.5, 7.0],
    )
    # At tau=0.3: (6.5 - 1.0) / (0.4 - 0.2) = 27.5  ← max
    # At tau=0.2: (6.0 - 1.0) / (0.3 - 0.1) = 25.0
    tau_star = find_critical_tau(data)
    assert tau_star == 0.3

def test_critical_tau_empty():
    assert find_critical_tau([]) == 0.0

# ---------------------------------------------------------------------------
# aggregate_summary
# ---------------------------------------------------------------------------

def _run(**kwargs) -> RunSummary:
    defaults = dict(
        ticket_bounce_rate=0.1,
        efficiency_ratio=5.0,
        task_score=80.0,
        total_coordination_cost=10.0,
        time_to_completion=50,
        throughput=0.3,
        cognitive_load_variance=0.02,
        mean_rework_cascade_depth=1.0,
        channel_utilization_ratio=0.2,
        demand_supply_ratio_mean=2.0,
    )
    defaults.update(kwargs)
    return RunSummary(**defaults)

def test_aggregate_empty():
    assert aggregate_summary([]) == {}

def test_aggregate_n_runs():
    runs = [_run() for _ in range(7)]
    assert aggregate_summary(runs)["n_runs"] == 7

def test_aggregate_mean():
    runs = [_run(ticket_bounce_rate=v) for v in [0.1, 0.2, 0.3]]
    result = aggregate_summary(runs)
    assert abs(result["ticket_bounce_rate_mean"] - 0.2) < 1e-9

def test_aggregate_std_identical():
    runs = [_run(efficiency_ratio=5.0)] * 4
    result = aggregate_summary(runs)
    assert abs(result["efficiency_ratio_std"]) < 1e-9
