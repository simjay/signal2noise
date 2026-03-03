"""Task model: complexity, dependencies, validation gates, rework count."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from signal2noise.core.types import TaskStatus


@dataclass
class ValidationGate:
    """A single automated check that may fail, triggering rework.

    Parameters
    ----------
    name:
        Human-readable gate label (e.g. "unit_tests", "integration").
    pass_probability:
        Probability the gate passes on a clean (non-defective) task.
        Defective tasks always fail. Default 1.0.
    """

    name: str
    pass_probability: float = 1.0


@dataclass
class Task:
    """A unit of work in the task graph.

    Parameters
    ----------
    id:
        Unique task identifier (e.g. "T0", "T3").
    complexity:
        Difficulty in [0, 1]. Higher complexity → higher defect probability.
    dependency_set:
        IDs of upstream tasks whose outputs feed into this task.
    assigned_agent:
        Agent currently responsible; None if unassigned.
    validation_gates:
        Automated checks applied when the task is submitted for review.
    status:
        Current lifecycle state.
    rework_count:
        Number of times this task has bounced back.
    base_effort:
        Nominal work units required to complete the task (before any
        efficiency modifiers).
    remaining_effort:
        Work units still needed in the current cycle.
    """

    id: str
    complexity: float
    dependency_set: set[str] = field(default_factory=set)
    validation_gates: list[ValidationGate] = field(default_factory=list)
    assigned_agent: Optional[str] = None
    status: TaskStatus = TaskStatus.BLOCKED
    rework_count: int = 0
    base_effort: float = 1.0
    remaining_effort: float = 0.0

    def __post_init__(self) -> None:
        if self.remaining_effort <= 0.0:
            self.remaining_effort = self.base_effort

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_complete(self) -> bool:
        """Return True iff the task has status DONE."""
        return self.status == TaskStatus.DONE

    def is_blocked(self) -> bool:
        """Return True iff all upstream dependencies are unmet."""
        return self.status == TaskStatus.BLOCKED

    def can_start(self, done_task_ids: set[str]) -> bool:
        """Return True iff all dependencies are satisfied.

        Parameters
        ----------
        done_task_ids:
            Set of task IDs that have reached DONE or IN_REVIEW status.
        """
        return self.dependency_set.issubset(done_task_ids)
