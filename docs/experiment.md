# Experiment Design

An agent-based model (ABM) simulating software teams under three
coordination protocols: async-only, sync-always, and an adaptive
"Communication Valve" triggered by rework rate. The experiment tests
whether the adaptive protocol achieves higher rework-adjusted efficiency
(eta*) and whether a phase transition occurs at a critical threshold
tau*.

Built for the CAS 2026 paper: *"Signal-to-Noise: Rework Propagation as a
Phase Transition Trigger in Socio-Technical Systems"*

See [dataset.md](dataset.md) for calibration data and
[results.md](results.md) for outcomes.

## Key Terms

| Term | Definition |
|------|-----------|
| **tick** | One discrete simulation time step. Abstract unit, not mapped to wall-clock hours. |
| **tau** | Rework-rate threshold that triggers the Communication Valve to switch from async to sync. |
| **tau*** | Critical tau at which a phase transition in eta* occurs. |
| **Communication Valve** | The adaptive protocol (Group C). Defaults to async; opens sync only when rework rate exceeds tau. |
| **agent-minute** | One agent working for one tick. A team of 5 produces 5 agent-minutes per tick. |
| **lambda** | Cost weight for async messages in T_cost (default 0.2). Converts message count to agent-minute equivalents. |

## Research Question

> Does a rework-triggered Communication Valve produce emergent efficiency
> advantages over both async-only and sync-always coordination, with a
> phase transition at critical threshold tau*?

The simulation compares three treatment groups:

| Group | Protocol | Mechanism |
|-------|----------|-----------|
| A | Async Only | Agents never hold sync meetings (control) |
| B | Sync Always | Agents maintain a persistent sync channel |
| C | Adaptive | Default async; sync swarm when rework rate > tau |

## Hypotheses

See [results.md](results.md) for evaluation.

- **H1**: Adaptive reduces rework vs async-only while maintaining
  throughput (bounce_rate_C < bounce_rate_A, throughput_C >= 90% of A).
- **H2**: Adaptive achieves the highest eta* (above both A and B).
- **H3**: A phase transition exists in `eta*(tau)` at critical `tau*`
  (max |d(eta*)/d(tau)| > 0.1).
- **H4**: Adaptive minimises total overhead `T_cost + T_rework` (below
  both A and B).

## ABM Formulation

### Simulation Loop at a Glance

Each tick proceeds through eight phases:

```
Perturbation -> Demand -> Protocol Decision -> Allocation -> Execution
    -> Cognitive Load Update -> Metric Collection -> Termination Check
```

### Agents

Each agent `i` has:

- **skill_level** in [0, 1]: competence at producing defect-free work
- **cognitive_load** in [0, 1]: accumulated fatigue (see Cognitive Load below)
- **time budget** `(w_i, s_i, a_i)`: fractions allocated to work, sync, and async (sum to 1.0)

The protocol sets the time budget each tick. Effective work rate is
`w_i * skill_level`.

### Task Graph

Work is organised as a directed acyclic graph (DAG) of `n` tasks, each
with:

- **complexity** in [0, 1]: difficulty, drawn from configurable distributions
- **base_effort**: nominal work units to complete (default 1.0)
- **dependency_set**: upstream tasks that must finish first
- **rework_count**: number of times the task has bounced back

Supported topologies: `linear` (chain), `tree` (fan-out), `diamond`
(fan-out then fan-in).

Task lifecycle:

```
BLOCKED --> READY --> IN_PROGRESS --> IN_REVIEW --> DONE
                         ^                |
                         |    (validation failure)
                         +--- REWORK <----+
```

### Cognitive Load Dynamics

Cognitive load (CL) evolves each tick:

```
CL(t+1) = clamp(0, 1,
    CL(t)
    + sync_load_rate  * s_i    (meetings add fatigue)
    + async_load_rate * a_i    (messages add less fatigue)
    - recovery_rate   * w_i    (focused work recovers)
    - natural_decay             (passive recovery)
)
```

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| sync_load_rate | 0.40 | Meetings are cognitively expensive |
| async_load_rate | 0.05 | Async messages are lightweight |
| recovery_rate | 0.03 | Deep work slowly restores focus |
| natural_decay | 0.01 | Passive recovery between ticks |

At `cognitive_load_penalty = 2.5`, a fully fatigued agent (CL = 1.0)
gets a 3.5x error multiplier (`1 + 2.5 * 1.0 = 3.5`). Sustained sync
accumulates CL that eventually overwhelms the 40% sync error reduction.

### Error Model

When a task's effort is exhausted, it undergoes validation. The base
defect probability is:

```
P_error = base_error_rate
          * (task_complexity / skill_level)
          * (1 + cognitive_load_penalty * cognitive_load)
```

Two modifiers adjust `P_error` based on coordination state:

1. **Sync error reduction** (multiplicative): when sync is active,
   `P_error` is scaled by `(1 - sync_error_reduction)`. At the default
   of 0.4: `P_error_sync = P_error * 0.6`.
2. **Rework-async penalty** (multiplicative): rework without sync
   multiplies `P_error` by `REWORK_ASYNC_PENALTY` (default 2.0). With
   sync active, this penalty does not apply.

### Exogenous Perturbation

Each tick, external events can disrupt in-flight tasks:

- **Signal** (p = 0.10): requirement shifts or API breaks force an
  in-progress task into REWORK.
- **Noise** (p = 0.15): communication churn adds +0.03 cognitive load
  to all agents without carrying useful information.

### Rework Cascade

When a task enters REWORK, each upstream dependency is also set to
REWORK with probability `p_cascade` (default 0.3), bounded by
`max_cascade_depth` (default 2). This nonlinear amplification produces
the phase-transition dynamics central to the paper.

Each rework cycle costs `base_effort * rework_effort_multiplier`
(default 1.0).

## Coordination Protocols

### Group A: Async Only (`AsyncOnlyProtocol`)

All agents allocate `(w=0.85, s=0, a=0.15)` every tick. No sync
meetings ever held.

**Expected outcome**: fast throughput but high rework from insufficient
coordination.

### Group B: Sync Always (`SyncAlwaysProtocol`)

All agents allocate `(w=1-s_min, s=s_min, a=0)` every tick, with
`s_min = 0.2` (minimum sync fraction). A persistent sync channel is
maintained regardless of rework state.

**Expected outcome**: lower rework but reduced throughput from constant
meeting overhead and cognitive load accumulation.

### Group C: Adaptive / Communication Valve (`AdaptiveProtocol`)

The protocol monitors rework rate each tick:

```
R(t) = D_rework(t) / max(D_total(t), 1)
```

where `D_rework(t)` = number of tasks that entered REWORK this tick
(from cascades and signal events), and `D_total(t)` = total demand
events this tick (newly READY tasks + newly REWORK tasks). This is a
per-tick flow ratio, not a ratio over the full task pool.

- **Default mode (async)**: `(w=0.85, s=0, a=0.15)`, same as Group A
- **Valve opens** when `R(t) > tau`: switches to `(w=0.80, s=0.20, a=0)`
- **Valve closes** when `R(t) <= tau * exit_ratio` (default 0.5):
  reverts to async. The exit_ratio creates hysteresis, preventing rapid
  mode-flapping.

**Expected outcome**: minimises `T_cost + T_rework` by activating sync
only when needed.

## Simulation Engine

### Tick-Based Loop

```
Phase 0: Exogenous Perturbation
    - Signal events force in-flight tasks to REWORK
    - Noise events add cognitive load to all agents

Phase 1: Demand Generation
    - Resolve dependencies (BLOCKED -> READY)
    - Propagate rework cascades upstream
    - Compute rework rate R(t)

Phase 2: Protocol Decision
    - Protocol evaluates R(t) and returns time-budget allocations

Phase 3: Supply Allocation
    - Apply (w_i, s_i, a_i) fractions to each agent
    - Set agent state (WORKING, IN_SYNC, READING_ASYNC, IDLE)

Phase 4: Execution
    - Each agent works on assigned task
    - Reduce task.remaining_effort by w_i * skill_level
    - On effort exhaustion: run validation (error model)
    - Generate async messages if a_i > 0

Phase 5: Cognitive Load Update
    - Apply CognitiveLoadModel.update() to all agents

Phase 6: Metric Collection
    - Record TickSnapshot (rework rate, demands, sync state, etc.)

Phase 7: Termination Check
    - If all tasks DONE, record completion tick and stop
```

### Coordination Cost Accounting

```
T_cost = sum_over_ticks(
    sum(agent.sync_fraction for all agents)        # sync agent-minutes
    + lambda * async_messages_this_tick             # async overhead
)
```

`lambda` (default 0.2) converts each async message into agent-minute
equivalents: 0.2 means each message costs one-fifth of an agent-minute.

Sync cost is `sum(s_i)` per tick, not `len(agents)`. An agent spending
20% of a tick in a meeting incurs 0.2 agent-minutes, not 1.0.

## Metrics

### Primary Metric: eta* (Rework-Adjusted Efficiency)

```
eta* = TaskScore / (T_completion + (T_cost + T_rework) / n_agents)
```

| Component | Units | Measures |
|-----------|-------|----------|
| T_completion | ticks | Wall-clock delay including rework |
| T_cost / n | ticks | Coordination overhead (meetings + messages) |
| T_rework / n | ticks | Wasted effort on rework cycles |

Both `T_cost` and `T_rework` are in agent-minutes; dividing by `n`
converts to ticks.

**Why eta* favours adaptive:**

- **Async-only**: low `T_cost` but high `T_rework`
- **Sync-always**: moderate `T_cost` but CL degradation increases errors
- **Adaptive**: minimises `T_cost + T_rework` by activating sync only
  when needed

### TaskScore (0-100)

```
TaskScore = (
    0.40 * unit_test_pass_rate
  + 0.40 * integration_integrity
  + 0.20 * spec_adherence
) * 100
```

| Component | Range | Computation |
|-----------|-------|-------------|
| `unit_test_pass_rate` | [0, 1] | Fraction of tasks passing validation defect-free on final attempt |
| `integration_integrity` | [0, 1] | Fraction of dependency edges where downstream completed without upstream-caused rework |
| `spec_adherence` | [0, 1] | `1 - (total_rework_events / total_tasks)`, clamped to [0, 1] |

### Legacy Metric: eta (without rework adjustment)

```
eta = TaskScore / (T_completion + T_cost / n_agents)
```

Retained for reference. Favours async-only because rework costs are
invisible.

### Secondary Metrics

| Metric | Description |
|--------|-------------|
| ticket_bounce_rate | Total rework events / total tasks |
| throughput | Tasks completed / ticks elapsed |
| time_to_completion | Ticks until all tasks reach DONE |
| total_coordination_cost | T_cost (sync + lambda * async messages) |
| total_rework_cost | T_rework (sum of rework_count * base_effort * rework_effort_multiplier) |
| cognitive_load_variance | Variance of agent cognitive loads at completion |
| mean_rework_cascade_depth | Average depth of rework cascade propagation |
| channel_utilization_ratio | Fraction of ticks with active sync channel |

### Phase Transition Detection

The tau sweep produces a curve of `eta*(tau)`. The numerical derivative
`d(eta*)/d(tau)` is computed via central differences. A sharp peak in
the absolute derivative indicates a phase transition at tau*.

## Paper Preset Parameters

100 replications per configuration with identical random seeds across
groups (seed_base = 42), ensuring every group faces the same exogenous
perturbation sequences and task graphs.

**Team structure**

| Parameter | Value |
|-----------|-------|
| num_agents | 5 |
| num_tasks | 20 |
| graph_topology | tree |

**Error model**

| Parameter | Value |
|-----------|-------|
| base_error_rate | 0.15 |
| cognitive_load_penalty | 2.5 |
| sync_error_reduction | 0.4 (40%) |
| rework_effort_multiplier | 1.0 |

**Perturbation**

| Parameter | Value |
|-----------|-------|
| p_signal_change | 0.10 |
| p_noise_change | 0.15 |
| p_cascade | 0.3 |
| max_cascade_depth | 2 |

**Simulation control**

| Parameter | Value |
|-----------|-------|
| max_ticks | 200 |
| runs_per_config | 100 |

Group C sweeps tau across 12 values:
`[0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]`

## Running the Experiment

See the [README](../README.md) for usage examples.
