"""Demand generator: resolves dependencies and promotes BLOCKED → READY tasks."""

from __future__ import annotations

from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import TaskStatus


class DemandGenerator:
    """Resolves dependency constraints each tick and reports new demand.

    At each simulation tick, this component:
    1. Computes the set of tasks whose upstream dependencies are all satisfied.
    2. Promotes those tasks from BLOCKED to READY.
    3. Returns the count of newly promoted tasks (D_new).
    """

    def resolve(self, task_graph: TaskGraph, tick: int) -> int:
        """Resolve dependency constraints and return count of newly READY tasks.

        Tasks become READY when every entry in their ``dependency_set`` has
        reached DONE (or IN_REVIEW, which counts as satisfied for downstream
        unblocking purposes).

        Parameters
        ----------
        task_graph:
            The current task graph.
        tick:
            Current simulation tick (unused by this component; included for
            API consistency and future filtering).

        Returns
        -------
        int
            Number of tasks that transitioned BLOCKED → READY this tick
            (D_new component of total demand).
        """
        satisfiable = task_graph.satisfiable_ids()
        new_demand = 0
        for task in task_graph.tasks.values():
            if task.status != TaskStatus.BLOCKED:
                continue
            if task.dependency_set.issubset(satisfiable):
                task.status = TaskStatus.READY
                new_demand += 1
        return new_demand
