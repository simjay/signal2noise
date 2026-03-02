from __future__ import annotations

import pytest

from signal2noise.cli import _expand_grid


def test_expand_grid_with_stress_ladder_combines_with_sweep() -> None:
    cfg = {
        "sweep": {"policy.type": ["async_only", "swarm"]},
        "stress_ladder": {
            "enabled": True,
            "multipliers": [1.0, 3.0],
            "parameters": {
                "propagation.p_change": {"anchor": 0.01, "min": 0.0, "max": 0.02},
                "propagation.base_propagation": 0.1,
            },
        },
    }

    combos = _expand_grid(cfg)
    assert len(combos) == 4

    multipliers = sorted({float(c["stress_multiplier"]) for c in combos})
    assert multipliers == [1.0, 3.0]

    p_change_vals = sorted({float(c["propagation.p_change"]) for c in combos})
    assert p_change_vals == [0.01, 0.02]

    base_prop_vals = sorted({float(c["propagation.base_propagation"]) for c in combos})
    assert base_prop_vals == [0.1, 0.30000000000000004]


def test_expand_grid_stress_ladder_conflict_raises() -> None:
    cfg = {
        "sweep": {"propagation.p_change": [0.01]},
        "stress_ladder": {
            "enabled": True,
            "multipliers": [2.0],
            "parameters": {"propagation.p_change": {"anchor": 0.02}},
        },
    }
    with pytest.raises(ValueError):
        _expand_grid(cfg)

