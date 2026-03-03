"""Tests for signal2noise.demand.generator and signal2noise.demand.rework."""

from __future__ import annotations

import numpy as np

from signal2noise.core.task import Task
from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import TaskStatus
from signal2noise.demand.generator import DemandGenerator
from signal2noise.demand.rework import ReworkEngine

# ---------------------------------------------------------------------------
# DemandGenerator tests
# ---------------------------------------------------------------------------

def _linear_graph(n: int) -> TaskGraph:
    rng = np.random.default_rng(0)
    return TaskGraph.linear(n_tasks=n, rng=rng)

def test_generator_promotes_no_tasks_when_nothing_done():
    g = _linear_graph(5)
    gen = DemandGenerator()
    # T0 is READY, T1–T4 are BLOCKED; none has deps satisfied yet
    new = gen.resolve(g, tick=0)
    # T0 is already READY (not BLOCKED) so resolve returns 0 newly promoted tasks
    assert new == 0
    # All downstream tasks should remain BLOCKED (T0 not done yet)
    for i in range(1, 5):
        assert g.tasks[f"T{i}"].status == TaskStatus.BLOCKED

def test_generator_promotes_tasks_when_deps_done():
    g = _linear_graph(3)
    gen = DemandGenerator()
    # Mark T0 as DONE (satisfiable)
    g.tasks["T0"].status = TaskStatus.DONE
    new = gen.resolve(g, tick=1)
    assert new == 1
    assert g.tasks["T1"].status == TaskStatus.READY

def test_generator_promotes_multiple_ready():
    rng = np.random.default_rng(5)
    # Diamond: T0 → {T1, T2, T3} → T4
    g = TaskGraph.diamond(n_tasks=4, rng=rng)
    gen = DemandGenerator()
    g.tasks["T0"].status = TaskStatus.DONE
    new = gen.resolve(g, tick=0)
    # All branches should become READY
    assert new >= 2

def test_generator_does_not_promote_already_ready():
    g = _linear_graph(3)
    gen = DemandGenerator()
    g.tasks["T0"].status = TaskStatus.DONE
    n1 = gen.resolve(g, tick=0)
    n2 = gen.resolve(g, tick=1)
    # Second call: T1 is already READY, should not re-promote
    assert n2 == 0
    assert g.tasks["T1"].status == TaskStatus.READY

# ---------------------------------------------------------------------------
# ReworkEngine tests
# ---------------------------------------------------------------------------

def test_rework_engine_no_cascade_when_p_zero():
    rng = np.random.default_rng(99)
    g = _linear_graph(5)
    # Set T2 to REWORK
    g.tasks["T2"].status = TaskStatus.REWORK
    engine = ReworkEngine(p_cascade=0.0, max_cascade_depth=2, rng=rng)
    total_rework, depths = engine.propagate(g, tick=0)
    # T2 is rework; p_cascade=0 so no upstream tasks affected
    assert total_rework == 1
    assert depths == []  # no cascades occurred (depth == 0)

def test_rework_engine_cascades_upstream_when_p_one():
    rng = np.random.default_rng(42)
    g = _linear_graph(5)
    # T2 is rework, T1 is IN_PROGRESS (eligible for cascade)
    g.tasks["T2"].status = TaskStatus.REWORK
    g.tasks["T1"].status = TaskStatus.IN_PROGRESS
    engine = ReworkEngine(p_cascade=1.0, max_cascade_depth=2, rng=rng)
    total_rework, depths = engine.propagate(g, tick=0)
    assert g.tasks["T1"].status == TaskStatus.REWORK
    assert total_rework >= 2  # T2 + T1

def test_rework_engine_respects_max_cascade_depth():
    rng = np.random.default_rng(7)
    g = _linear_graph(6)
    # Set T3 to rework, T2 and T1 in progress (eligible)
    g.tasks["T3"].status = TaskStatus.REWORK
    g.tasks["T2"].status = TaskStatus.IN_PROGRESS
    g.tasks["T1"].status = TaskStatus.IN_PROGRESS
    # Depth 1: T3 → T2; Depth 2: T2 → T1
    engine = ReworkEngine(p_cascade=1.0, max_cascade_depth=1, rng=rng)
    engine.propagate(g, tick=0)
    # Only T2 should be cascaded (depth=1 reached)
    assert g.tasks["T2"].status == TaskStatus.REWORK
    # T1 should NOT be cascaded (depth=2 would exceed max=1)
    assert g.tasks["T1"].status == TaskStatus.IN_PROGRESS

def test_rework_engine_does_not_cascade_not_started_tasks():
    rng = np.random.default_rng(11)
    g = _linear_graph(4)
    g.tasks["T2"].status = TaskStatus.REWORK
    # T1 is BLOCKED (not started) — should not be cascaded
    engine = ReworkEngine(p_cascade=1.0, max_cascade_depth=2, rng=rng)
    engine.propagate(g, tick=0)
    assert g.tasks["T1"].status != TaskStatus.REWORK

def test_rework_count_incremented_on_cascade():
    rng = np.random.default_rng(22)
    g = _linear_graph(4)
    g.tasks["T2"].status = TaskStatus.REWORK
    g.tasks["T1"].status = TaskStatus.DONE  # eligible
    prev_count = g.tasks["T1"].rework_count
    engine = ReworkEngine(p_cascade=1.0, max_cascade_depth=2, rng=rng)
    engine.propagate(g, tick=0)
    assert g.tasks["T1"].rework_count == prev_count + 1
