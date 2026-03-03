# Experiment Design

An agent-based model (ABM) for investigating how adaptive coordination
protocols affect team efficiency in software development workflows.
Built for the CAS 2026 paper: *"Signal-to-Noise: Rework Propagation as a Phase Transition Trigger in Socio-Technical Systems"*

## Research Question

> Does a rework-triggered **Communication Valve** (adaptive protocol)
> produce emergent efficiency advantages over both async-only and
> sync-always coordination, with a phase transition at a critical
> rework-rate threshold tau*?

The simulation compares three treatment groups:

| Group | Protocol | Mechanism |
|-------|----------|-----------|
| A | Async Only | Agents never hold sync meetings (control) |
| B | Sync Always | Agents maintain a persistent sync channel |
| C | Adaptive | Default async; sync swarm when rework rate > tau |

## ABM Formulation

### Agents

Each agent `i` is characterised by:

- **skill_level** in [0, 1] -- competence at producing defect-free work
- **cognitive_load** in [0, 1] -- accumulated fatigue from meetings
- **time budget** `(w_i, s_i, a_i)` -- fractions allocated to work,
  sync, and async communication (sum to 1.0)

The protocol sets the time budget each tick. Agents execute work on
assigned tasks with an effective work rate of `w_i * skill_level`.

### Task Graph

Work is organised as a directed acyclic graph (DAG) of `n` tasks, each
with:

- **complexity** in [0, 1] -- difficulty, drawn from configurable distributions
- **base_effort** -- nominal work units to complete (default 1.0)
- **dependency_set** -- upstream tasks that must finish first
- **rework_count** -- how many times the task has bounced back

Supported topologies: `linear` (chain), `tree` (fan-out), `diamond`
(fan-out then fan-in).

Task lifecycle:

```
BLOCKED --> READY --> IN_PROGRESS --> IN_REVIEW --> DONE
                         ^                |
                         |    (validation failure)
                         +--- REWORK <----+
```

### Error Model

When a task's effort is exhausted, it undergoes validation. The defect
probability is:

```
P_error = base_error_rate
          * (task_complexity / skill_level)
          * (1 + cognitive_load_penalty * cognitive_load)
```

Two key asymmetries drive the hypothesis:

1. **Sync error reduction**: when sync is active, `P_error` is reduced
   by `sync_error_reduction` (default 40%).
2. **Rework-async penalty**: resolving rework *without* sync context
   is harder -- the error rate is multiplied by `REWORK_ASYNC_PENALTY`
   (default 2.0x). With sync, the high-bandwidth channel helps agents
   understand what broke.

### Cognitive Load Dynamics

Cognitive load evolves each tick:

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
has a 3.5x error multiplier. This makes sustained sync genuinely costly
-- sync-always agents accumulate cognitive load that eventually
overwhelms the 40% sync error reduction.

### Exogenous Perturbation

Each tick, external events can disrupt in-flight tasks:

- **Signal** (p = 0.10): requirement shifts or upstream API breaks force
  an in-progress task into REWORK. This is the real-world signal that
  drives coordination need.
- **Noise** (p = 0.15): communication churn adds +0.03 cognitive load
  to all agents. This is overhead that does not carry useful information.

### Rework Cascade

When a task enters REWORK, upstream dependencies may also be affected.
With probability `p_cascade` (default 0.3), each upstream dependency
is set to REWORK, bounded by `max_cascade_depth` (default 2). This
nonlinear amplification produces the phase-transition dynamics central
to the paper.

Each rework cycle costs `base_effort * rework_effort_multiplier`
(default 1.0 -- rework costs the same as the original work, consistent
with empirical software engineering data from Boehm & Basili 2001).

## Coordination Protocols

### Group A: Async Only (`AsyncOnlyProtocol`)

All agents allocate `(w=0.85, s=0, a=0.15)` every tick. No sync
meetings are ever held.

**Expected outcome**: fast individual throughput but high rework from
insufficient coordination bandwidth.

### Group B: Sync Always (`SyncAlwaysProtocol`)

All agents allocate `(w=1-s_min, s=s_min, a=0)` every tick, with
`s_min = 0.2`. A persistent sync channel is maintained regardless of
the rework state.

**Expected outcome**: lower rework rate but reduced throughput from
constant meeting overhead and cognitive load accumulation.

### Group C: Adaptive / Communication Valve (`AdaptiveProtocol`)

The protocol monitors the rework rate `R(t) = D_rework / D_total` each
tick:

- **Default mode (async)**: `(w=0.85, s=0, a=0.15)` -- same as Group A
- **Valve opens** when `R(t) > tau`: switches to sync mode
  `(w=0.80, s=0.20, a=0)` -- same sync intensity as Group B
- **Valve closes** when `R(t) <= tau * exit_ratio` (default 0.5): reverts
  to async. The hysteresis prevents rapid flapping.

**Expected outcome**: minimises `T_cost + T_rework` by activating sync
only when the system signals it is needed.

## Simulation Engine

### Tick-Based Loop

Each tick proceeds through seven phases:

```
Phase 0: Exogenous Perturbation
    - Signal events force in-flight tasks to REWORK
    - Noise events add cognitive load to all agents

Phase 1: Demand Generation
    - Resolve dependencies (BLOCKED -> READY)
    - Propagate rework cascades upstream
    - Compute rework rate R(t)

Phase 2: Protocol Decision
    - Protocol.decide(R(t), agents, tick) -> AllocationPolicy
    - Update sync channel active/inactive state

Phase 3: Supply Allocation
    - Apply (w_i, s_i, a_i) fractions to each agent
    - Set agent state (WORKING, IN_SYNC, READING_ASYNC, IDLE)

Phase 4: Execution
    - Each agent works on their assigned task
    - Reduce task.remaining_effort by w_i * skill_level
    - On effort exhaustion: run validation (error model)
    - Generate async messages if a_i > 0

Phase 5: Cognitive Load Update
    - Apply CognitiveLoadModel.update() to all agents

Phase 6: Metric Collection
    - Record TickSnapshot (rework rate, demands, sync state, etc.)

Phase 7: Termination Check
    - If all tasks are DONE, record completion tick and stop
```

### Coordination Cost Accounting

The coordination cost `T_cost` sums two components each tick:

```
T_cost = sum_over_ticks(
    sum(agent.sync_fraction for all agents)   # sync agent-minutes
    + lambda * async_messages_this_tick        # async overhead
)
```

Sync cost is `sum(s_i)` per tick, not `len(agents)`. An agent spending
20% of their tick in a meeting incurs 0.2 agent-minutes of sync cost,
not 1.0. This accurate accounting is essential for fair comparison
between protocols.

## Metrics

### Primary Metric: eta* (Rework-Adjusted Efficiency)

```
eta* = TaskScore / (T_completion + (T_cost + T_rework) / n_agents)
```

The denominator captures all three sources of team-time consumption:

| Component | Units | What it measures |
|-----------|-------|-----------------|
| T_completion | ticks | Wall-clock delay (including rework) |
| T_cost / n | ticks | Coordination overhead (meetings + msgs) |
| T_rework / n | ticks | Wasted effort on rework cycles |

Both `T_cost` and `T_rework` are in agent-minutes; dividing by `n`
converts to ticks (one tick = `n` agent-minutes of team capacity).

**Why eta* favours the adaptive protocol:**

- **Async-only**: low `T_cost` but high `T_rework` (errors compound
  without sync context for rework resolution).
- **Sync-always**: low `T_rework` but high `T_cost` (constant meeting
  overhead) and cognitive load degradation that eventually increases
  errors.
- **Adaptive**: minimises `T_cost + T_rework` by activating sync only
  when needed, catching errors early without unnecessary meetings.

### TaskScore (0--100)

```
TaskScore = (
    0.40 * unit_test_pass_rate
  + 0.40 * integration_integrity
  + 0.20 * spec_adherence
) * 100
```

### Legacy Metric: eta (without rework adjustment)

```
eta = TaskScore / (T_completion + T_cost / n_agents)
```

Retained for reference. Systematically favours async-only because rework
costs are invisible.

### Secondary Metrics

| Metric | Description |
|--------|-------------|
| ticket_bounce_rate | Total rework events / total tasks |
| throughput | Tasks completed / ticks elapsed |
| time_to_completion | Ticks until all tasks reach DONE |
| total_coordination_cost | T_cost (sync + lambda * async messages) |
| total_rework_cost | T_rework (sum of rework_count * base_effort * m) |
| cognitive_load_variance | Variance of agent cognitive loads at completion |
| mean_rework_cascade_depth | Average depth of rework cascade propagation |
| channel_utilization_ratio | Fraction of ticks with active sync channel |

### Phase Transition Detection

The tau sweep produces a curve of `eta*(tau)`. The numerical derivative
`d(eta*)/d(tau)` is computed via central differences. A sharp peak in
the absolute derivative indicates a phase transition at critical
threshold `tau*` -- the point where switching from async to sync becomes
net-positive for system efficiency.

## Paper Preset Parameters

The main experiment runs 100 replications per configuration with
identical random seeds across all groups (seed_base = 42), ensuring
fair comparison -- every group faces the same exogenous perturbation
sequences and task graphs.

| Parameter | Value |
|-----------|-------|
| num_agents | 5 |
| num_tasks | 20 |
| graph_topology | tree |
| base_error_rate | 0.15 |
| cognitive_load_penalty | 2.5 |
| sync_error_reduction | 0.4 (40%) |
| rework_effort_multiplier | 1.0 |
| p_signal_change | 0.10 |
| p_noise_change | 0.15 |
| p_cascade | 0.3 |
| max_cascade_depth | 2 |
| max_ticks | 200 |
| runs_per_config | 100 |

Group C sweeps tau across 12 values:
`[0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]`

## Hypotheses

- **H1**: Adaptive reduces rework vs async-only while maintaining
  throughput (bounce_rate_C < bounce_rate_A, throughput_C >= 90% of A).
- **H2**: Adaptive achieves the highest eta* (above both A and B).
- **H3**: A phase transition exists in `eta*(tau)` at critical `tau*`
  (max |d(eta*)/d(tau)| > 0.1).
- **H4**: Adaptive minimises total overhead `T_cost + T_rework` (below
  both A and B).

## Running the Experiment

```python
from signal2noise.experiments.presets import cas2026_paper

results = cas2026_paper(runs_per_config=100, seed_base=42)
```

Or with a custom parameter sweep:

```python
from signal2noise import Simulation, SimulationConfig
from signal2noise.experiments import ParameterSweep

sweep = ParameterSweep(
    base_config=SimulationConfig(num_agents=5, num_tasks=20),
    sweep_params={
        "protocol": ["async_only", "sync_always", "adaptive"],
        "tau": [0.1, 0.2, 0.3, 0.4, 0.5],
    },
    runs_per_config=50,
    seed_base=42,
)
results = sweep.run()
```
