"""Integration tests for signal2noise.core.simulation (Simulation + SimulationConfig)."""

from __future__ import annotations

import pytest

from signal2noise.core.simulation import Simulation, SimulationConfig
from signal2noise.core.types import RunSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**kwargs) -> SimulationConfig:
    defaults = dict(
        num_tasks=8,
        num_agents=2,
        graph_topology="linear",
        max_ticks=100,
        random_seed=42,
    )
    defaults.update(kwargs)
    return SimulationConfig(**defaults)

# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------

def test_simulation_returns_run_summary():
    result = Simulation(_cfg()).run()
    assert isinstance(result, RunSummary)

def test_simulation_completion_tick_positive():
    result = Simulation(_cfg()).run()
    assert result.time_to_completion > 0

def test_simulation_tick_snapshots_populated():
    result = Simulation(_cfg()).run()
    assert len(result.tick_snapshots) > 0

def test_simulation_efficiency_ratio_positive():
    result = Simulation(_cfg()).run()
    assert result.efficiency_ratio >= 0.0

def test_simulation_ticket_bounce_rate_nonneg():
    result = Simulation(_cfg()).run()
    assert result.ticket_bounce_rate >= 0.0

def test_simulation_throughput_positive():
    result = Simulation(_cfg()).run()
    assert result.throughput > 0.0

def test_simulation_channel_util_in_range():
    result = Simulation(_cfg()).run()
    assert 0.0 <= result.channel_utilization_ratio <= 1.0

# ---------------------------------------------------------------------------
# Protocol-specific tests
# ---------------------------------------------------------------------------

def test_async_only_no_sync_activity():
    cfg = _cfg(protocol="async_only", num_tasks=6, max_ticks=80)
    result = Simulation(cfg).run()
    # Async only → no sync ticks
    assert result.channel_utilization_ratio == 0.0

def test_sync_always_has_sync_activity():
    cfg = _cfg(protocol="sync_always", s_min=0.3, num_tasks=6, max_ticks=80)
    result = Simulation(cfg).run()
    # Sync always → every tick is sync
    assert result.channel_utilization_ratio == 1.0

def test_adaptive_sync_between_async_and_sync_always():
    """Adaptive should spend less sync time than sync_always and more than async_only."""
    base = dict(num_tasks=10, max_ticks=150)
    async_result = Simulation(_cfg(protocol="async_only", **base)).run()
    sync_result = Simulation(_cfg(protocol="sync_always", s_min=0.25, **base)).run()
    adaptive_result = Simulation(_cfg(protocol="adaptive", tau=0.2, **base)).run()
    assert async_result.channel_utilization_ratio <= adaptive_result.channel_utilization_ratio
    assert adaptive_result.channel_utilization_ratio <= sync_result.channel_utilization_ratio

# ---------------------------------------------------------------------------
# Topology tests
# ---------------------------------------------------------------------------

def test_linear_topology_runs():
    cfg = _cfg(graph_topology="linear", num_tasks=8)
    result = Simulation(cfg).run()
    assert result.time_to_completion > 0

def test_tree_topology_runs():
    cfg = _cfg(graph_topology="tree", num_tasks=7)
    result = Simulation(cfg).run()
    assert result.time_to_completion > 0

def test_diamond_topology_runs():
    cfg = _cfg(graph_topology="diamond", num_tasks=6)
    result = Simulation(cfg).run()
    assert result.time_to_completion > 0

# ---------------------------------------------------------------------------
# Reproducibility test
# ---------------------------------------------------------------------------

def test_same_seed_same_result():
    cfg_a = _cfg(random_seed=7)
    cfg_b = _cfg(random_seed=7)
    r_a = Simulation(cfg_a).run()
    r_b = Simulation(cfg_b).run()
    assert r_a.time_to_completion == r_b.time_to_completion
    assert abs(r_a.efficiency_ratio - r_b.efficiency_ratio) < 1e-9

def test_different_seeds_may_differ():
    r1 = Simulation(_cfg(random_seed=1)).run()
    r2 = Simulation(_cfg(random_seed=9999)).run()
    # They might coincidentally agree, but usually differ
    # Just check they both run successfully
    assert isinstance(r1, RunSummary)
    assert isinstance(r2, RunSummary)

# ---------------------------------------------------------------------------
# Error model tests
# ---------------------------------------------------------------------------

def test_zero_base_error_leads_to_low_rework():
    # Disable both error sources: base_error_rate and exogenous perturbation
    cfg = _cfg(base_error_rate=0.0, p_signal_change=0.0, num_tasks=10, max_ticks=200)
    result = Simulation(cfg).run()
    assert result.ticket_bounce_rate == 0.0

def test_high_base_error_leads_to_higher_rework():
    low = Simulation(_cfg(base_error_rate=0.0, p_signal_change=0.0, num_tasks=8, max_ticks=200, random_seed=5)).run()
    high = Simulation(_cfg(base_error_rate=0.5, num_tasks=8, max_ticks=200, random_seed=5)).run()
    assert high.ticket_bounce_rate >= low.ticket_bounce_rate

# ---------------------------------------------------------------------------
# Invalid config
# ---------------------------------------------------------------------------

def test_invalid_protocol_raises():
    with pytest.raises(ValueError, match="Unknown protocol"):
        cfg = _cfg(protocol="unknown_protocol")
        Simulation(cfg).run()

def test_invalid_topology_raises():
    with pytest.raises(ValueError, match="Unknown graph_topology"):
        cfg = SimulationConfig(graph_topology="hexagon", num_tasks=5, random_seed=42)
        Simulation(cfg).run()
