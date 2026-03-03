"""signal2noise — Agent-Based Model for adaptive coordination protocols.

Public API re-exports for the most common use cases.

Quick start
-----------
>>> from signal2noise import Simulation, SimulationConfig
>>> cfg = SimulationConfig(protocol="adaptive", tau=0.3, num_agents=5, num_tasks=20, random_seed=42)
>>> result = Simulation(cfg).run()
>>> print(f"eta* = {result.rework_adjusted_eta:.3f}")

Parameter sweep
---------------
>>> from signal2noise.experiments import ParameterSweep
>>> sweep = ParameterSweep(
...     base_config=SimulationConfig(num_agents=5, num_tasks=20),
...     sweep_params={"protocol": ["async_only", "sync_always", "adaptive"], "tau": [0.1, 0.3, 0.5]},
...     runs_per_config=10,
... )
>>> results = sweep.run()

CAS 2026 paper experiment
-------------------------
>>> from signal2noise.experiments import presets
>>> results = presets.cas2026_paper(runs_per_config=100)
"""

from signal2noise.core.simulation import Simulation, SimulationConfig
from signal2noise.core.types import AgentState, RunSummary, TaskStatus, TickSnapshot
from signal2noise.protocols import AdaptiveProtocol, AsyncOnlyProtocol, SyncAlwaysProtocol

__version__ = "0.1.0"

__all__ = [
    "AdaptiveProtocol",
    "AgentState",
    "AsyncOnlyProtocol",
    "RunSummary",
    "Simulation",
    "SimulationConfig",
    "SyncAlwaysProtocol",
    "TaskStatus",
    "TickSnapshot",
]
