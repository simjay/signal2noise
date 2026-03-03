"""Abstract Protocol interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from signal2noise.core.agent import Agent
from signal2noise.core.types import AllocationPolicy


class Protocol(ABC):
    """Base class for coordination protocols (Groups A, B, C).

    All protocols implement a single ``decide`` method that maps the current
    rework rate and agent states to an ``AllocationPolicy`` — the per-agent
    time-budget fractions for the coming tick.
    """

    @abstractmethod
    def decide(
        self,
        rework_rate: float,
        agents: list[Agent],
        tick: int,
    ) -> AllocationPolicy:
        """Determine the allocation policy for this tick.

        Parameters
        ----------
        rework_rate:
            Current system rework rate R(t) = D_rework / D_total in [0, 1].
        agents:
            Current list of agents (read-only; do not mutate).
        tick:
            Current simulation tick.

        Returns
        -------
        AllocationPolicy
            Maps each agent_id to (work_fraction, sync_fraction, async_fraction).
            Fractions are normalised internally so they need not sum to 1.0.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the protocol's display name for logging and comparison."""
        ...
