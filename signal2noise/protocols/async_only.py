"""Group A — Async Only protocol: s_i = 0 always."""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AllocationPolicy
from signal2noise.protocols.base import Protocol


class AsyncOnlyProtocol(Protocol):
    """Group A control condition: agents never hold synchronous meetings.

    All coordination happens through asynchronous messages.  Agents split
    their time between working (w_i) and reading/sending async messages
    (a_i).  Sync fraction s_i is always 0.

    Expected outcome: fast individual throughput but high rework due to
    insufficient coordination bandwidth.
    """

    # Fraction of non-work time allocated to async communication.
    _async_share: float = 0.15

    def decide(
        self,
        rework_rate: float,
        agents: list[Agent],
        tick: int,
    ) -> AllocationPolicy:
        """Return all-async allocation for every agent.

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
            Each agent gets (1 - async_share, 0, async_share).
        """
        w = 1.0 - self._async_share
        return {agent.id: (w, 0.0, self._async_share) for agent in agents}

    def name(self) -> str:
        return "async_only"
