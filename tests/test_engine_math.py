from __future__ import annotations

from signal2noise.engine import invalidate_probability


def test_invalidate_probability_formula_and_bounds():
    assert invalidate_probability(0.35, 0.6, 1.0) == 0.21
    assert invalidate_probability(1.0, 1.0, 2.0) == 1.0
    assert invalidate_probability(0.2, 0.5, -1.0) == 0.0
