from __future__ import annotations

from pathlib import Path

from signal2noise.calibration import calibrate_from_csv


def test_calibration_outputs_expected_keys(tmp_path: Path):
    p = tmp_path / "sample.csv"
    p.write_text(
        "fix_time,rework,cascade_size,post_done_change\n"
        "3.0,1,2,1\n"
        "5.0,0,1,0\n"
        "4.0,1,3,1\n",
        encoding="utf-8",
    )

    out = calibrate_from_csv(p)
    assert "task_effort_distribution" in out
    assert "agent_distributions" in out
    assert "propagation" in out
    assert "calibration_summary" in out
    assert "p_change" in out["propagation"]
