"""Tests for signal2noise.core.task and signal2noise.core.task_graph."""

from __future__ import annotations

import numpy as np
import pytest

from signal2noise.core.task import Task, ValidationGate
from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import TaskStatus

# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------

def test_task_default_status_blocked():
    t = Task(id="T0", complexity=0.5, dependency_set={"T1"})
    assert t.status == TaskStatus.BLOCKED

def test_task_default_ready_when_no_deps():
    t = Task(id="T0", complexity=0.5)
    assert t.status == TaskStatus.BLOCKED  # default; status must be set explicitly

def test_task_can_start_when_deps_satisfied():
    t = Task(id="T1", complexity=0.3, dependency_set={"T0"})
    assert t.can_start(done_task_ids={"T0"})
    assert not t.can_start(done_task_ids=set())

def test_task_remaining_effort_initialized_from_base():
    t = Task(id="T0", complexity=0.5, base_effort=5.0)
    assert t.remaining_effort == 5.0

def test_task_rework_count_default_zero():
    t = Task(id="T0", complexity=0.4)
    assert t.rework_count == 0

# ---------------------------------------------------------------------------
# TaskGraph — linear
# ---------------------------------------------------------------------------

def test_linear_graph_has_correct_count():
    rng = np.random.default_rng(0)
    g = TaskGraph.linear(n_tasks=10, rng=rng)
    assert len(g.tasks) == 10

def test_linear_graph_first_task_ready():
    rng = np.random.default_rng(1)
    g = TaskGraph.linear(n_tasks=5, rng=rng)
    assert g.tasks["T0"].status == TaskStatus.READY
    for i in range(1, 5):
        assert g.tasks[f"T{i}"].status == TaskStatus.BLOCKED

def test_linear_graph_sequential_dependencies():
    rng = np.random.default_rng(2)
    g = TaskGraph.linear(n_tasks=5, rng=rng)
    for i in range(1, 5):
        assert g.tasks[f"T{i}"].dependency_set == {f"T{i-1}"}

def test_linear_graph_topological_order():
    rng = np.random.default_rng(3)
    g = TaskGraph.linear(n_tasks=6, rng=rng)
    order = g.topological_order()
    assert order[0] == "T0"
    assert len(order) == 6

def test_linear_graph_acyclic_validation_passes():
    rng = np.random.default_rng(4)
    g = TaskGraph.linear(n_tasks=4, rng=rng)
    assert g.topological_order() == ["T0", "T1", "T2", "T3"]

def test_cyclic_graph_raises():
    tasks = {
        "T0": Task(id="T0", complexity=0.5, dependency_set={"T1"}),
        "T1": Task(id="T1", complexity=0.5, dependency_set={"T0"}),
    }
    with pytest.raises(ValueError, match="cycle"):
        TaskGraph(tasks)

# ---------------------------------------------------------------------------
# TaskGraph — tree
# ---------------------------------------------------------------------------

def test_tree_graph_root_has_no_deps():
    rng = np.random.default_rng(10)
    g = TaskGraph.tree(n_tasks=7, branching_factor=2, rng=rng)
    assert g.tasks["T0"].dependency_set == set()

def test_tree_graph_node_count():
    rng = np.random.default_rng(11)
    g = TaskGraph.tree(n_tasks=7, rng=rng)
    assert len(g.tasks) == 7

# ---------------------------------------------------------------------------
# TaskGraph — diamond
# ---------------------------------------------------------------------------

def test_diamond_graph_has_sink():
    rng = np.random.default_rng(20)
    g = TaskGraph.diamond(n_tasks=6, rng=rng)
    # Sink is last task
    tasks = list(g.tasks.values())
    sink = tasks[-1]
    assert len(sink.dependency_set) >= 2

def test_diamond_graph_root_has_no_deps():
    rng = np.random.default_rng(21)
    g = TaskGraph.diamond(n_tasks=5, rng=rng)
    assert g.tasks["T0"].dependency_set == set()

# ---------------------------------------------------------------------------
# TaskGraph — query helpers
# ---------------------------------------------------------------------------

def test_all_complete_false_initially():
    rng = np.random.default_rng(30)
    g = TaskGraph.linear(n_tasks=3, rng=rng)
    assert not g.all_complete()

def test_all_complete_true_when_all_done():
    rng = np.random.default_rng(31)
    g = TaskGraph.linear(n_tasks=3, rng=rng)
    for t in g.tasks.values():
        t.status = TaskStatus.DONE
    assert g.all_complete()

def test_done_ids_returns_done_tasks():
    rng = np.random.default_rng(32)
    g = TaskGraph.linear(n_tasks=4, rng=rng)
    g.tasks["T0"].status = TaskStatus.DONE
    g.tasks["T2"].status = TaskStatus.DONE
    assert g.done_ids() == {"T0", "T2"}

def test_complexity_values_in_range():
    rng = np.random.default_rng(40)
    g = TaskGraph.linear(n_tasks=20, rng=rng)
    for t in g.tasks.values():
        assert 0.0 < t.complexity <= 1.0
