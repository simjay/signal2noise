from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    ASYNC = "ASYNC"
    SYNC = "SYNC"


class TaskState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_TEST = "READY_FOR_TEST"
    DONE = "DONE"
    REWORK = "REWORK"


@dataclass
class Agent:
    id: str
    skill_speed: float
    defect_rate: float
    clarification_need: float
    response_delay_async: float
    response_delay_sync: float
    cost_per_sync_minute: float
    cost_per_message: float


@dataclass
class Task:
    id: str
    base_effort: float
    owner_agent_id: str
    deps: list[str]
    dependents: list[str] = field(default_factory=list)
    coupling_to_dep: dict[str, float] = field(default_factory=dict)

    state: TaskState = TaskState.NOT_STARTED
    remaining_work: float = 0.0
    version: int = 0
    rework_count: int = 0
    pending_defect: bool = False

    # Snapshot of dependency versions used when this task started its current cycle.
    dep_versions_used: dict[str, int] = field(default_factory=dict)

    # Explicit stale marker from propagation. Integration also checks version mismatch.
    stale: bool = False

    # True means increment version when this rework cycle is completed.
    bump_version_on_rework_done: bool = True

    def __post_init__(self) -> None:
        if self.remaining_work <= 0:
            self.remaining_work = self.base_effort


@dataclass
class CascadeRecord:
    run_id: int
    t: int
    root_task_id: str
    mode: str
    size: int


@dataclass
class ProjectState:
    run_id: int
    mode: Mode
    agents: dict[str, Agent]
    tasks: dict[str, Task]
    mode_history: list[tuple[int, str]] = field(default_factory=list)
    messages_sent: int = 0
    sync_minutes: float = 0.0
    coordination_cost: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)
    cascades: list[CascadeRecord] = field(default_factory=list)
    rework_events_per_tick: list[int] = field(default_factory=list)
    signal_events_per_tick: list[int] = field(default_factory=list)
    noise_events_per_tick: list[int] = field(default_factory=list)
    exogenous_signal_per_tick: list[int] = field(default_factory=list)
    exogenous_noise_per_tick: list[int] = field(default_factory=list)
    coordination_backlog: float = 0.0
    demand_per_tick: list[float] = field(default_factory=list)
    supply_per_tick: list[float] = field(default_factory=list)
    gap_per_tick: list[float] = field(default_factory=list)
    high_need_per_tick: list[int] = field(default_factory=list)
    escalated_per_tick: list[int] = field(default_factory=list)
    false_alarm_per_tick: list[int] = field(default_factory=list)
    missed_escalation_per_tick: list[int] = field(default_factory=list)
    tasks_done_per_tick: list[int] = field(default_factory=list)

    def all_done(self) -> bool:
        return all(t.state == TaskState.DONE for t in self.tasks.values())

    def done_count(self) -> int:
        return sum(1 for t in self.tasks.values() if t.state == TaskState.DONE)


@dataclass
class Config:
    seed: int = 42
    n_runs: int = 100
    ticks_per_run: int = 500
    team_size: int = 4
    integration_check_interval: int = 1
    rework_effort_fraction: float = 0.4
    retest_effort_fraction: float = 0.25

    task_graph: dict[str, Any] = field(default_factory=dict)
    task_effort_distribution: dict[str, Any] = field(default_factory=dict)
    agent_distributions: dict[str, Any] = field(default_factory=dict)
    propagation: dict[str, Any] = field(default_factory=dict)
    mode_effects: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    costs: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def policy_type(self) -> str:
        return str(self.policy.get("type", "async_only"))

    @property
    def coupling_strength(self) -> float:
        p = self.propagation
        if "coupling_strength" in p:
            return float(p["coupling_strength"])
        if "coupling_distribution" in p and isinstance(p["coupling_distribution"], dict):
            return float(p["coupling_distribution"].get("value", 0.6))
        return 0.6
