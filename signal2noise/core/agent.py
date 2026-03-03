"""Agent model: skill, cognitive load, state machine, time budget allocation."""

from __future__ import annotations

from dataclasses import dataclass, field

from signal2noise.core.types import AgentState


@dataclass
class Agent:
    """A single team member participating in the simulation.

    Parameters
    ----------
    id:
        Unique agent identifier (e.g. "A0", "A1").
    skill_level:
        Competence in [0, 1]. Higher skill → lower defect probability and
        faster effective work rate.
    position:
        Ordinal station in the serial workflow (e.g. 0=Stage A, 1=Stage B).
    cognitive_load:
        Current accumulated fatigue in [0, 1]. Updated each tick by the
        cognitive load model.
    state:
        Current activity state for the tick.
    """

    id: str
    skill_level: float
    position: int = 0
    cognitive_load: float = 0.0
    state: AgentState = AgentState.IDLE

    # Time budget fractions for the current tick (set by allocator each tick)
    _work_fraction: float = field(default=1.0, repr=False)
    _sync_fraction: float = field(default=0.0, repr=False)
    _async_fraction: float = field(default=0.0, repr=False)

    # -----------------------------------------------------------------------
    # Derived properties
    # -----------------------------------------------------------------------

    def effective_error_rate(
        self,
        task_complexity: float,
        base_error_rate: float = 0.15,
        cognitive_load_penalty: float = 0.5,
    ) -> float:
        """Probability that this agent produces a defect on a given task.

        Uses the formula from the spec:

            P_error = base_error_rate
                      × (task_complexity / skill_level)
                      × (1 + cognitive_load_penalty × cognitive_load)

        Parameters
        ----------
        task_complexity:
            Complexity of the task in [0, 1].
        base_error_rate:
            Configurable constant; default 0.15.
        cognitive_load_penalty:
            How much fatigue amplifies errors; default 0.5.

        Returns
        -------
        float
            Defect probability clamped to [0, 1].
        """
        skill = max(self.skill_level, 1e-6)
        p = base_error_rate * (task_complexity / skill) * (1.0 + cognitive_load_penalty * self.cognitive_load)
        return max(0.0, min(1.0, p))

    def apply_allocation(self, w: float, s: float, a: float) -> None:
        """Store the time-budget fractions for the current tick.

        Parameters
        ----------
        w:
            Fraction spent working (producing output).
        s:
            Fraction spent in synchronous communication.
        a:
            Fraction spent on asynchronous communication.
        """
        total = w + s + a
        if total > 0:
            self._work_fraction = w / total
            self._sync_fraction = s / total
            self._async_fraction = a / total
        else:
            self._work_fraction = 1.0
            self._sync_fraction = 0.0
            self._async_fraction = 0.0

        # Update state to reflect dominant activity
        if self._sync_fraction >= self._work_fraction and self._sync_fraction >= self._async_fraction:
            self.state = AgentState.IN_SYNC
        elif self._async_fraction > self._work_fraction:
            self.state = AgentState.READING_ASYNC
        elif self._work_fraction > 0:
            self.state = AgentState.WORKING
        else:
            self.state = AgentState.IDLE

    @property
    def work_fraction(self) -> float:
        """Fraction of tick budget allocated to productive work."""
        return self._work_fraction

    @property
    def sync_fraction(self) -> float:
        """Fraction of tick budget allocated to synchronous communication."""
        return self._sync_fraction

    @property
    def async_fraction(self) -> float:
        """Fraction of tick budget allocated to asynchronous communication."""
        return self._async_fraction
