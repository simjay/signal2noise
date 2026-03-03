"""Core enumerations, dataclasses, and type aliases for signal2noise."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """Lifecycle states of a single task in the simulation."""

    BLOCKED = "BLOCKED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    REWORK = "REWORK"


class AgentState(str, Enum):
    """What an agent is doing during a given tick."""

    WORKING = "WORKING"
    IN_SYNC = "IN_SYNC"
    READING_ASYNC = "READING_ASYNC"
    IDLE = "IDLE"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Maps agent_id -> (w_i, s_i, a_i) time-budget fractions that sum to 1.0
AllocationPolicy = dict[str, tuple[float, float, float]]


# ---------------------------------------------------------------------------
# Tick snapshot (per-tick metrics record)
# ---------------------------------------------------------------------------

@dataclass
class TickSnapshot:
    """Complete state snapshot captured at the end of each simulation tick."""

    tick: int
    rework_rate: float
    new_demand: int
    rework_demand: int
    total_demand: int
    sync_active: bool
    tasks_done: int
    tasks_total: int
    agent_states: dict[str, AgentState]
    agent_cognitive_loads: dict[str, float]
    # Coordination cost accumulated in this tick
    sync_minutes_this_tick: float
    async_messages_this_tick: int


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    """Aggregate results produced by a single completed simulation run."""

    # Primary metrics (from paper)
    ticket_bounce_rate: float
    efficiency_ratio: float
    task_score: float
    total_coordination_cost: float

    # Rework-adjusted efficiency (primary comparison metric)
    rework_adjusted_eta: float = 0.0
    total_rework_cost: float = 0.0

    # Secondary metrics
    time_to_completion: int = 0
    throughput: float = 0.0
    cognitive_load_variance: float = 0.0
    mean_rework_cascade_depth: float = 0.0
    channel_utilization_ratio: float = 0.0
    demand_supply_ratio_mean: float = 0.0

    # Time series
    tick_snapshots: list[TickSnapshot] = field(default_factory=list)
