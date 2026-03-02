from __future__ import annotations

from signal2noise.config import dict_to_config
from signal2noise.engine import run_many


def test_run_summary_includes_lean_core_metrics() -> None:
    cfg = {
        "seed": 11,
        "n_runs": 3,
        "ticks_per_run": 120,
        "team_size": 3,
        "integration_check_interval": 1,
        "rework_effort_fraction": 0.4,
        "retest_effort_fraction": 0.25,
        "task_graph": {"type": "chain", "n_tasks": 8},
        "task_effort_distribution": {"kind": "fixed", "value": 3.0},
        "agent_distributions": {
            "skill_speed": {"kind": "fixed", "value": 1.0},
            "defect_rate": {"kind": "fixed", "value": 0.12},
            "clarification_need": {"kind": "fixed", "value": 0.10},
            "response_delay_async": {"kind": "fixed", "value": 3.0},
            "response_delay_sync": {"kind": "fixed", "value": 0.5},
            "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
            "cost_per_message": {"kind": "fixed", "value": 0.05},
        },
        "propagation": {"base_propagation": 0.2, "coupling_strength": 0.6, "p_change": 0.01},
        "mode_effects": {
            "misalignment_factor_async": 1.0,
            "misalignment_factor_sync": 0.6,
            "defect_multiplier_async": 1.2,
            "defect_multiplier_sync": 0.9,
            "productivity_factor_async": 1.0,
            "productivity_factor_sync": 1.0,
        },
        "policy": {"type": "swarm", "W": 8, "T_enter": 0.4, "T_exit": 0.1, "K": 3},
        "costs": {"cost_per_sync_minute": 1.0, "cost_per_message": 0.05},
        "metrics": {"cognitive_load_lambda": 0.5, "gap_high_threshold": 1.0},
    }
    runs, _, _, _ = run_many(dict_to_config(cfg))
    assert runs
    row = runs[0]

    assert "B_total" in row
    assert "tickets_processed" in row
    assert "bounce_rate" in row
    assert "S_task" in row
    assert "C_load" in row
    assert "eta" in row
    assert "false_alarm_rate" in row
    assert "missed_escalation_rate" in row

    assert 0.0 <= float(row["false_alarm_rate"]) <= 1.0
    assert 0.0 <= float(row["missed_escalation_rate"]) <= 1.0
    assert float(row["bounce_rate"]) >= 0.0


def test_dual_process_noise_only_creates_churn_without_cascades() -> None:
    cfg = {
        "seed": 7,
        "n_runs": 1,
        "ticks_per_run": 80,
        "team_size": 2,
        "integration_check_interval": 1,
        "rework_effort_fraction": 0.3,
        "retest_effort_fraction": 0.2,
        "task_graph": {"type": "chain", "n_tasks": 6},
        "task_effort_distribution": {"kind": "fixed", "value": 1.5},
        "agent_distributions": {
            "skill_speed": {"kind": "fixed", "value": 1.0},
            "defect_rate": {"kind": "fixed", "value": 0.0},
            "clarification_need": {"kind": "fixed", "value": 0.0},
            "response_delay_async": {"kind": "fixed", "value": 1.0},
            "response_delay_sync": {"kind": "fixed", "value": 1.0},
            "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
            "cost_per_message": {"kind": "fixed", "value": 0.0},
        },
        "propagation": {
            "base_propagation": 1.0,
            "coupling_strength": 1.0,
            "p_signal_change": 0.0,
            "p_noise_change": 1.0,
            "signal_shock_multiplier": 3.0,
        },
        "mode_effects": {
            "misalignment_factor_async": 1.0,
            "misalignment_factor_sync": 1.0,
            "defect_multiplier_async": 1.0,
            "defect_multiplier_sync": 1.0,
            "productivity_factor_async": 1.0,
            "productivity_factor_sync": 1.0,
        },
        "policy": {"type": "async_only"},
    }
    runs, _, _, _ = run_many(dict_to_config(cfg))
    assert runs
    row = runs[0]
    assert float(row["B_total"]) == 0.0
    assert float(row["avg_cascade_size"]) == 0.0
    assert float(row["demand_mean"]) > 0.0


def test_dual_process_signal_shocks_create_cascades() -> None:
    cfg = {
        "seed": 9,
        "n_runs": 1,
        "ticks_per_run": 80,
        "team_size": 2,
        "integration_check_interval": 1,
        "rework_effort_fraction": 0.3,
        "retest_effort_fraction": 0.2,
        "task_graph": {"type": "chain", "n_tasks": 6},
        "task_effort_distribution": {"kind": "fixed", "value": 1.5},
        "agent_distributions": {
            "skill_speed": {"kind": "fixed", "value": 1.0},
            "defect_rate": {"kind": "fixed", "value": 0.0},
            "clarification_need": {"kind": "fixed", "value": 0.0},
            "response_delay_async": {"kind": "fixed", "value": 1.0},
            "response_delay_sync": {"kind": "fixed", "value": 1.0},
            "cost_per_sync_minute": {"kind": "fixed", "value": 1.0},
            "cost_per_message": {"kind": "fixed", "value": 0.0},
        },
        "propagation": {
            "base_propagation": 1.0,
            "coupling_strength": 1.0,
            "p_signal_change": 1.0,
            "p_noise_change": 0.0,
            "signal_shock_multiplier": 3.0,
        },
        "mode_effects": {
            "misalignment_factor_async": 1.0,
            "misalignment_factor_sync": 1.0,
            "defect_multiplier_async": 1.0,
            "defect_multiplier_sync": 1.0,
            "productivity_factor_async": 1.0,
            "productivity_factor_sync": 1.0,
        },
        "policy": {"type": "async_only"},
    }
    runs, _, _, _ = run_many(dict_to_config(cfg))
    assert runs
    row = runs[0]
    assert float(row["B_total"]) > 0.0
    assert float(row["avg_cascade_size"]) > 0.0
