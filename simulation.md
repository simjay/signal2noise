# Signal-to-Noise: Communication Valve Simulation

An agent-based model (ABM) for investigating how adaptive coordination
protocols affect team efficiency in software development workflows.
Built for the CAS 2026 paper: *"The Communication Valve: When Synchronous
Coordination Becomes the Signal."*

---

## 1. Research Question

> Does a rework-triggered **Communication Valve** (adaptive protocol)
> produce emergent efficiency advantages over both async-only and
> sync-always coordination, with a phase transition at a critical
> rework-rate threshold tau*?

The simulation compares three treatment groups:

| Group | Protocol     | Mechanism                                      |
|-------|--------------|-------------------------------------------------|
| A     | Async Only   | Agents never hold sync meetings (control)       |
| B     | Sync Always  | Agents maintain a persistent sync channel        |
| C     | Adaptive     | Default async; sync swarm when rework rate > tau |

---

## 2. ABM Formulation

### 2.1 Agents

Each agent `i` is characterised by:

- **skill_level** in [0, 1] -- competence at producing defect-free work
- **cognitive_load** in [0, 1] -- accumulated fatigue from meetings
- **time budget** `(w_i, s_i, a_i)` -- fractions allocated to work,
  sync, and async communication (sum to 1.0)

The protocol sets the time budget each tick. Agents execute work on
assigned tasks with an effective work rate of `w_i * skill_level`.

### 2.2 Task Graph

Work is organised as a directed acyclic graph (DAG) of `n` tasks, each
with:

- **complexity** in [0, 1] -- difficulty, drawn from configurable distributions
- **base_effort** -- nominal work units to complete (default 1.0)
- **dependency_set** -- upstream tasks that must finish first
- **rework_count** -- how many times the task has bounced back

Supported topologies: `linear` (chain), `tree` (fan-out), `diamond`
(fan-out then fan-in).

Tasks follow a lifecycle:

```
BLOCKED --> READY --> IN_PROGRESS --> IN_REVIEW --> DONE
                         ^                |
                         |    (validation failure)
                         +--- REWORK <----+
```

### 2.3 Error Model

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

### 2.4 Cognitive Load Dynamics

Cognitive load evolves each tick according to:

```
CL(t+1) = clamp(0, 1,
    CL(t)
    + sync_load_rate  * s_i    (meetings add fatigue)
    + async_load_rate * a_i    (messages add less fatigue)
    - recovery_rate   * w_i    (focused work recovers)
    - natural_decay            (passive recovery)
)
```

| Parameter        | Default | Rationale                                  |
|------------------|---------|--------------------------------------------|
| sync_load_rate   | 0.40    | Meetings are cognitively expensive         |
| async_load_rate  | 0.05    | Async messages are lightweight             |
| recovery_rate    | 0.03    | Deep work slowly restores focus            |
| natural_decay    | 0.01    | Passive recovery between ticks             |

At `cognitive_load_penalty = 2.5`, a fully fatigued agent (CL = 1.0)
has a 3.5x error multiplier. This makes sustained sync genuinely costly
-- sync-always agents accumulate cognitive load that eventually
overwhelms the 40% sync error reduction.

### 2.5 Exogenous Perturbation

Each tick, external events can disrupt in-flight tasks:

- **Signal** (p = 0.10): requirement shifts or upstream API breaks force
  an in-progress task into REWORK. This is the real-world signal that
  drives coordination need.
- **Noise** (p = 0.15): communication churn adds +0.03 cognitive load
  to all agents. This is overhead that does not carry useful information.

### 2.6 Rework Cascade

When a task enters REWORK, upstream dependencies may also be affected.
With probability `p_cascade` (default 0.3), each upstream dependency
is set to REWORK, bounded by `max_cascade_depth` (default 2). This
nonlinear amplification produces the phase-transition dynamics central
to the paper.

Each rework cycle costs `base_effort * rework_effort_multiplier`
(default 1.0 -- rework costs the same as the original work, consistent
with empirical software engineering data from Boehm & Basili 2001).

---

## 3. Coordination Protocols

### 3.1 Group A: Async Only (`AsyncOnlyProtocol`)

All agents allocate `(w=0.85, s=0, a=0.15)` every tick. No sync
meetings are ever held. Coordination happens exclusively through
asynchronous messages.

**Expected outcome**: fast individual throughput but high rework from
insufficient coordination bandwidth.

### 3.2 Group B: Sync Always (`SyncAlwaysProtocol`)

All agents allocate `(w=1-s_min, s=s_min, a=0)` every tick, with
`s_min = 0.2`. A persistent sync channel is maintained regardless of
the rework state.

**Expected outcome**: lower rework rate but reduced throughput from
constant meeting overhead and cognitive load accumulation.

### 3.3 Group C: Adaptive / Communication Valve (`AdaptiveProtocol`)

The protocol monitors the rework rate `R(t) = D_rework / D_total` each
tick:

- **Default mode (async)**: `(w=0.85, s=0, a=0.15)` -- same as Group A
- **Valve opens** when `R(t) > tau`: switches to sync mode
  `(w=0.80, s=0.20, a=0)` -- same sync intensity as Group B
- **Valve closes** when `R(t) <= tau * exit_ratio` (default 0.5): reverts
  to async. The hysteresis prevents rapid flapping.

**Expected outcome**: minimises `T_cost + T_rework` by activating sync
only when the system signals it is needed.

---

## 4. Simulation Engine

### 4.1 Tick-Based Loop

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

### 4.2 Coordination Cost Accounting

The coordination cost `T_cost` sums two components each tick:

```
T_cost = sum_over_ticks(
    sum(agent.sync_fraction for all agents)   # sync agent-minutes
    + lambda * async_messages_this_tick        # async overhead
)
```

Key detail: sync cost is `sum(s_i)` per tick, not `len(agents)`. An
agent spending 20% of their tick in a meeting incurs 0.2 agent-minutes
of sync cost, not 1.0. This accurate accounting is essential for fair
comparison between protocols.

---

## 5. Metrics

### 5.1 Primary Metric: eta* (Rework-Adjusted Efficiency)

```
eta* = TaskScore / (T_completion + (T_cost + T_rework) / n_agents)
```

The denominator captures **all three** sources of team-time consumption:

| Component      | Units          | What it measures                       |
|----------------|----------------|----------------------------------------|
| T_completion   | ticks          | Wall-clock delay (including rework)    |
| T_cost / n     | ticks          | Coordination overhead (meetings + msgs)|
| T_rework / n   | ticks          | Wasted effort on rework cycles         |

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

### 5.2 TaskScore (0--100)

```
TaskScore = (
    0.40 * unit_test_pass_rate     # fraction of tasks reaching DONE
  + 0.40 * integration_integrity   # fraction of all tasks completed
  + 0.20 * spec_adherence          # fraction of DONE tasks with zero rework
) * 100
```

### 5.3 Legacy Metric: eta (without rework adjustment)

```
eta = TaskScore / (T_completion + T_cost / n_agents)
```

This metric does not penalise rework waste and is retained only for
reference. It systematically favours async-only (low `T_cost`) because
rework costs are invisible.

### 5.4 Secondary Metrics

| Metric                    | Description                                       |
|---------------------------|---------------------------------------------------|
| ticket_bounce_rate        | Total rework events / total tasks                 |
| throughput                | Tasks completed / ticks elapsed                   |
| time_to_completion        | Ticks until all tasks reach DONE                  |
| total_coordination_cost   | T_cost (sync + lambda * async messages)           |
| total_rework_cost         | T_rework (sum of rework_count * base_effort * m)  |
| cognitive_load_variance   | Variance of agent cognitive loads at completion    |
| mean_rework_cascade_depth | Average depth of rework cascade propagation       |
| channel_utilization_ratio | Fraction of ticks with active sync channel        |

### 5.5 Phase Transition Detection

The tau sweep produces a curve of `eta*(tau)`. The numerical derivative
`d(eta*)/d(tau)` is computed via central differences. A sharp peak in
the absolute derivative indicates a phase transition at critical
threshold `tau*` -- the point where switching from async to sync becomes
net-positive for system efficiency.

---

## 6. Experiment Design

### 6.1 Paper Preset (`cas2026_paper`)

The main experiment runs 100 replications per configuration with
identical random seeds across all groups (seed_base = 42), ensuring
fair comparison -- every group faces the same exogenous perturbation
sequences and task graphs.

| Parameter             | Value          |
|-----------------------|----------------|
| num_agents            | 5              |
| num_tasks             | 20             |
| graph_topology        | tree           |
| base_error_rate       | 0.15           |
| cognitive_load_penalty| 2.5            |
| sync_error_reduction  | 0.4 (40%)      |
| rework_effort_mult.   | 1.0            |
| p_signal_change       | 0.10           |
| p_noise_change        | 0.15           |
| p_cascade             | 0.3            |
| max_cascade_depth     | 2              |
| max_ticks             | 200            |
| runs_per_config       | 100            |

Group C sweeps tau across 12 values:
`[0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]`

### 6.2 Hypotheses

- **H1**: Adaptive reduces rework vs async-only while maintaining
  throughput (bounce_rate_C < bounce_rate_A, throughput_C >= 90% of A).
- **H2**: Adaptive achieves the highest eta* (above both A and B).
- **H3**: A phase transition exists in `eta*(tau)` at critical `tau*`
  (max |d(eta*)/d(tau)| > 0.1).
- **H4**: Adaptive minimises total overhead `T_cost + T_rework` (below
  both A and B).

### 6.3 Running the Experiment

```bash
python run_experiment.py
```

This runs the full 3-group comparison and reports:
- Per-group metrics (eta*, TaskScore, bounce rate, costs, etc.)
- Group C tau sweep table
- Phase transition analysis with tau* identification
- Hypothesis evaluation (H1--H4)
- Raw results saved to `experiment_results.json`

---

## 7. Code Architecture

```
signal2noise/
  __init__.py               # Public API re-exports
  core/
    types.py                # Enums (TaskStatus, AgentState), dataclasses
                            #   (TickSnapshot, RunSummary), type aliases
    agent.py                # Agent model: skill, cognitive load, error rate
    task.py                 # Task model: complexity, effort, rework count
    task_graph.py           # DAG builder (linear/tree/diamond), queries
    channel.py              # AsyncChannel and SyncChannel models
    simulation.py           # SimulationConfig + Simulation tick loop
  demand/
    generator.py            # DemandGenerator: dependency resolution
    rework.py               # ReworkEngine: cascade propagation
  supply/
    allocator.py            # Allocator: applies time-budget fractions
    cognitive_load.py       # CognitiveLoadModel: fatigue dynamics
  protocols/
    base.py                 # Protocol ABC (decide -> AllocationPolicy)
    async_only.py           # Group A: s_i = 0 always
    sync_always.py          # Group B: s_i >= s_min always
    adaptive.py             # Group C: Communication Valve
  metrics/
    collectors.py           # TickCollector: per-tick snapshot recording
    efficiency.py           # eta, eta*, TaskScore, T_rework computation
    phase.py                # Phase derivative and tau* detection
    summary.py              # RunSummary aggregation (mean, std, CI)
  experiments/
    runner.py               # run_single, run_replications
    sweep.py                # ParameterSweep (Cartesian grid)
    presets.py              # cas2026_paper(), tau_sweep(), etc.
  viz/
    plots.py                # Plotting utilities
tests/                      # 119 tests covering all components
run_experiment.py           # Main experiment entry point
```

### 7.1 Data Flow

```
SimulationConfig
    |
    v
Simulation.__init__()
    - builds Agents (skill distribution)
    - builds TaskGraph (DAG topology)
    - creates AsyncChannel, SyncChannel
    |
    v
Simulation.run() -- tick loop
    |
    +---> DemandGenerator.resolve() -- BLOCKED -> READY
    +---> ReworkEngine.propagate()  -- cascade REWORK upstream
    +---> Protocol.decide()         -- AllocationPolicy
    +---> Allocator.apply()         -- set agent (w, s, a)
    +---> _agent_execute()          -- work on tasks, validate
    +---> CognitiveLoadModel.update() -- fatigue dynamics
    +---> TickCollector.record()    -- snapshot
    |
    v
RunSummary
    - ticket_bounce_rate, eta, eta*, T_cost, T_rework, etc.
    - tick_snapshots (time series)
```

### 7.2 Key Design Decisions

1. **Same seeds across groups**: All three groups use identical
   `seed_base`, ensuring the only experimental variable is the protocol.

2. **Sync cost = sum(s_i)**: Sync cost is the actual agent-minutes spent
   in meetings (sum of sync fractions), not the headcount. This prevents
   over-counting when agents spend only 20% of their tick in sync.

3. **Rework-async penalty (2x)**: Resolving rework without sync context
   is harder -- agents must guess at the root cause without high-bandwidth
   discussion. This is the core mechanism that makes the adaptive
   protocol valuable.

4. **Cognitive load penalty (2.5x)**: At full fatigue, errors are
   amplified 3.5x. This penalises sync-always for the cumulative
   cognitive cost of sustained meetings.

5. **Hysteresis in valve control**: The valve closes at `tau * exit_ratio`
   (default 0.5 * tau), not at tau itself. This prevents rapid flapping
   between async and sync modes.

---

## 8. Extending the Model

### Adding a New Protocol

1. Create a new class inheriting from `Protocol` (in `protocols/base.py`)
2. Implement `decide(rework_rate, agents, tick) -> AllocationPolicy`
3. Register it in `Simulation._attach_protocol()` and `SimulationConfig`

### Adding New Metrics

1. Add fields to `RunSummary` in `core/types.py`
2. Compute the metric in `_build_run_summary()` in `core/simulation.py`
3. Add to `aggregate_summary()` in `metrics/summary.py`

### Custom Experiments

```python
from signal2noise import Simulation, SimulationConfig
from signal2noise.experiments import ParameterSweep

sweep = ParameterSweep(
    base_config=SimulationConfig(num_agents=5, num_tasks=20),
    sweep_params={
        "protocol": ["async_only", "sync_always", "adaptive"],
        "tau": [0.1, 0.2, 0.3, 0.4, 0.5],
        "num_agents": [3, 5, 8],
    },
    runs_per_config=50,
    seed_base=42,
)
results = sweep.run()
```
