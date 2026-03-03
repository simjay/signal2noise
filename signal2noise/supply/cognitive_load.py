"""Cognitive load accumulation and decay model."""

from __future__ import annotations

from dataclasses import dataclass

from signal2noise.core.agent import Agent
from signal2noise.core.types import AgentState


@dataclass
class CognitiveLoadModel:
    """Updates agent cognitive load each tick based on their activity.

    The model implements the formula from the spec:

        cognitive_load(t+1) = clamp(0, 1,
            cognitive_load(t)
            + sync_load_rate  × s_i    # sync meetings add load
            + async_load_rate × a_i    # async messages add (less) load
            - recovery_rate   × w_i    # focused work recovers load
            - natural_decay            # passive recovery
        )

    Parameters
    ----------
    sync_load_rate:
        Load added per tick of sync participation. Default 0.40.
    async_load_rate:
        Load added per tick of async activity. Default 0.05.
    recovery_rate:
        Load recovered per tick of focused work. Default 0.03.
    natural_decay:
        Passive load decay per tick (regardless of activity). Default 0.01.

    Note
    ----
    The defaults here are overridden by ``SimulationConfig`` when the model
    is constructed inside ``Simulation.run()``.  The values below match the
    paper's calibrated baseline so the class can also be used standalone.
    """

    sync_load_rate: float = 0.40
    async_load_rate: float = 0.05
    recovery_rate: float = 0.03
    natural_decay: float = 0.01

    def update(self, agents: list[Agent]) -> None:
        """Update cognitive load for every agent based on their current state.

        Parameters
        ----------
        agents:
            List of agents whose cognitive loads will be updated in place.
        """
        for agent in agents:
            delta = (
                self.sync_load_rate * agent.sync_fraction
                + self.async_load_rate * agent.async_fraction
                - self.recovery_rate * agent.work_fraction
                - self.natural_decay
            )
            agent.cognitive_load = max(0.0, min(1.0, agent.cognitive_load + delta))
