"""Rework engine: validation failure → upstream cascade propagation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import TaskStatus


@dataclass
class ReworkEngine:
    """Models rework demand including upstream cascade propagation.

    When a task fails validation it is set to REWORK.  With probability
    ``p_cascade``, each upstream dependency is *also* set to REWORK (bounded
    by ``max_cascade_depth``).  This nonlinear amplification produces the
    phase-transition dynamics described in the paper.

    Parameters
    ----------
    p_cascade:
        Per-edge probability that a rework event cascades to an upstream task.
        Default 0.3.
    max_cascade_depth:
        Maximum hops upstream the cascade can propagate.  Default 2.
    rng:
        NumPy random Generator used for all stochastic decisions.
    """

    p_cascade: float = 0.3
    max_cascade_depth: int = 2
    rework_effort_multiplier: float = 1.0
    rng: np.random.Generator = field(default_factory=np.random.default_rng)

    def propagate(
        self, task_graph: TaskGraph, tick: int
    ) -> tuple[int, list[int]]:
        """Cascade REWORK events from currently failing tasks upstream.

        Iterates over all tasks currently in REWORK status and, for each,
        stochastically propagates failures to their upstream dependencies up
        to ``max_cascade_depth`` hops away.

        Parameters
        ----------
        task_graph:
            The current task graph (mutated in place).
        tick:
            Current simulation tick (unused; included for API consistency).

        Returns
        -------
        tuple[int, list[int]]
            - ``rework_demand``: Total number of tasks added/confirmed in
              REWORK state during this propagation pass.
            - ``cascade_depths``: List of propagation depths for each cascade
              event (used for secondary metric computation).
        """
        rework_root_ids = [
            tid
            for tid, t in task_graph.tasks.items()
            if t.status == TaskStatus.REWORK
        ]

        newly_reworked: set[str] = set(rework_root_ids)
        cascade_depths: list[int] = []

        for root_id in rework_root_ids:
            depth = self._cascade_upstream(task_graph, root_id, newly_reworked)
            if depth > 0:
                cascade_depths.append(depth)

        return len(newly_reworked), cascade_depths

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cascade_upstream(
        self,
        task_graph: TaskGraph,
        start_id: str,
        already_reworked: set[str],
    ) -> int:
        """BFS-style upstream cascade bounded by max_cascade_depth.

        Parameters
        ----------
        task_graph:
            The task graph to mutate.
        start_id:
            ID of the task that triggered the cascade.
        already_reworked:
            Set of task IDs already in REWORK (updated in place).

        Returns
        -------
        int
            Maximum depth reached by the cascade (0 if no upstream tasks
            were affected).
        """
        # Build reverse adjacency: for each task, its direct upstream deps
        # We only propagate *upstream* (toward dependencies, not dependents).
        frontier: list[tuple[str, int]] = [(start_id, 0)]
        visited: set[str] = {start_id}
        max_depth_reached = 0

        while frontier:
            current_id, depth = frontier.pop(0)
            if depth >= self.max_cascade_depth:
                continue

            current_task = task_graph.tasks.get(current_id)
            if current_task is None:
                continue

            for dep_id in current_task.dependency_set:
                if dep_id in visited:
                    continue
                visited.add(dep_id)

                if self.rng.random() < self.p_cascade:
                    dep_task = task_graph.tasks.get(dep_id)
                    if dep_task is None:
                        continue
                    # Only mark completed/in-progress tasks as rework
                    if dep_task.status in (
                        TaskStatus.DONE,
                        TaskStatus.IN_PROGRESS,
                        TaskStatus.IN_REVIEW,
                    ):
                        dep_task.status = TaskStatus.REWORK
                        dep_task.rework_count += 1
                        dep_task.remaining_effort = dep_task.base_effort * self.rework_effort_multiplier
                        already_reworked.add(dep_id)
                        new_depth = depth + 1
                        max_depth_reached = max(max_depth_reached, new_depth)
                        frontier.append((dep_id, new_depth))

        return max_depth_reached
