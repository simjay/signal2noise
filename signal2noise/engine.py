from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from typing import Any

from signal2noise.entities import Agent, CascadeRecord, Config, Mode, ProjectState, Task, TaskState
from signal2noise.graphs import assign_couplings, generate_graph
from signal2noise.policies import build_policy


def sample_distribution(spec: dict[str, Any], rng: random.Random, default: float) -> float:
    if not spec:
        return default
    kind = str(spec.get("kind", "fixed"))
    if kind == "fixed":
        return float(spec.get("value", default))
    if kind == "uniform":
        return float(rng.uniform(float(spec.get("low", default)), float(spec.get("high", default))))
    if kind == "normal":
        return float(max(0.0, rng.gauss(float(spec.get("mean", default)), float(spec.get("sigma", 0.1)))))
    if kind == "lognormal":
        mean = float(spec.get("mean", math.log(max(default, 1e-6))))
        sigma = float(spec.get("sigma", 0.25))
        return float(max(0.0, rng.lognormvariate(mean, sigma)))
    if kind == "beta":
        a = float(spec.get("a", 2.0))
        b = float(spec.get("b", 2.0))
        scale = float(spec.get("scale", 1.0))
        return float(rng.betavariate(a, b) * scale)
    raise ValueError(f"Unsupported distribution kind: {kind}")


def mode_value(mode: Mode, async_value: float, sync_value: float) -> float:
    return async_value if mode == Mode.ASYNC else sync_value


def invalidate_probability(base_propagation: float, coupling: float, misalignment_factor: float) -> float:
    return max(0.0, min(1.0, base_propagation * coupling * misalignment_factor))


def _is_signal_rework_reason(reason: str) -> bool:
    return reason in {"invalidated", "stale_dependency", "exogenous_change"}


def log_event(
    project: ProjectState,
    t: int,
    event_type: str,
    task_id: str = "",
    agent_id: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    project.events.append(
        {
            "run_id": project.run_id,
            "t": t,
            "event_type": event_type,
            "task_id": task_id,
            "agent_id": agent_id,
            "mode": project.mode.value,
            "meta_json": json.dumps(meta or {}, sort_keys=True),
        }
    )


def build_agents(cfg: Config, rng: random.Random) -> dict[str, Agent]:
    ad = cfg.agent_distributions
    out: dict[str, Agent] = {}
    for i in range(cfg.team_size):
        aid = f"A{i}"
        out[aid] = Agent(
            id=aid,
            skill_speed=sample_distribution(ad.get("skill_speed", {}), rng, default=1.0),
            defect_rate=sample_distribution(ad.get("defect_rate", {}), rng, default=0.08),
            clarification_need=sample_distribution(ad.get("clarification_need", {}), rng, default=0.12),
            response_delay_async=sample_distribution(ad.get("response_delay_async", {}), rng, default=3.0),
            response_delay_sync=sample_distribution(ad.get("response_delay_sync", {}), rng, default=0.5),
            cost_per_sync_minute=sample_distribution(
                ad.get("cost_per_sync_minute", {}),
                rng,
                default=float(cfg.costs.get("cost_per_sync_minute", 1.0)),
            ),
            cost_per_message=sample_distribution(
                ad.get("cost_per_message", {}),
                rng,
                default=float(cfg.costs.get("cost_per_message", 0.05)),
            ),
        )
    return out


def build_tasks(cfg: Config, agents: dict[str, Agent], rng: random.Random) -> dict[str, Task]:
    g = generate_graph(cfg.task_graph, rng)
    couplings = assign_couplings(g["edges"], cfg.propagation, rng)

    owners = list(agents.keys())
    td = cfg.task_effort_distribution
    tasks: dict[str, Task] = {}
    for i in range(g["n_tasks"]):
        tid = f"T{i}"
        task = Task(
            id=tid,
            base_effort=max(0.1, sample_distribution(td, rng, default=8.0)),
            owner_agent_id=owners[i % len(owners)],
            deps=list(g["deps"][tid]),
            dependents=list(g["dependents"][tid]),
        )
        task.coupling_to_dep = {dep: float(couplings.get((tid, dep), 0.0)) for dep in task.dependents}
        tasks[tid] = task
    return tasks


def dep_versions_snapshot(task: Task, tasks: dict[str, Task]) -> dict[str, int]:
    return {d: tasks[d].version for d in task.deps}


def deps_allow_start(task: Task, tasks: dict[str, Task]) -> bool:
    return all(tasks[d].state in (TaskState.READY_FOR_TEST, TaskState.DONE) for d in task.deps)


def task_is_stale(task: Task, tasks: dict[str, Task]) -> bool:
    if task.stale:
        return True
    for d in task.deps:
        used = task.dep_versions_used.get(d)
        if used is None:
            continue
        if tasks[d].version != used:
            return True
    return False


def pick_task_for_agent(agent_id: str, tasks: dict[str, Task]) -> Task | None:
    owned = [t for t in tasks.values() if t.owner_agent_id == agent_id]

    for state in (TaskState.REWORK, TaskState.IN_PROGRESS):
        for t in owned:
            if t.state == state:
                return t

    for t in owned:
        if t.state == TaskState.NOT_STARTED and deps_allow_start(t, tasks):
            return t

    return None


def _force_task_into_rework(
    task: Task,
    cfg: Config,
    project: ProjectState,
    t: int,
    reason: str,
    bump_version_on_done: bool,
) -> None:
    prev_state = task.state
    task.state = TaskState.REWORK
    task.rework_count += 1
    task.remaining_work = max(0.1, task.base_effort * cfg.rework_effort_fraction)
    task.pending_defect = False
    task.stale = reason == "invalidated" or reason == "stale_dependency"
    task.bump_version_on_rework_done = bump_version_on_done
    project.rework_events_per_tick[-1] += 1
    if _is_signal_rework_reason(reason):
        project.signal_events_per_tick[-1] += 1
    else:
        project.noise_events_per_tick[-1] += 1
    log_event(
        project,
        t,
        "TASK_BOUNCE",
        task_id=task.id,
        meta={"from_state": prev_state.value, "reason": reason},
    )
    log_event(project, t, "TASK_REWORK_START", task_id=task.id, meta={"reason": reason})


def propagate_change(
    project: ProjectState,
    root_task_id: str,
    t: int,
    cfg: Config,
    rng: random.Random,
    propagation_multiplier: float = 1.0,
) -> int:
    base_propagation = float(cfg.propagation.get("base_propagation", 0.35)) * max(0.0, propagation_multiplier)
    misalignment = mode_value(
        project.mode,
        async_value=float(cfg.mode_effects.get("misalignment_factor_async", 1.0)),
        sync_value=float(cfg.mode_effects.get("misalignment_factor_sync", 0.5)),
    )

    queue = [root_task_id]
    visited = {root_task_id}
    invalidated: set[str] = set()

    while queue:
        u = queue.pop(0)
        u_task = project.tasks[u]
        for v in u_task.dependents:
            if v in visited:
                continue
            p = invalidate_probability(base_propagation, float(u_task.coupling_to_dep.get(v, 0.0)), misalignment)
            if rng.random() >= p:
                continue

            v_task = project.tasks[v]
            # Only invalidate active/ready/done tasks. Not-started tasks will consume latest versions at start.
            if v_task.state == TaskState.NOT_STARTED:
                continue

            visited.add(v)
            queue.append(v)
            invalidated.add(v)

            v_task.stale = True
            log_event(project, t, "TASK_INVALIDATED", task_id=v, meta={"upstream": u, "root": root_task_id})

            if v_task.state != TaskState.REWORK:
                _force_task_into_rework(
                    task=v_task,
                    cfg=cfg,
                    project=project,
                    t=t,
                    reason="invalidated",
                    bump_version_on_done=True,
                )

    project.cascades.append(
        CascadeRecord(
            run_id=project.run_id,
            t=t,
            root_task_id=root_task_id,
            mode=project.mode.value,
            size=len(invalidated),
        )
    )
    return len(invalidated)


def apply_exogenous_changes(project: ProjectState, cfg: Config, t: int, rng: random.Random) -> list[tuple[str, float]]:
    p_signal_change = float(cfg.propagation.get("p_signal_change", 0.0))
    p_noise_change = float(cfg.propagation.get("p_noise_change", 0.0))
    signal_shock_multiplier = float(cfg.propagation.get("signal_shock_multiplier", 1.0))

    use_dual_process = p_signal_change > 0.0 or p_noise_change > 0.0
    signal_source = "exogenous_signal" if use_dual_process else "exogenous"

    # Backward compatible single-process setting.
    if not use_dual_process:
        p_change = float(cfg.propagation.get("p_change", 0.0))
        p_signal_change = p_change
        p_noise_change = 0.0
        signal_shock_multiplier = 1.0

    p_signal_change = max(0.0, min(1.0, p_signal_change))
    p_noise_change = max(0.0, min(1.0, p_noise_change))
    p_total = max(0.0, min(1.0, p_signal_change + p_noise_change))
    if p_total <= 0.0:
        return []

    roots: list[tuple[str, float]] = []
    for task in project.tasks.values():
        if task.state not in (TaskState.READY_FOR_TEST, TaskState.DONE):
            continue
        draw = rng.random()
        if draw >= p_total:
            continue

        is_signal = draw < p_signal_change
        if is_signal:
            task.version += 1
            log_event(project, t, "TASK_VERSION_CHANGE", task_id=task.id, meta={"source": signal_source})
            if task.state != TaskState.REWORK:
                _force_task_into_rework(
                    task=task,
                    cfg=cfg,
                    project=project,
                    t=t,
                    reason="exogenous_change",
                    bump_version_on_done=False,
                )
            roots.append((task.id, max(0.0, signal_shock_multiplier)))
        else:
            # Routine churn is modeled as low-impact coordination noise, not backward movement.
            project.noise_events_per_tick[-1] += 1
            project.messages_sent += 1
            log_event(project, t, "NOISE_CHURN", task_id=task.id, meta={"source": "exogenous_noise"})

    return roots


def compute_run_metrics(project: ProjectState, cfg: Config, makespan: int) -> dict[str, Any]:
    event_counts: dict[str, int] = defaultdict(int)
    for e in project.events:
        event_counts[e["event_type"]] += 1

    n_tasks = len(project.tasks)
    total_rework_events = event_counts["TASK_REWORK_START"]
    b_total = event_counts["TASK_BOUNCE"]
    passes = event_counts["TASK_TEST_PASS"]
    fails = event_counts["TASK_TEST_FAIL"]
    test_pass_rate = passes / max(1, passes + fails)

    stale_fails = 0
    defect_fails = 0
    for e in project.events:
        if e["event_type"] != "TASK_TEST_FAIL":
            continue
        try:
            meta = json.loads(e.get("meta_json", "{}"))
        except (TypeError, ValueError):
            meta = {}
        reason = str(meta.get("reason", ""))
        if reason == "stale":
            stale_fails += 1
        else:
            defect_fails += 1

    final_defects_remaining = sum(1 for t in project.tasks.values() if t.state != TaskState.DONE or t.pending_defect)
    tickets_processed = project.done_count()
    bounce_rate = b_total / max(1, tickets_processed)
    spec_adherence = 1.0 - final_defects_remaining / max(1, n_tasks)
    integration_failure_rate = stale_fails / max(1, passes + fails)

    mcfg = cfg.metrics if isinstance(cfg.metrics, dict) else {}
    w = mcfg.get("task_score_weights", {}) if isinstance(mcfg.get("task_score_weights", {}), dict) else {}
    alpha = float(w.get("unit_pass", 0.4))
    beta = float(w.get("integration", 0.4))
    gamma = float(w.get("spec", 0.2))
    w_sum = alpha + beta + gamma
    if w_sum <= 0:
        alpha, beta, gamma = 0.4, 0.4, 0.2
        w_sum = 1.0
    alpha, beta, gamma = alpha / w_sum, beta / w_sum, gamma / w_sum

    # Make system coherence more sensitive to integration failures and bounce churn.
    integration_failure_penalty = float(mcfg.get("integration_failure_penalty", 1.6))
    bounce_penalty_weight = float(mcfg.get("bounce_penalty_weight", 0.4))
    integration_integrity = max(
        0.0,
        1.0 - integration_failure_penalty * integration_failure_rate - bounce_penalty_weight * bounce_rate,
    )
    s_task = alpha * test_pass_rate + beta * integration_integrity + gamma * spec_adherence

    cascade_sizes = [c.size for c in project.cascades]
    avg_cascade = float(statistics.fmean(cascade_sizes)) if cascade_sizes else 0.0
    max_cascade = int(max(cascade_sizes)) if cascade_sizes else 0

    avg_msg_cost = statistics.fmean([a.cost_per_message for a in project.agents.values()])
    coordination_cost = project.coordination_cost + project.messages_sent * float(avg_msg_cost)
    cognitive_lambda = float(mcfg.get("cognitive_load_lambda", 0.5))
    sync_fatigue_multiplier = float(mcfg.get("sync_fatigue_multiplier", 1.0))
    sync_fatigue_exponent = float(mcfg.get("sync_fatigue_exponent", 1.0))
    # Report-style coordination load: fatigue-weighted sync event minutes + weighted async message load.
    sync_event_minutes = float(sum(project.escalated_per_tick))
    sync_load = sync_fatigue_multiplier * (sync_event_minutes ** sync_fatigue_exponent)
    c_load = sync_load + cognitive_lambda * float(project.messages_sent)
    c_load_per_ticket = c_load / max(1, tickets_processed)
    eta = s_task / (c_load_per_ticket + 1e-9)

    high_need_count = sum(project.high_need_per_tick)
    low_need_count = max(0, len(project.high_need_per_tick) - high_need_count)
    false_alarm_rate = sum(project.false_alarm_per_tick) / max(1, low_need_count)
    missed_escalation_rate = sum(project.missed_escalation_per_tick) / max(1, high_need_count)

    return {
        "run_id": project.run_id,
        "policy": cfg.policy_type,
        "coupling_strength": cfg.coupling_strength,
        "B_total": b_total,
        "tickets_processed": tickets_processed,
        "bounce_rate": bounce_rate,
        "S_task": s_task,
        "C_load": c_load,
        "C_load_per_ticket": c_load_per_ticket,
        "eta": eta,
        "false_alarm_rate": false_alarm_rate,
        "missed_escalation_rate": missed_escalation_rate,
        "total_rework_events": total_rework_events,
        "ticket_bounce_count": b_total,
        "avg_rework_per_task": total_rework_events / max(1, n_tasks),
        "avg_cascade_size": avg_cascade,
        "max_cascade_size": max_cascade,
        "makespan": makespan,
        "tasks_completed": project.done_count(),
        "sync_minutes": project.sync_minutes,
        "messages_sent": project.messages_sent,
        "coordination_cost": coordination_cost,
        "test_pass_rate": test_pass_rate,
        "integration_integrity": integration_integrity,
        "spec_adherence": spec_adherence,
        "final_defects_remaining": final_defects_remaining,
        "quality_score": s_task,
        "efficiency": eta,
        "demand_mean": float(statistics.fmean(project.demand_per_tick)) if project.demand_per_tick else 0.0,
        "supply_mean": float(statistics.fmean(project.supply_per_tick)) if project.supply_per_tick else 0.0,
        "gap_mean": float(statistics.fmean(project.gap_per_tick)) if project.gap_per_tick else 0.0,
    }


def _mode_at_t(history: list[tuple[int, str]], t: int) -> str:
    current = history[0][1]
    for ts, mode in history:
        if ts <= t:
            current = mode
        else:
            break
    return current


def run_single(
    cfg: Config,
    run_id: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(cfg.seed + run_id)
    agents = build_agents(cfg, rng)
    tasks = build_tasks(cfg, agents, rng)

    policy = build_policy(cfg.policy)
    project = ProjectState(run_id=run_id, mode=policy.initial_mode(), agents=agents, tasks=tasks)
    project.mode_history.append((0, project.mode.value))
    log_event(project, 0, "MODE_SWITCH", meta={"mode": project.mode.value, "reason": "init"})

    prod_async = float(cfg.mode_effects.get("productivity_factor_async", 1.0))
    prod_sync = float(cfg.mode_effects.get("productivity_factor_sync", 1.0))
    defect_async = float(cfg.mode_effects.get("defect_multiplier_async", 1.3))
    defect_sync = float(cfg.mode_effects.get("defect_multiplier_sync", 0.7))

    makespan = cfg.ticks_per_run
    for t in range(cfg.ticks_per_run):
        project.rework_events_per_tick.append(0)
        project.signal_events_per_tick.append(0)
        project.noise_events_per_tick.append(0)
        roots_to_propagate: list[tuple[str, float]] = []
        messages_before_tick = project.messages_sent

        maybe_mode = policy.step(project, t)
        if maybe_mode is not None and maybe_mode != project.mode:
            old = project.mode
            project.mode = maybe_mode
            project.mode_history.append((t, project.mode.value))
            log_event(project, t, "MODE_SWITCH", meta={"from": old.value, "to": project.mode.value})
            log_event(project, t, "SYNC_SESSION_START" if project.mode == Mode.SYNC else "SYNC_SESSION_END")

        # Periodic external requirement churn.
        roots_to_propagate.extend(apply_exogenous_changes(project, cfg, t, rng))

        for agent in project.agents.values():
            task = pick_task_for_agent(agent.id, project.tasks)
            if task is None:
                continue

            if task.state == TaskState.NOT_STARTED:
                task.state = TaskState.IN_PROGRESS
                task.dep_versions_used = dep_versions_snapshot(task, project.tasks)
                task.stale = False
                log_event(project, t, "TASK_START", task_id=task.id, agent_id=agent.id)

            if project.mode == Mode.ASYNC and rng.random() < agent.clarification_need:
                project.messages_sent += 1
                log_event(project, t, "MESSAGE_SENT", task_id=task.id, agent_id=agent.id, meta={"type": "CLARIFY"})

            work_rate = max(
                0.01,
                agent.skill_speed
                * mode_value(project.mode, prod_async, prod_sync)
                / (1.0 + 0.05 * mode_value(project.mode, agent.response_delay_async, agent.response_delay_sync)),
            )

            task.remaining_work -= work_rate
            log_event(
                project,
                t,
                "TASK_PROGRESS",
                task_id=task.id,
                agent_id=agent.id,
                meta={"remaining_work": max(task.remaining_work, 0.0)},
            )

            if task.remaining_work > 0:
                continue

            if task.state == TaskState.IN_PROGRESS:
                task.state = TaskState.READY_FOR_TEST
                p_defect = max(0.0, min(1.0, agent.defect_rate * mode_value(project.mode, defect_async, defect_sync)))
                task.pending_defect = rng.random() < p_defect
                log_event(project, t, "TASK_SUBMIT", task_id=task.id, agent_id=agent.id)

            elif task.state == TaskState.REWORK:
                if task.bump_version_on_rework_done:
                    task.version += 1
                    roots_to_propagate.append((task.id, 1.0))
                    log_event(project, t, "TASK_VERSION_CHANGE", task_id=task.id, meta={"source": "rework_done"})

                task.bump_version_on_rework_done = True
                task.stale = False
                task.pending_defect = False
                task.state = TaskState.IN_PROGRESS
                task.remaining_work = max(0.1, task.base_effort * cfg.retest_effort_fraction)
                task.dep_versions_used = dep_versions_snapshot(task, project.tasks)
                log_event(project, t, "TASK_REWORK_DONE", task_id=task.id, agent_id=agent.id)

        for root_task_id, propagation_multiplier in roots_to_propagate:
            propagate_change(
                project,
                root_task_id,
                t,
                cfg,
                rng,
                propagation_multiplier=propagation_multiplier,
            )

        if t % cfg.integration_check_interval == 0:
            for task in project.tasks.values():
                if task.state != TaskState.READY_FOR_TEST:
                    continue

                stale_dependency = task_is_stale(task, project.tasks)
                if task.pending_defect or stale_dependency:
                    log_event(
                        project,
                        t,
                        "TASK_TEST_FAIL",
                        task_id=task.id,
                        meta={"reason": "stale" if stale_dependency else "defect"},
                    )
                    _force_task_into_rework(
                        task=task,
                        cfg=cfg,
                        project=project,
                        t=t,
                        reason="stale_dependency" if stale_dependency else "test_fail",
                        bump_version_on_done=True,
                    )
                else:
                    task.state = TaskState.DONE
                    task.remaining_work = 0.0
                    task.stale = False
                    log_event(project, t, "TASK_TEST_PASS", task_id=task.id)

        if project.mode == Mode.SYNC:
            project.sync_minutes += float(len(project.agents))
            project.coordination_cost += sum(a.cost_per_sync_minute for a in project.agents.values())

        mcfg = cfg.metrics if isinstance(cfg.metrics, dict) else {}
        signal_weight = float(mcfg.get("demand_signal_weight", 1.0))
        noise_weight = float(mcfg.get("demand_noise_weight", 0.25))
        rework_weight = float(mcfg.get("demand_rework_weight", 0.5))
        sync_supply_base = float(mcfg.get("sync_supply_base", 2.0))
        async_supply_base = float(mcfg.get("async_supply_base", 0.8))
        message_supply_factor = float(mcfg.get("message_supply_factor", 0.05))
        gap_threshold = float(mcfg.get("gap_high_threshold", 1.0))

        signal_t = float(project.signal_events_per_tick[t])
        noise_t = float(project.noise_events_per_tick[t])
        active_rework = float(sum(1 for task in project.tasks.values() if task.state == TaskState.REWORK))
        demand_t = signal_weight * signal_t + noise_weight * noise_t + rework_weight * active_rework

        delta_messages = float(project.messages_sent - messages_before_tick)
        supply_base = sync_supply_base if project.mode == Mode.SYNC else async_supply_base
        supply_t = supply_base + message_supply_factor * delta_messages
        gap_t = demand_t - supply_t

        high_need = 1 if gap_t >= gap_threshold else 0
        escalated = 1 if project.mode == Mode.SYNC else 0
        false_alarm = 1 if (escalated == 1 and high_need == 0) else 0
        missed_escalation = 1 if (high_need == 1 and escalated == 0) else 0

        project.demand_per_tick.append(demand_t)
        project.supply_per_tick.append(supply_t)
        project.gap_per_tick.append(gap_t)
        project.high_need_per_tick.append(high_need)
        project.escalated_per_tick.append(escalated)
        project.false_alarm_per_tick.append(false_alarm)
        project.missed_escalation_per_tick.append(missed_escalation)

        project.tasks_done_per_tick.append(project.done_count())

        if project.all_done():
            makespan = t + 1
            break

    run_summary = compute_run_metrics(project, cfg, makespan)
    cascade_rows = [
        {
            "run_id": c.run_id,
            "t": c.t,
            "root_task_id": c.root_task_id,
            "mode": c.mode,
            "size": c.size,
            "policy": cfg.policy_type,
            "coupling_strength": cfg.coupling_strength,
        }
        for c in project.cascades
    ]
    timeseries_rows = [
        {
            "run_id": run_id,
            "policy": cfg.policy_type,
            "t": t,
            "mode": _mode_at_t(project.mode_history, t),
            "rework_events": project.rework_events_per_tick[t] if t < len(project.rework_events_per_tick) else 0,
            "signal_events": project.signal_events_per_tick[t] if t < len(project.signal_events_per_tick) else 0,
            "noise_events": project.noise_events_per_tick[t] if t < len(project.noise_events_per_tick) else 0,
            "demand": project.demand_per_tick[t] if t < len(project.demand_per_tick) else 0.0,
            "supply": project.supply_per_tick[t] if t < len(project.supply_per_tick) else 0.0,
            "gap": project.gap_per_tick[t] if t < len(project.gap_per_tick) else 0.0,
            "high_need": project.high_need_per_tick[t] if t < len(project.high_need_per_tick) else 0,
            "escalated": project.escalated_per_tick[t] if t < len(project.escalated_per_tick) else 0,
            "false_alarm": project.false_alarm_per_tick[t] if t < len(project.false_alarm_per_tick) else 0,
            "missed_escalation": (
                project.missed_escalation_per_tick[t] if t < len(project.missed_escalation_per_tick) else 0
            ),
            "tasks_done": project.tasks_done_per_tick[t] if t < len(project.tasks_done_per_tick) else 0,
        }
        for t in range(len(project.tasks_done_per_tick))
    ]
    return run_summary, project.events, cascade_rows, timeseries_rows


def run_many(cfg: Config) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    cascades: list[dict[str, Any]] = []
    timeseries: list[dict[str, Any]] = []

    for run_id in range(cfg.n_runs):
        r, e, c, ts = run_single(cfg, run_id)
        runs.append(r)
        events.extend(e)
        cascades.extend(c)
        timeseries.extend(ts)

    return runs, events, cascades, timeseries
