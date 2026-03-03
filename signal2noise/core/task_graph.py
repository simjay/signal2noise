"""DAG builder and manager: topological ordering, dependency resolution."""

from __future__ import annotations

from collections import deque
from typing import Literal

import numpy as np

from signal2noise.core.task import Task, ValidationGate
from signal2noise.core.types import TaskStatus


class TaskGraph:
    """Directed Acyclic Graph of tasks representing the project work.

    Attributes
    ----------
    tasks:
        Mapping from task ID to Task object.
    """

    def __init__(self, tasks: dict[str, Task]) -> None:
        self.tasks = tasks
        self._validate_acyclic()

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def linear(
        cls,
        n_tasks: int,
        complexity_distribution: Literal["uniform", "normal", "bimodal"] = "uniform",
        complexity_mean: float = 0.5,
        complexity_std: float = 0.15,
        base_effort: float = 1.0,
        rng: np.random.Generator | None = None,
    ) -> "TaskGraph":
        """Build a simple chain: T0 → T1 → … → T(n-1).

        Parameters
        ----------
        n_tasks:
            Number of tasks in the chain.
        complexity_distribution:
            Distribution of task complexity values.
        complexity_mean:
            Mean complexity (for normal/bimodal distributions).
        complexity_std:
            Std dev of complexity (for normal distribution).
        base_effort:
            Nominal effort per task.
        rng:
            NumPy random Generator.
        """
        if rng is None:
            rng = np.random.default_rng()

        complexities = _sample_complexities(
            n_tasks, complexity_distribution, complexity_mean, complexity_std, rng
        )
        tasks: dict[str, Task] = {}
        for i in range(n_tasks):
            tid = f"T{i}"
            deps = {f"T{i - 1}"} if i > 0 else set()
            tasks[tid] = Task(
                id=tid,
                complexity=float(complexities[i]),
                dependency_set=deps,
                status=TaskStatus.READY if i == 0 else TaskStatus.BLOCKED,
                base_effort=base_effort,
            )
        return cls(tasks)

    @classmethod
    def tree(
        cls,
        n_tasks: int,
        branching_factor: int = 2,
        complexity_distribution: Literal["uniform", "normal", "bimodal"] = "uniform",
        complexity_mean: float = 0.5,
        complexity_std: float = 0.15,
        base_effort: float = 1.0,
        rng: np.random.Generator | None = None,
    ) -> "TaskGraph":
        """Build a tree graph where each parent fans out to *branching_factor* children.

        Parameters
        ----------
        n_tasks:
            Total number of tasks.
        branching_factor:
            Number of children per internal node.
        complexity_distribution:
            Distribution of task complexity values.
        complexity_mean:
            Mean complexity.
        complexity_std:
            Std dev of complexity.
        base_effort:
            Nominal effort per task.
        rng:
            NumPy random Generator.
        """
        if rng is None:
            rng = np.random.default_rng()

        complexities = _sample_complexities(
            n_tasks, complexity_distribution, complexity_mean, complexity_std, rng
        )
        tasks: dict[str, Task] = {}
        for i in range(n_tasks):
            tid = f"T{i}"
            if i == 0:
                deps: set[str] = set()
                status = TaskStatus.READY
            else:
                parent_idx = (i - 1) // branching_factor
                deps = {f"T{parent_idx}"}
                status = TaskStatus.BLOCKED
            tasks[tid] = Task(
                id=tid,
                complexity=float(complexities[i]),
                dependency_set=deps,
                status=status,
                base_effort=base_effort,
            )
        return cls(tasks)

    @classmethod
    def diamond(
        cls,
        n_tasks: int = 15,
        complexity_distribution: Literal["uniform", "normal", "bimodal"] = "uniform",
        complexity_mean: float = 0.5,
        complexity_std: float = 0.15,
        base_effort: float = 1.0,
        rng: np.random.Generator | None = None,
    ) -> "TaskGraph":
        """Build a diamond-shaped DAG (fan-out then fan-in).

        Parameters
        ----------
        n_tasks:
            Total number of tasks (will be adjusted to nearest valid diamond).
        complexity_distribution:
            Distribution of task complexity values.
        complexity_mean:
            Mean complexity.
        complexity_std:
            Std dev of complexity.
        base_effort:
            Nominal effort per task.
        rng:
            NumPy random Generator.
        """
        if rng is None:
            rng = np.random.default_rng()

        # Structure: 1 root → n_parallel branches → 1 sink
        n_parallel = max(2, n_tasks - 2)
        actual_n = n_parallel + 2  # root + branches + sink
        complexities = _sample_complexities(
            actual_n, complexity_distribution, complexity_mean, complexity_std, rng
        )
        tasks: dict[str, Task] = {}
        # root
        tasks["T0"] = Task(
            id="T0",
            complexity=float(complexities[0]),
            dependency_set=set(),
            status=TaskStatus.READY,
            base_effort=base_effort,
        )
        # branches
        for i in range(1, n_parallel + 1):
            tasks[f"T{i}"] = Task(
                id=f"T{i}",
                complexity=float(complexities[i]),
                dependency_set={"T0"},
                status=TaskStatus.BLOCKED,
                base_effort=base_effort,
            )
        # sink
        sink_id = f"T{n_parallel + 1}"
        tasks[sink_id] = Task(
            id=sink_id,
            complexity=float(complexities[n_parallel + 1]),
            dependency_set={f"T{i}" for i in range(1, n_parallel + 1)},
            status=TaskStatus.BLOCKED,
            base_effort=base_effort,
        )
        return cls(tasks)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def ready_task_ids(self) -> list[str]:
        """Return IDs of all tasks currently in READY or REWORK status."""
        return [
            tid
            for tid, t in self.tasks.items()
            if t.status in (TaskStatus.READY, TaskStatus.REWORK)
        ]

    def all_complete(self) -> bool:
        """Return True iff every task has status DONE."""
        return all(t.status == TaskStatus.DONE for t in self.tasks.values())

    def done_ids(self) -> set[str]:
        """Return the set of task IDs that have reached DONE."""
        return {tid for tid, t in self.tasks.items() if t.status == TaskStatus.DONE}

    def satisfiable_ids(self) -> set[str]:
        """Return task IDs considered 'satisfied' for dependency resolution.

        DONE and IN_REVIEW tasks both unblock downstream tasks.
        """
        return {
            tid
            for tid, t in self.tasks.items()
            if t.status in (TaskStatus.DONE, TaskStatus.IN_REVIEW)
        }

    def topological_order(self) -> list[str]:
        """Return task IDs in a valid topological processing order (Kahn's algorithm).

        Returns
        -------
        list[str]
            Task IDs from sources to sinks.
        """
        in_degree: dict[str, int] = {tid: 0 for tid in self.tasks}
        children: dict[str, list[str]] = {tid: [] for tid in self.tasks}
        for tid, task in self.tasks.items():
            for dep in task.dependency_set:
                if dep in self.tasks:
                    in_degree[tid] += 1
                    children[dep].append(tid)

        queue: deque[str] = deque(tid for tid, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        while queue:
            tid = queue.popleft()
            order.append(tid)
            for child in children[tid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        return order

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_acyclic(self) -> None:
        """Raise ValueError if the task graph contains a cycle."""
        order = self.topological_order()
        if len(order) != len(self.tasks):
            raise ValueError("TaskGraph contains a cycle — not a valid DAG.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_complexities(
    n: int,
    distribution: Literal["uniform", "normal", "bimodal"],
    mean: float,
    std: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample *n* complexity values from the given distribution.

    Parameters
    ----------
    n:
        Number of samples.
    distribution:
        "uniform", "normal", or "bimodal".
    mean:
        Target mean complexity (used for normal/bimodal).
    std:
        Standard deviation (used for normal/bimodal).
    rng:
        NumPy random Generator.

    Returns
    -------
    np.ndarray
        Array of complexity values clamped to [0, 1].
    """
    if distribution == "uniform":
        low = max(0.0, mean - std * 1.732)
        high = min(1.0, mean + std * 1.732)
        vals = rng.uniform(low, high, size=n)
    elif distribution == "normal":
        vals = rng.normal(mean, std, size=n)
    elif distribution == "bimodal":
        mask = rng.random(size=n) < 0.5
        vals = np.where(
            mask,
            rng.normal(mean - 2 * std, std, size=n),
            rng.normal(mean + 2 * std, std, size=n),
        )
    else:
        raise ValueError(f"Unknown complexity distribution: {distribution!r}")
    return np.clip(vals, 0.01, 1.0)
