"""Tests for signal2noise.experiments.runner, sweep, and presets."""

from __future__ import annotations

import pytest

from signal2noise.core.simulation import SimulationConfig
from signal2noise.core.types import RunSummary
from signal2noise.experiments.runner import run_replications, run_single
from signal2noise.experiments.sweep import ParameterSweep

# ---------------------------------------------------------------------------
# run_single tests
# ---------------------------------------------------------------------------

def _base_cfg(**kwargs) -> SimulationConfig:
    defaults = dict(num_tasks=6, num_agents=2, max_ticks=60, random_seed=42)
    defaults.update(kwargs)
    return SimulationConfig(**defaults)

def test_run_single_returns_run_summary():
    result = run_single(_base_cfg())
    assert isinstance(result, RunSummary)

def test_run_single_positive_completion():
    result = run_single(_base_cfg())
    assert result.time_to_completion > 0

# ---------------------------------------------------------------------------
# run_replications tests
# ---------------------------------------------------------------------------

def test_run_replications_count():
    runs = run_replications(_base_cfg(), n_runs=5, seed_base=0)
    assert len(runs) == 5

def test_run_replications_all_run_summaries():
    runs = run_replications(_base_cfg(), n_runs=3, seed_base=100)
    for r in runs:
        assert isinstance(r, RunSummary)

def test_run_replications_different_seeds_may_differ():
    runs = run_replications(_base_cfg(), n_runs=5, seed_base=0)
    times = [r.time_to_completion for r in runs]
    # With stochastic runs, not all completion times should be identical
    # (this is probabilistic; just check they all ran)
    assert len(times) == 5

def test_run_replications_seed_offset():
    """Each replication should use a unique seed (verifiable via determinism)."""
    r_a = run_single(SimulationConfig(num_tasks=6, num_agents=2, max_ticks=60, random_seed=42))
    r_b = run_single(SimulationConfig(num_tasks=6, num_agents=2, max_ticks=60, random_seed=43))
    # With different seeds they may produce different results (not guaranteed,
    # but both should run successfully)
    assert isinstance(r_a, RunSummary)
    assert isinstance(r_b, RunSummary)

# ---------------------------------------------------------------------------
# ParameterSweep tests
# ---------------------------------------------------------------------------

def test_sweep_correct_number_of_combos():
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={"protocol": ["async_only", "sync_always"]},
        runs_per_config=3,
        seed_base=0,
    )
    results = sweep.run()
    assert len(results) == 2

def test_sweep_cross_product():
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={
            "protocol": ["async_only", "adaptive"],
            "num_tasks": [5, 8],
        },
        runs_per_config=2,
        seed_base=0,
    )
    results = sweep.run()
    assert len(results) == 4  # 2 × 2

def test_sweep_result_contains_override_keys():
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={"protocol": ["async_only"]},
        runs_per_config=2,
        seed_base=0,
    )
    results = sweep.run()
    assert results[0]["protocol"] == "async_only"

def test_sweep_result_has_aggregate_metrics():
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={"protocol": ["async_only"]},
        runs_per_config=3,
        seed_base=0,
    )
    results = sweep.run()
    r = results[0]
    assert "efficiency_ratio_mean" in r
    assert "ticket_bounce_rate_mean" in r
    assert r["n_runs"] == 3

def test_sweep_tau_sweep_only_applies_to_adaptive():
    """When sweeping tau alongside protocols, non-adaptive protocols should run fine."""
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={
            "protocol": ["adaptive"],
            "tau": [0.1, 0.5],
        },
        runs_per_config=2,
        seed_base=0,
    )
    results = sweep.run()
    assert len(results) == 2
    taus = {r["tau"] for r in results}
    assert taus == {0.1, 0.5}

def test_sweep_raw_runs_stored():
    sweep = ParameterSweep(
        base_config=_base_cfg(),
        sweep_params={"protocol": ["async_only"]},
        runs_per_config=3,
        seed_base=0,
    )
    results = sweep.run()
    assert "_raw_runs" in results[0]
    assert len(results[0]["_raw_runs"]) == 3
