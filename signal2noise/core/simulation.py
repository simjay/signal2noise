"""Main simulation loop: tick-based scheduler, orchestrates all phases."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

import numpy as np

from signal2noise.core.agent import Agent
from signal2noise.core.channel import AsyncChannel, SyncChannel
from signal2noise.core.task import Task
from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import (
    AgentState,
    AllocationPolicy,
    RunSummary,
    TaskStatus,
    TickSnapshot,
)

if TYPE_CHECKING:
    from signal2noise.protocols.base import Protocol


# ---------------------------------------------------------------------------
# Simulation configuration
# ---------------------------------------------------------------------------

@dataclass
class SimulationConfig:
    """Complete configuration for a single simulation run.

    All parameters have defaults that match the paper's baseline experiment.
    """

    # Task graph
    num_tasks: int = 15
    graph_topology: Literal["linear", "tree", "diamond"] = "linear"
    complexity_distribution: Literal["uniform", "normal", "bimodal"] = "uniform"
    complexity_mean: float = 0.5
    complexity_std: float = 0.15

    # Agents
    num_agents: int = 3
    skill_distribution: Literal["uniform", "normal", "bimodal"] = "uniform"
    skill_mean: float = 0.6
    skill_std: float = 0.15

    # Protocol
    protocol: Literal["async_only", "sync_always", "adaptive"] = "adaptive"

    # Adaptive protocol parameters (Group C)
    tau: float = 0.3

    # Sync-always parameters (Group B)
    s_min: float = 0.2

    # Error model
    base_error_rate: float = 0.15
    # Cognitive load penalty: how much fatigue amplifies error rates.
    # At cognitive_load=1.0, errors are multiplied by (1 + penalty) = 3.5x.
    # This reflects research showing that sustained high cognitive load
    # severely degrades decision quality (Kahneman 2011, Hockey 1997).
    cognitive_load_penalty: float = 2.5

    # Exogenous perturbation (signal vs noise from simulation.md)
    p_signal_change: float = 0.10  # per-tick prob. of external change → rework
    p_noise_change: float = 0.15   # per-tick prob. of churn → cognitive load

    # Rework propagation
    p_cascade: float = 0.3
    max_cascade_depth: int = 2

    # Cognitive load
    # Sync meetings are cognitively expensive: context switching,
    # active listening, debate, and decision-making all consume
    # attentional resources that deplete over sustained use.
    sync_load_rate: float = 0.40
    async_load_rate: float = 0.05
    recovery_rate: float = 0.03
    natural_decay: float = 0.01

    # Communication
    lambda_async: float = 0.2
    sync_error_reduction: float = 0.4

    # Rework cost: fraction of base_effort required per rework cycle.
    # Default 1.0 means rework costs the same as the original work —
    # the agent must understand what broke, trace the root cause, fix
    # it, and re-validate.  This is consistent with empirical data
    # from software engineering (Boehm & Basili 2001) showing rework
    # often matches or exceeds original development effort.
    rework_effort_multiplier: float = 1.0

    # Simulation
    max_ticks: int = 200
    random_seed: Optional[int] = None


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class Simulation:
    """Discrete-time, tick-based ABM simulation.

    Parameters
    ----------
    config:
        Full configuration for this run.

    Examples
    --------
    >>> from signal2noise.core.simulation import Simulation, SimulationConfig
    >>> cfg = SimulationConfig(protocol="async_only", num_tasks=10, random_seed=42)
    >>> result = Simulation(cfg).run()
    >>> result.ticket_bounce_rate  # doctest: +SKIP
    0.2
    """

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self._rng = np.random.default_rng(config.random_seed)

        # Build agents
        self.agents: list[Agent] = _build_agents(config, self._rng)

        # Build task graph
        self.task_graph: TaskGraph = _build_task_graph(config, self._rng)

        # Communication channels (shared)
        self.async_channel = AsyncChannel(lambda_cost=config.lambda_async)
        self.sync_channel = SyncChannel(error_reduction=config.sync_error_reduction)

        # Protocol (set after construction via _attach_protocol or in run())
        self._protocol: Optional["Protocol"] = None

    def _attach_protocol(self) -> None:
        """Import and instantiate the protocol specified in config."""
        from signal2noise.protocols.async_only import AsyncOnlyProtocol
        from signal2noise.protocols.sync_always import SyncAlwaysProtocol
        from signal2noise.protocols.adaptive import AdaptiveProtocol

        proto_map = {
            "async_only": lambda: AsyncOnlyProtocol(),
            "sync_always": lambda: SyncAlwaysProtocol(s_min=self.config.s_min),
            "adaptive": lambda: AdaptiveProtocol(tau=self.config.tau),
        }
        factory = proto_map.get(self.config.protocol)
        if factory is None:
            raise ValueError(f"Unknown protocol: {self.config.protocol!r}")
        self._protocol = factory()

    def run(self) -> RunSummary:
        """Execute the simulation and return aggregate results.

        Returns
        -------
        RunSummary
            Aggregate metrics and tick-level snapshots.
        """
        self._attach_protocol()
        assert self._protocol is not None

        from signal2noise.demand.generator import DemandGenerator
        from signal2noise.demand.rework import ReworkEngine
        from signal2noise.supply.allocator import Allocator
        from signal2noise.supply.cognitive_load import CognitiveLoadModel
        from signal2noise.metrics.collectors import TickCollector

        demand_gen = DemandGenerator()
        rework_engine = ReworkEngine(
            p_cascade=self.config.p_cascade,
            max_cascade_depth=self.config.max_cascade_depth,
            rework_effort_multiplier=self.config.rework_effort_multiplier,
            rng=self._rng,
        )
        allocator = Allocator()
        cog_model = CognitiveLoadModel(
            sync_load_rate=self.config.sync_load_rate,
            async_load_rate=self.config.async_load_rate,
            recovery_rate=self.config.recovery_rate,
            natural_decay=self.config.natural_decay,
        )
        collector = TickCollector()

        cfg = self.config
        completion_tick = cfg.max_ticks

        # Track cascade depths
        cascade_depths: list[int] = []

        for tick in range(cfg.max_ticks):
            # --- PHASE 0: EXOGENOUS PERTURBATION ---
            # External changes (requirement shifts, upstream API breaks, etc.)
            # can force in-flight tasks into rework.  This is the "signal"
            # that the Communication Valve must detect.
            signal_rework = _apply_exogenous_perturbation(
                self.task_graph, cfg, self._rng,
            )

            # Noise: communication churn adds cognitive load to all agents
            if self._rng.random() < cfg.p_noise_change:
                for agent in self.agents:
                    agent.cognitive_load = min(
                        1.0, agent.cognitive_load + 0.03
                    )

            # --- PHASE 1: DEMAND GENERATION ---
            new_demand = demand_gen.resolve(self.task_graph, tick)
            rework_demand, depths = rework_engine.propagate(self.task_graph, tick)
            cascade_depths.extend(depths)
            rework_demand += signal_rework

            total_demand = new_demand + rework_demand
            rework_rate = rework_demand / max(total_demand, 1)

            # --- PHASE 2: PROTOCOL DECISION ---
            alloc_policy: AllocationPolicy = self._protocol.decide(
                rework_rate, self.agents, tick
            )

            # Update sync channel state
            sync_active = any(s > 0 for _, s, _ in alloc_policy.values())
            if sync_active:
                self.sync_channel.start_session()
            else:
                self.sync_channel.end_session()
            self.sync_channel.record_tick()

            # --- PHASE 3: SUPPLY ALLOCATION ---
            allocator.apply(self.agents, alloc_policy)

            # --- PHASE 4: EXECUTION ---
            messages_this_tick = 0
            for agent in self.agents:
                msgs = _agent_execute(
                    agent, tick, self.task_graph, self.async_channel, self.sync_channel, cfg, self._rng, sync_active
                )
                messages_this_tick += msgs

            # --- PHASE 5: COGNITIVE LOAD UPDATE ---
            cog_model.update(self.agents)

            # --- PHASE 6: METRIC COLLECTION ---
            snapshot = TickSnapshot(
                tick=tick,
                rework_rate=rework_rate,
                new_demand=new_demand,
                rework_demand=rework_demand,
                total_demand=total_demand,
                sync_active=sync_active,
                tasks_done=len(self.task_graph.done_ids()),
                tasks_total=len(self.task_graph.tasks),
                agent_states={a.id: a.state for a in self.agents},
                agent_cognitive_loads={a.id: a.cognitive_load for a in self.agents},
                # Sync cost: sum of each agent's sync fraction (one tick at
                # fraction s_i costs s_i agent-minutes for agent i).
                sync_minutes_this_tick=sum(a.sync_fraction for a in self.agents),
                async_messages_this_tick=messages_this_tick,
            )
            collector.record(snapshot)

            # --- PHASE 7: TERMINATION CHECK ---
            if self.task_graph.all_complete():
                completion_tick = tick + 1
                break

        return _build_run_summary(
            config=cfg,
            collector=collector,
            completion_tick=completion_tick,
            async_channel=self.async_channel,
            sync_channel=self.sync_channel,
            task_graph=self.task_graph,
            cascade_depths=cascade_depths,
        )


# ---------------------------------------------------------------------------
# Builder helpers (private)
# ---------------------------------------------------------------------------

def _build_agents(config: SimulationConfig, rng: np.random.Generator) -> list[Agent]:
    """Construct the agent list from config."""
    skills: np.ndarray
    if config.skill_distribution == "uniform":
        low = max(0.01, config.skill_mean - config.skill_std * 1.732)
        high = min(1.0, config.skill_mean + config.skill_std * 1.732)
        skills = rng.uniform(low, high, size=config.num_agents)
    elif config.skill_distribution == "normal":
        skills = np.clip(
            rng.normal(config.skill_mean, config.skill_std, size=config.num_agents),
            0.01, 1.0,
        )
    elif config.skill_distribution == "bimodal":
        mask = rng.random(size=config.num_agents) < 0.5
        skills = np.clip(
            np.where(
                mask,
                rng.normal(config.skill_mean - 2 * config.skill_std, config.skill_std, size=config.num_agents),
                rng.normal(config.skill_mean + 2 * config.skill_std, config.skill_std, size=config.num_agents),
            ),
            0.01, 1.0,
        )
    else:
        raise ValueError(f"Unknown skill_distribution: {config.skill_distribution!r}")

    return [
        Agent(id=f"A{i}", skill_level=float(skills[i]), position=i)
        for i in range(config.num_agents)
    ]


def _build_task_graph(config: SimulationConfig, rng: np.random.Generator) -> TaskGraph:
    """Construct the task graph from config."""
    kwargs = dict(
        n_tasks=config.num_tasks,
        complexity_distribution=config.complexity_distribution,
        complexity_mean=config.complexity_mean,
        complexity_std=config.complexity_std,
        rng=rng,
    )
    if config.graph_topology == "linear":
        return TaskGraph.linear(**kwargs)
    if config.graph_topology == "tree":
        return TaskGraph.tree(**kwargs)
    if config.graph_topology == "diamond":
        return TaskGraph.diamond(**kwargs)
    raise ValueError(f"Unknown graph_topology: {config.graph_topology!r}")


def _apply_exogenous_perturbation(
    task_graph: TaskGraph,
    cfg: SimulationConfig,
    rng: np.random.Generator,
) -> int:
    """Apply random external changes that force in-flight tasks into rework.

    Models requirement shifts, upstream API breaks, or spec changes —
    the real-world "signal" that drives coordination need.  Each
    in-progress task has ``p_signal_change`` probability per tick of
    being hit.

    Returns the number of tasks pushed to rework.
    """
    rework_count = 0
    for task in task_graph.tasks.values():
        if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW):
            if rng.random() < cfg.p_signal_change:
                task.status = TaskStatus.REWORK
                task.rework_count += 1
                task.remaining_effort = task.base_effort * cfg.rework_effort_multiplier
                rework_count += 1
    return rework_count


def _agent_execute(
    agent: Agent,
    tick: int,
    task_graph: TaskGraph,
    async_channel: AsyncChannel,
    sync_channel: SyncChannel,
    cfg: SimulationConfig,
    rng: np.random.Generator,
    tick_sync_active: bool = False,
) -> int:
    """Execute one tick's work for *agent*.  Returns async messages sent."""
    messages_sent = 0

    if agent.state == AgentState.IDLE:
        return 0

    # Find an assigned task for this agent
    task = _pick_task(agent, task_graph)
    if task is None:
        agent.state = AgentState.IDLE
        return 0

    # Sync error reduction applies when the protocol has activated sync
    # for this tick (not just when the agent's dominant state is IN_SYNC).
    # An agent with w=0.7, s=0.3 still benefits from the meeting.
    agent_has_sync = tick_sync_active and agent.sync_fraction > 0

    if agent.state == AgentState.IN_SYNC:
        # Synchronous session: work proceeds with error reduction
        _do_work(agent, task, cfg, rng, sync_active=True)

    elif agent.state == AgentState.READING_ASYNC:
        # Async reading: deliver messages but no output produced
        async_channel.deliver()

    elif agent.state == AgentState.WORKING:
        # Productive work — sync error reduction still applies if
        # the agent is participating in a sync session this tick
        _do_work(agent, task, cfg, rng, sync_active=agent_has_sync)

    # Async communication overhead: every agent with a non-zero async
    # fraction generates messages proportional to that fraction.
    # This represents the overhead of reading/writing on Slack, Jira,
    # email etc., regardless of the dominant activity state.
    if agent.async_fraction > 0:
        messages_sent += 1

    return messages_sent


def _pick_task(agent: Agent, task_graph: TaskGraph) -> Optional[Task]:
    """Find the highest-priority task assigned to this agent."""
    # Prefer REWORK > IN_PROGRESS > READY
    for status in (TaskStatus.REWORK, TaskStatus.IN_PROGRESS, TaskStatus.READY):
        for task in task_graph.tasks.values():
            if task.assigned_agent == agent.id and task.status == status:
                return task

    # Assign an unassigned READY task if available
    satisfiable = task_graph.satisfiable_ids()
    for task in task_graph.tasks.values():
        if task.assigned_agent is None and task.status == TaskStatus.BLOCKED:
            if task.dependency_set.issubset(satisfiable):
                task.status = TaskStatus.READY
        if task.assigned_agent is None and task.status == TaskStatus.READY:
            task.assigned_agent = agent.id
            task.status = TaskStatus.IN_PROGRESS
            return task

    return None


def _do_work(
    agent: Agent,
    task: Task,
    cfg: SimulationConfig,
    rng: np.random.Generator,
    sync_active: bool,
) -> None:
    """Reduce task remaining effort and handle completion.

    Error model: when a task's effort is exhausted, it undergoes
    validation.  The base error rate is amplified by task complexity,
    agent skill, and cognitive load.

    Key asymmetry that drives the hypothesis:
    - **First-pass validation** uses the base error rate — sync
      provides a modest reduction.
    - **Rework resolution** is harder without coordination: the agent
      must understand *what* went wrong, which requires context that
      only sync meetings efficiently provide.  Without sync the error
      rate is amplified by ``rework_async_penalty`` (×1.5 by default).
      With sync, the high-bandwidth channel reduces errors by
      ``sync_error_reduction`` (40 %).
    """
    # Work rate is modulated by the agent's work_fraction
    work_rate = agent.work_fraction * agent.skill_level
    task.remaining_effort = max(0.0, task.remaining_effort - work_rate)

    if task.remaining_effort > 0:
        return

    # Rework-resolution difficulty multiplier when async-only.
    # Fixing a bug without context about what broke is substantially
    # harder — the agent must guess at the root cause.
    REWORK_ASYNC_PENALTY = 2.0

    # Task effort exhausted — run validation
    if task.status == TaskStatus.IN_PROGRESS:
        task.status = TaskStatus.IN_REVIEW
        p_error = agent.effective_error_rate(
            task.complexity, cfg.base_error_rate, cfg.cognitive_load_penalty
        )
        if sync_active:
            p_error *= (1.0 - cfg.sync_error_reduction)
        if rng.random() < p_error:
            # Validation failure → rework
            task.status = TaskStatus.REWORK
            task.rework_count += 1
            task.remaining_effort = task.base_effort * cfg.rework_effort_multiplier
        else:
            task.status = TaskStatus.DONE

    elif task.status == TaskStatus.REWORK:
        # Re-validate after rework.
        # Rework resolution is harder without sync context.
        p_error = agent.effective_error_rate(
            task.complexity, cfg.base_error_rate, cfg.cognitive_load_penalty
        )
        if sync_active:
            # Sync provides the context needed to fix the root cause
            p_error *= (1.0 - cfg.sync_error_reduction)
        else:
            # Without sync, fixing rework is harder — agent lacks context
            p_error = min(1.0, p_error * REWORK_ASYNC_PENALTY)
        if rng.random() < p_error:
            task.rework_count += 1
            task.remaining_effort = task.base_effort * cfg.rework_effort_multiplier
        else:
            task.status = TaskStatus.DONE


def _build_run_summary(
    config: SimulationConfig,
    collector: "TickCollector",
    completion_tick: int,
    async_channel: AsyncChannel,
    sync_channel: SyncChannel,
    task_graph: TaskGraph,
    cascade_depths: list[int],
) -> RunSummary:
    """Aggregate per-tick snapshots into a RunSummary."""
    from signal2noise.metrics.collectors import TickCollector
    from signal2noise.metrics.efficiency import compute_efficiency_ratio
    from signal2noise.metrics.summary import aggregate_summary

    snapshots = collector.snapshots
    total_tasks = len(task_graph.tasks)
    done_count = sum(1 for t in task_graph.tasks.values() if t.status == TaskStatus.DONE)
    total_rework = sum(t.rework_count for t in task_graph.tasks.values())

    ticket_bounce_rate = total_rework / max(total_tasks, 1)
    throughput = done_count / max(completion_tick, 1)

    # Cognitive load variance at completion
    final_loads = [
        snap.agent_cognitive_loads
        for snap in snapshots[-3:] if snap.agent_cognitive_loads
    ]
    if final_loads:
        last_loads = list(final_loads[-1].values())
        cog_variance = float(np.var(last_loads)) if len(last_loads) > 1 else 0.0
    else:
        cog_variance = 0.0

    mean_cascade_depth = (
        float(np.mean(cascade_depths)) if cascade_depths else 0.0
    )

    total_ticks = len(snapshots)
    sync_ticks = sum(1 for s in snapshots if s.sync_active)
    channel_util = sync_ticks / max(total_ticks, 1)

    demand_values = [s.total_demand for s in snapshots]
    demand_supply_ratio = float(np.mean(demand_values)) if demand_values else 0.0

    # Coordination cost
    sync_minutes = sum(s.sync_minutes_this_tick for s in snapshots)
    total_async_msgs = sum(s.async_messages_this_tick for s in snapshots)
    t_cost = sync_minutes + config.lambda_async * total_async_msgs

    # Task score and efficiency (legacy η)
    task_score, eta = compute_efficiency_ratio(
        task_graph, t_cost,
        time_to_completion=completion_tick,
        n_agents=config.num_agents,
    )

    # Rework-adjusted efficiency (primary η*)
    from signal2noise.metrics.efficiency import compute_rework_adjusted_efficiency
    _, eta_star, t_rework = compute_rework_adjusted_efficiency(
        task_graph, t_cost,
        time_to_completion=completion_tick,
        n_agents=config.num_agents,
        rework_effort_multiplier=config.rework_effort_multiplier,
    )

    return RunSummary(
        ticket_bounce_rate=ticket_bounce_rate,
        efficiency_ratio=eta,
        task_score=task_score,
        total_coordination_cost=t_cost,
        rework_adjusted_eta=eta_star,
        total_rework_cost=t_rework,
        time_to_completion=completion_tick,
        throughput=throughput,
        cognitive_load_variance=cog_variance,
        mean_rework_cascade_depth=mean_cascade_depth,
        channel_utilization_ratio=channel_util,
        demand_supply_ratio_mean=demand_supply_ratio,
        tick_snapshots=snapshots,
    )


# Re-export SimulationConfig for convenience
__all__ = ["Simulation", "SimulationConfig"]
