"""Group C — Adaptive (Communication Valve) protocol.

Defaults to async, but forces a sync 'swarm' when rework rate R(t) > τ.
Reverts to async once rework is resolved (R(t) falls below τ × exit_ratio).
"""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AllocationPolicy
from signal2noise.protocols.base import Protocol


class AdaptiveProtocol(Protocol):
    """Group C treatment: rework-triggered media switching.

    The protocol monitors the system rework rate R(t) each tick and opens
    the *Communication Valve* (switches from async to sync) when R(t) > τ.
    Once the rework is resolved, it reverts to async.

    This implements the core research mechanism: defaulting to async
    (maximising work time) but escalating to high-bandwidth sync exactly
    when the system signals it's needed.

    Parameters
    ----------
    tau:
        Rework rate threshold τ that triggers a sync swarm session.
        Default 0.3.
    exit_ratio:
        Multiplier on τ defining the exit threshold: when R(t) falls below
        ``tau × exit_ratio`` the valve closes. Default 0.5 (i.e. exits
        at 0.5 × τ to provide hysteresis and avoid rapid flapping).
    s_sync:
        Sync fraction assigned to each agent during an active swarm session.
        Default 0.3.
    async_share:
        Async fraction assigned to each agent in async-default mode.
        Default 0.15.
    """

    def __init__(
        self,
        tau: float = 0.3,
        exit_ratio: float = 0.5,
        s_sync: float = 0.2,
        async_share: float = 0.15,
    ) -> None:
        self.tau = tau
        self._exit_threshold = tau * exit_ratio
        self.s_sync = max(0.0, min(1.0, s_sync))
        self._async_share = max(0.0, min(1.0, async_share))
        self._valve_open = False

    @property
    def valve_open(self) -> bool:
        """Whether the Communication Valve is currently open (sync mode)."""
        return self._valve_open

    def decide(
        self,
        rework_rate: float,
        agents: list[Agent],
        tick: int,
    ) -> AllocationPolicy:
        """Open or close the valve based on R(t), then allocate budgets.

        Parameters
        ----------
        rework_rate:
            Current system rework rate R(t) = D_rework / D_total.
        agents:
            Agents to allocate.
        tick:
            Current simulation tick (unused).

        Returns
        -------
        AllocationPolicy
            In async mode: ``(1 - async_share, 0, async_share)`` per agent.
            In sync mode:  ``(1 - s_sync, s_sync, 0)`` per agent.
        """
        # Update valve state
        if not self._valve_open and rework_rate > self.tau:
            self._valve_open = True
        elif self._valve_open and rework_rate <= self._exit_threshold:
            self._valve_open = False

        if self._valve_open:
            w = max(0.0, 1.0 - self.s_sync)
            return {agent.id: (w, self.s_sync, 0.0) for agent in agents}
        else:
            w = max(0.0, 1.0 - self._async_share)
            return {agent.id: (w, 0.0, self._async_share) for agent in agents}

    def name(self) -> str:
        return "adaptive"
