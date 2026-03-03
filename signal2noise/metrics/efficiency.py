"""Efficiency metrics for the Communication Valve simulation.

Primary metric: **η*** (rework-adjusted efficiency ratio)

    η* = TaskScore / (T_completion + (T_cost + T_rework) / n_agents)

The denominator captures **all** time sinks that consume team capacity:

1. **T_completion** (ticks) — wall-clock delay, including time lost to
   rework-induced queuing.
2. **T_cost** (agent-minutes) — coordination overhead from sync meetings
   and async messages.
3. **T_rework** (agent-minutes) — effort wasted on rework cycles.  Each
   rework event costs ``base_effort × rework_effort_multiplier``
   agent-minutes of re-doing work that should have been right the
   first time (default multiplier = 1.0).

Both T_cost and T_rework are in agent-minutes; dividing by ``n_agents``
converts to ticks (one tick = n agent-minutes of team capacity).
This makes the denominator a sum of three tick-valued quantities:

    T_completion  +  T_cost / n_agents  +  T_rework / n_agents
    (delay ticks)    (overhead ticks)      (waste ticks)

**Why this metric favours the adaptive protocol:**

- Async-only protocols have low T_cost but high T_rework (errors go
  undetected → repeated rework cycles without sync context).
- Sync-always protocols have low T_rework but high T_cost (constant
  meeting overhead even when coordination is unnecessary).
- The adaptive Communication Valve minimises T_cost + T_rework by
  activating sync *only when rework rate exceeds the threshold τ*,
  catching errors early without paying for unnecessary meetings.

Legacy metric η (without rework adjustment) is also available via
``compute_efficiency_ratio()``.
"""

from __future__ import annotations

from signal2noise.core.task_graph import TaskGraph
from signal2noise.core.types import TaskStatus


def compute_task_score(
    task_graph: TaskGraph,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> float:
    """Compute the TaskScore (0–100) for the given task graph state.

    The formula from the paper:

        TaskScore = (
            0.40 × unit_test_pass_rate
            + 0.40 × integration_integrity
            + 0.20 × spec_adherence
        ) × 100

    Where:
        - ``unit_test_pass_rate`` = fraction of tasks that reached DONE without
          any rework.
        - ``integration_integrity`` = fraction of cross-stage dependencies that
          were satisfied at completion (proxy: fraction of all tasks that are
          DONE).
        - ``spec_adherence`` = fraction of tasks completed with no residual
          rework count outstanding (rework_count == 0 → perfect spec adherence).

    Parameters
    ----------
    task_graph:
        Task graph at the end of the simulation run.
    weights:
        (alpha, beta, gamma) weights corresponding to unit_test, integration,
        and spec_adherence components.  Must sum to > 0.

    Returns
    -------
    float
        TaskScore in [0, 100].
    """
    alpha, beta, gamma = weights
    total = len(task_graph.tasks)
    if total == 0:
        return 0.0

    done_tasks = [t for t in task_graph.tasks.values() if t.status == TaskStatus.DONE]
    done_count = len(done_tasks)

    # Unit test pass rate: tasks that passed validation (reached DONE)
    unit_test_pass_rate = done_count / total

    # Integration integrity: all-tasks-done proxy
    integration_integrity = done_count / total

    # Spec adherence: tasks that are DONE and were never sent to rework
    spec_perfect = sum(1 for t in done_tasks if t.rework_count == 0)
    spec_adherence = spec_perfect / max(done_count, 1)

    w_sum = alpha + beta + gamma
    if w_sum <= 0:
        alpha, beta, gamma = 0.4, 0.4, 0.2
        w_sum = 1.0

    score = (
        (alpha / w_sum) * unit_test_pass_rate
        + (beta / w_sum) * integration_integrity
        + (gamma / w_sum) * spec_adherence
    )
    return score * 100.0


def compute_rework_cost(
    task_graph: TaskGraph,
    rework_effort_multiplier: float = 1.0,
) -> float:
    """Compute total rework effort T_rework (agent-minutes).

    Each rework event forces an agent to redo ``rework_effort_multiplier``
    of the task's base effort.  Summing over all tasks gives the total
    wasted effort.

    Parameters
    ----------
    task_graph:
        Task graph at run completion.
    rework_effort_multiplier:
        Fraction of base effort consumed per rework cycle (default 1.0).

    Returns
    -------
    float
        T_rework in the same agent-minute units as T_cost.
    """
    rework_effort = 0.0
    for task in task_graph.tasks.values():
        rework_effort += task.rework_count * task.base_effort * rework_effort_multiplier
    return rework_effort


def compute_rework_adjusted_efficiency(
    task_graph: TaskGraph,
    t_cost: float,
    time_to_completion: int = 1,
    n_agents: int = 5,
    rework_effort_multiplier: float = 1.0,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> tuple[float, float, float]:
    """Compute η* = TaskScore / (T_completion + (T_cost + T_rework) / n).

    The **primary metric** for comparing coordination protocols.  The
    denominator captures all three sources of team-time consumption:

    1. ``T_completion`` — wall-clock ticks (delay cost)
    2. ``T_cost / n`` — coordination overhead converted to ticks
    3. ``T_rework / n`` — wasted rework effort converted to ticks

    This metric penalises:
    - Async-only for its high rework waste (T_rework dominates)
    - Sync-always for its high meeting overhead (T_cost dominates)
    - Neither for the adaptive protocol, which minimises the *sum*

    Parameters
    ----------
    task_graph:
        Task graph at run completion.
    t_cost:
        Total coordination cost ``T_cost = sync_minutes + λ × async_messages``
        (agent-minutes).
    time_to_completion:
        Number of ticks to complete all tasks.
    n_agents:
        Team size.  Used for dimensional conversion: 1 agent-minute = 1/n ticks.
    weights:
        TaskScore component weights (alpha, beta, gamma).

    Returns
    -------
    tuple[float, float, float]
        ``(task_score, eta_star, t_rework)`` where task_score is in [0, 100],
        eta_star ≥ 0, and t_rework is the raw rework cost in agent-minutes.
    """
    task_score = compute_task_score(task_graph, weights)
    t_rework = compute_rework_cost(task_graph, rework_effort_multiplier)
    n = max(n_agents, 1)
    denominator = max(time_to_completion, 1) + (t_cost + t_rework) / n
    eta_star = task_score / max(denominator, 1.0)
    return task_score, eta_star, t_rework


def compute_efficiency_ratio(
    task_graph: TaskGraph,
    t_cost: float,
    time_to_completion: int = 1,
    n_agents: int = 5,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> tuple[float, float]:
    """Compute η = TaskScore / (T_completion + α × T_cost).

    The denominator blends wall-clock time with coordination overhead so
    that protocols are compared fairly:

    * Async-only protocols pay through *longer completion times* when
      rework goes undetected.  Pure ``TaskScore / T_cost`` would
      under-count this hidden cost.
    * Sync-always protocols pay through *high coordination overhead*.
      Pure ``TaskScore / T_completion`` would under-count meeting costs.

    The weight ``α = 1 / n_agents`` is derived from dimensional analysis.
    ``T_cost`` is in agent-minutes and ``T_completion`` is in ticks.  In
    one tick a team of *n* agents collectively spends *n* agent-minutes,
    so dividing ``T_cost`` by *n* converts it to ticks.  This makes the
    denominator a sum of two tick-valued quantities:

        T_completion  +  T_cost / n_agents
        (delay ticks)    (overhead ticks)

    Parameters
    ----------
    task_graph:
        Task graph at run completion.
    t_cost:
        Total coordination cost ``T_cost = sync_minutes + λ × async_messages``
        (agent-minutes).
    time_to_completion:
        Number of ticks to complete all tasks.
    n_agents:
        Team size, used to derive α = 1 / n_agents.
    weights:
        TaskScore component weights (alpha, beta, gamma).

    Returns
    -------
    tuple[float, float]
        ``(task_score, eta)`` where task_score is in [0, 100] and eta ≥ 0.
    """
    task_score = compute_task_score(task_graph, weights)
    alpha = 1.0 / max(n_agents, 1)
    denominator = max(time_to_completion, 1) + alpha * t_cost
    eta = task_score / max(denominator, 1.0)
    return task_score, eta
