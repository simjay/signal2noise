"""Core engine: agents, tasks, channels, and simulation loop."""

from signal2noise.core.agent import Agent
from signal2noise.core.channel import AsyncChannel, SyncChannel
from signal2noise.core.simulation import Simulation, SimulationConfig
from signal2noise.core.task import Task, ValidationGate
from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import (
    AgentState,
    AllocationPolicy,
    RunSummary,
    TaskStatus,
    TickSnapshot,
)

__all__ = [
    "Agent",
    "AgentState",
    "AllocationPolicy",
    "AsyncChannel",
    "RunSummary",
    "Simulation",
    "SimulationConfig",
    "SyncChannel",
    "Task",
    "TaskGraph",
    "TaskStatus",
    "TickSnapshot",
    "ValidationGate",
]
