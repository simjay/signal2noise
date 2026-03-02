from __future__ import annotations

import json

from signal2noise.config import dict_to_config
from signal2noise.engine import run_many


def test_overlap_allows_downstream_start_before_upstream_done():
    cfg = dict_to_config(
        {
            "seed": 1,
            "n_runs": 1,
            "ticks_per_run": 50,
            "team_size": 2,
            "integration_check_interval": 10,
            "task_graph": {"type": "chain", "n_tasks": 2},
            "task_effort_distribution": {"kind": "fixed", "value": 1.0},
            "agent_distributions": {
                "skill_speed": {"kind": "fixed", "value": 1.0},
                "defect_rate": {"kind": "fixed", "value": 0.0},
                "clarification_need": {"kind": "fixed", "value": 0.0},
                "response_delay_async": {"kind": "fixed", "value": 0.0},
                "response_delay_sync": {"kind": "fixed", "value": 0.0},
                "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
                "cost_per_message": {"kind": "fixed", "value": 0.0},
            },
            "propagation": {"base_propagation": 0.0, "coupling_strength": 0.0, "p_change": 0.0},
            "mode_effects": {
                "misalignment_factor_async": 1.0,
                "misalignment_factor_sync": 1.0,
                "defect_multiplier_async": 1.0,
                "defect_multiplier_sync": 1.0,
                "productivity_factor_async": 1.0,
                "productivity_factor_sync": 1.0,
            },
            "policy": {"type": "async_only"},
            "costs": {"cost_per_sync_minute": 1.0, "cost_per_message": 0.0},
        }
    )

    _, events, _, _ = run_many(cfg)

    t1_start = min(e["t"] for e in events if e["event_type"] == "TASK_START" and e["task_id"] == "T1")
    t0_done = min(e["t"] for e in events if e["event_type"] == "TASK_TEST_PASS" and e["task_id"] == "T0")

    assert t1_start <= t0_done


def test_exogenous_change_emits_version_change_event():
    cfg = dict_to_config(
        {
            "seed": 2,
            "n_runs": 1,
            "ticks_per_run": 20,
            "team_size": 1,
            "integration_check_interval": 10,
            "task_graph": {"type": "chain", "n_tasks": 1},
            "task_effort_distribution": {"kind": "fixed", "value": 2.0},
            "agent_distributions": {
                "skill_speed": {"kind": "fixed", "value": 1.0},
                "defect_rate": {"kind": "fixed", "value": 0.0},
                "clarification_need": {"kind": "fixed", "value": 0.0},
                "response_delay_async": {"kind": "fixed", "value": 0.0},
                "response_delay_sync": {"kind": "fixed", "value": 0.0},
                "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
                "cost_per_message": {"kind": "fixed", "value": 0.0},
            },
            "propagation": {"base_propagation": 0.0, "coupling_strength": 0.0, "p_change": 1.0},
            "mode_effects": {
                "misalignment_factor_async": 1.0,
                "misalignment_factor_sync": 1.0,
                "defect_multiplier_async": 1.0,
                "defect_multiplier_sync": 1.0,
                "productivity_factor_async": 1.0,
                "productivity_factor_sync": 1.0,
            },
            "policy": {"type": "async_only"},
            "costs": {"cost_per_sync_minute": 1.0, "cost_per_message": 0.0},
        }
    )

    _, events, _, _ = run_many(cfg)

    has_exogenous_version_change = any(
        e["event_type"] == "TASK_VERSION_CHANGE" and json.loads(e["meta_json"]).get("source") == "exogenous"
        for e in events
    )
    assert has_exogenous_version_change
