from __future__ import annotations

import copy
import statistics

from signal2noise.config import dict_to_config
from signal2noise.engine import run_many


def base_cfg() -> dict:
    return {
        "seed": 7,
        "n_runs": 80,
        "ticks_per_run": 200,
        "team_size": 4,
        "integration_check_interval": 1,
        "rework_effort_fraction": 0.35,
        "retest_effort_fraction": 0.2,
        "task_graph": {"type": "chain", "n_tasks": 10},
        "task_effort_distribution": {"kind": "fixed", "value": 6.0},
        "agent_distributions": {
            "skill_speed": {"kind": "fixed", "value": 1.0},
            "defect_rate": {"kind": "fixed", "value": 0.1},
            "clarification_need": {"kind": "fixed", "value": 0.15},
            "response_delay_async": {"kind": "fixed", "value": 5.0},
            "response_delay_sync": {"kind": "fixed", "value": 0.5},
            "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
            "cost_per_message": {"kind": "fixed", "value": 0.05},
        },
        "propagation": {"base_propagation": 0.8, "coupling_strength": 0.7},
        "mode_effects": {
            "misalignment_factor_async": 1.0,
            "misalignment_factor_sync": 0.35,
            "defect_multiplier_async": 1.6,
            "defect_multiplier_sync": 0.5,
            "productivity_factor_async": 1.0,
            "productivity_factor_sync": 1.0,
        },
        "policy": {"type": "async_only"},
        "costs": {"cost_per_sync_minute": 1.0, "cost_per_message": 0.05},
    }


def run_policy(cfg: dict, policy_type: str):
    c = copy.deepcopy(cfg)
    c["policy"] = {"type": policy_type, "W": 30, "T_enter": 0.15, "T_exit": 0.05, "K": 10}
    config = dict_to_config(c)
    runs, _, cascades, _ = run_many(config)
    return runs, cascades


def test_zero_coupling_has_no_cascade():
    cfg = base_cfg()
    cfg["propagation"]["coupling_strength"] = 0.0
    runs, cascades = run_policy(cfg, "async_only")
    assert all(float(r["avg_cascade_size"]) == 0.0 for r in runs)
    assert all(int(c["size"]) == 0 for c in cascades)


def test_always_sync_reduces_rework_vs_async_in_high_risk_regime():
    cfg = base_cfg()

    async_runs, _ = run_policy(cfg, "async_only")
    sync_runs, _ = run_policy(cfg, "always_sync")

    async_rework = statistics.mean(float(r["total_rework_events"]) for r in async_runs)
    sync_rework = statistics.mean(float(r["total_rework_events"]) for r in sync_runs)

    assert sync_rework < async_rework


def test_swarm_coordination_cost_between_async_and_sync():
    cfg = base_cfg()

    async_runs, _ = run_policy(cfg, "async_only")
    sync_runs, _ = run_policy(cfg, "always_sync")
    swarm_runs, _ = run_policy(cfg, "swarm")

    async_cost = statistics.mean(float(r["coordination_cost"]) for r in async_runs)
    sync_cost = statistics.mean(float(r["coordination_cost"]) for r in sync_runs)
    swarm_cost = statistics.mean(float(r["coordination_cost"]) for r in swarm_runs)

    assert async_cost <= swarm_cost <= sync_cost
