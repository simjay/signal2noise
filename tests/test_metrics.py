from __future__ import annotations

from signal2noise.metrics import aggregate_by_policy, build_phase_diagram


def test_aggregate_by_policy_includes_risk_and_tail_metrics() -> None:
    rows = [
        {
            "policy": "async_only",
            "coupling_strength": 0.5,
            "total_rework_events": 1,
            "avg_cascade_size": 0.0,
            "max_cascade_size": 0,
            "makespan": 10,
            "tasks_completed": 5,
            "coordination_cost": 1.0,
            "sync_minutes": 0.0,
            "messages_sent": 1,
            "test_pass_rate": 0.9,
            "quality_score": 0.91,
            "efficiency": 0.91,
        },
        {
            "policy": "async_only",
            "coupling_strength": 0.5,
            "total_rework_events": 6,
            "avg_cascade_size": 0.4,
            "max_cascade_size": 2,
            "makespan": 12,
            "tasks_completed": 5,
            "coordination_cost": 1.0,
            "sync_minutes": 0.0,
            "messages_sent": 2,
            "test_pass_rate": 0.8,
            "quality_score": 0.85,
            "efficiency": 0.85,
        },
    ]

    agg = aggregate_by_policy(rows)
    assert len(agg) == 1
    row = agg[0]

    assert row["bad_run_rate_rework_ge_8"] == 0.0
    assert row["bad_run_rate_cascade_ge_1"] == 0.5
    assert row["bad_run_rate_cascade_ge_2"] == 0.5
    assert row["bad_run_rate_quality_lt_0_9"] == 0.5
    assert row["tail10_total_rework_events_mean"] == 6.0
    assert row["tail10_max_cascade_size_mean"] == 2.0


def test_phase_diagram_includes_risk_and_tail_metrics() -> None:
    rows = [
        {
            "policy": "swarm",
            "coupling_strength": 0.2,
            "total_rework_events": 2,
            "avg_cascade_size": 0.0,
            "max_cascade_size": 0,
            "efficiency": 1.0,
        },
        {
            "policy": "swarm",
            "coupling_strength": 0.2,
            "total_rework_events": 7,
            "avg_cascade_size": 0.3,
            "max_cascade_size": 1,
            "efficiency": 0.9,
        },
    ]

    out = build_phase_diagram(rows)
    assert len(out) == 1
    row = out[0]
    assert row["bad_run_rate_rework_ge_8"] == 0.0
    assert row["bad_run_rate_cascade_ge_1"] == 0.5
    assert row["tail10_total_rework_events_mean"] == 7.0
    assert row["tail10_max_cascade_size_mean"] == 1.0
