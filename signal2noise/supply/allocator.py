"""Allocator: distributes agent time budgets per the active protocol policy."""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AllocationPolicy, AgentState


class Allocator:
    """Applies an AllocationPolicy to a list of agents each tick.

    The allocator translates a protocol's decision (expressed as an
    ``AllocationPolicy`` mapping agent IDs to ``(w, s, a)`` fractions) into
    per-agent state updates.

    If an agent ID is absent from the policy, it defaults to full work-mode
    ``(1.0, 0.0, 0.0)``.
    """

    def apply(
        self,
        agents: list[Agent],
        policy: AllocationPolicy,
    ) -> None:
        """Apply the allocation policy to all agents for this tick.

        Parameters
        ----------
        agents:
            List of agents to update.
        policy:
            Mapping from agent ID to (work, sync, async) fractions.
            Fractions are normalised by Agent.apply_allocation so they
            do not need to sum to exactly 1.0.
        """
        for agent in agents:
            if agent.id in policy:
                w, s, a = policy[agent.id]
            else:
                w, s, a = 1.0, 0.0, 0.0
            agent.apply_allocation(w, s, a)
