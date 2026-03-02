from __future__ import annotations

import csv
from pathlib import Path

from signal2noise.resources import generate_resources


def _write_runs_summary(path: Path) -> None:
    rows = [
        # low regime
        {
            "run_id": 0,
            "policy": "async_only",
            "stress_multiplier": 1.0,
            "bounce_rate": 0.60,
            "eta": 0.40,
            "false_alarm_rate": 0.02,
            "missed_escalation_rate": 0.35,
            "C_load_per_ticket": 4.0,
        },
        {
            "run_id": 1,
            "policy": "swarm",
            "stress_multiplier": 1.0,
            "bounce_rate": 0.45,
            "eta": 0.55,
            "false_alarm_rate": 0.05,
            "missed_escalation_rate": 0.20,
            "C_load_per_ticket": 4.1,
        },
        {
            "run_id": 2,
            "policy": "always_sync",
            "stress_multiplier": 1.0,
            "bounce_rate": 0.40,
            "eta": 0.20,
            "false_alarm_rate": 0.60,
            "missed_escalation_rate": 0.01,
            "C_load_per_ticket": 7.0,
        },
        # near-threshold regime (include naive for ablation output)
        {
            "run_id": 3,
            "policy": "naive_trigger",
            "stress_multiplier": 3.0,
            "bounce_rate": 0.55,
            "eta": 0.30,
            "false_alarm_rate": 0.45,
            "missed_escalation_rate": 0.14,
            "C_load_per_ticket": 4.7,
        },
        {
            "run_id": 4,
            "policy": "swarm",
            "stress_multiplier": 3.0,
            "bounce_rate": 0.42,
            "eta": 0.44,
            "false_alarm_rate": 0.20,
            "missed_escalation_rate": 0.10,
            "C_load_per_ticket": 4.6,
        },
        {
            "run_id": 5,
            "policy": "async_only",
            "stress_multiplier": 3.0,
            "bounce_rate": 0.50,
            "eta": 0.41,
            "false_alarm_rate": 0.00,
            "missed_escalation_rate": 0.18,
            "C_load_per_ticket": 4.5,
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_generate_resources_outputs_tables(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    _write_runs_summary(in_dir / "runs_summary.csv")

    generate_resources(str(in_dir), str(out_dir))

    expected = [
        "mode_regime_summary.csv",
        "naive_vs_swarm_ablation.csv",
        "signal_capture_fixed_cost.csv",
    ]
    for name in expected:
        assert (out_dir / name).exists(), f"missing {name}"

    summary_rows = list(csv.DictReader((out_dir / "mode_regime_summary.csv").open()))
    assert summary_rows
    r0 = summary_rows[0]
    assert "bounce_rate_mean" in r0
    assert "eta_mean" in r0
    assert "false_alarm_rate_mean" in r0
    assert "missed_escalation_rate_mean" in r0

    ablation_rows = list(csv.DictReader((out_dir / "naive_vs_swarm_ablation.csv").open()))
    assert ablation_rows
    a0 = ablation_rows[0]
    assert "eta_gain_swarm_vs_naive" in a0

    fixed_rows = list(csv.DictReader((out_dir / "signal_capture_fixed_cost.csv").open()))
    assert fixed_rows
    f0 = fixed_rows[0]
    assert "signal_capture_bounce_gain_swarm_vs_async" in f0
    assert "eta_gain_swarm_vs_async_fixed_cost" in f0
