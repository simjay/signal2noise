"""Group B — Sync Always protocol: s_i >= s_min always."""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AllocationPolicy
from signal2noise.protocols.base import Protocol


class SyncAlwaysProtocol(Protocol):
    """Group B control condition: agents maintain a persistent sync channel.

    Every tick agents devote at least ``s_min`` of their time to synchronous
    communication.  The remaining time is split between work and async.

    Expected outcome: lower rework rate but lower throughput due to
    constant meeting overhead and cognitive load accumulation.

    Parameters
    ----------
    s_min:
        Minimum sync fraction imposed on all agents each tick. Default 0.2.
    """

    def __init__(self, s_min: float = 0.2) -> None:
        self.s_min = max(0.0, min(1.0, s_min))

    def decide(
        self,
        rework_rate: float,
        agents: list[Agent],
        tick: int,
    ) -> AllocationPolicy:
        """Return s_min sync fraction for every agent.

        Parameters
        ----------
        rework_rate:
            Ignored by this protocol.
        agents:
            Agents to allocate.
        tick:
            Ignored by this protocol.

        Returns
        -------
        AllocationPolicy
            Each agent: (1 - s_min, s_min, 0).
        """
        w = max(0.0, 1.0 - self.s_min)
        return {agent.id: (w, self.s_min, 0.0) for agent in agents}

    def name(self) -> str:
        return "sync_always"
