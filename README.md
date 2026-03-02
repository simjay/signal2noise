# Signal to Noise

Rework Propagation as a Phase Transition Trigger in Team Coordination.

## What this repo does

This repo simulates software teamwork with task dependencies.

The core question:
- When should a team switch from async work to live sync?

The model compares three coordination styles:
- `async_only`: never switch to sync
- `always_sync`: always in sync mode
- `swarm`: adaptive switching based on model signals

## Current model in plain language

- Work items depend on each other.
- If an upstream item changes, downstream items may need rework.
- Some events are meaningful `signal` (real change pressure).
- Some events are normal `noise` (routine communication churn).
- The policy decides when to turn sync on/off.

The simulator tracks:
- coordination need (`demand`)
- coordination capacity (`supply`)
- mismatch (`gap = demand - supply`)

This gap drives trigger quality metrics.

## Current policy behavior (swarm)

Swarm currently uses:
- signal-to-noise trigger
- gap gate
- hysteresis (`T_enter`, `T_exit`, `K`)
- cooldown (`cooldown_ticks`) to reduce rapid mode flipping

All defaults live in `config.yaml`.

## Main metrics

- `bounce_rate`: backward task movement rate
- `eta`: output quality per coordination effort
- `false_alarm_rate`: sync used when low need
- `missed_escalation_rate`: stayed async when high need

Extra paper metric:
- fixed-cost signal capture (swarm vs async at similar coordination cost)

## Repository layout

- `signal2noise/`: simulator engine and CLI code
- `config.yaml`: single source of truth for experiment settings
- `tests/`: unit tests
- `data/`: Jira and derived calibration data
- `results/`: experiment outputs

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .[dev]
```

## Quick start

Run experiment:

```bash
s2n run --config config.yaml --out results
```

Build summary tables:

```bash
s2n resources --in results --out results/resources
```

## CLI commands

Run:
```bash
s2n run --config config.yaml --out results
```

Resources:
```bash
s2n resources --in results --out results/resources
```

Analyze alias (same output path behavior):
```bash
s2n analyze --in results --out results/resources
```

Calibrate from external CSV:
```bash
s2n calibrate --in data/external_rework.csv --out results/calibrated_params.json
```

Calibrate directly from Jira SQL:
```bash
s2n calibrate-jira \
  --sql data/jira-social-repository/emotion_dataset_jira.sql \
  --out-csv data/derived/jira_calibration.csv \
  --out-stats results/calibration_stats.json \
  --out-summary results/calibration_summary.md
```

## Output files

From `s2n run`:
- `results/runs_summary.csv`
- `results/cascades.csv`
- `results/timeseries.csv`
- `results/events.csv` (unless `--no-events`)
- `results/config_resolved.json` or `results/multiple_config_resolved.json`

From `s2n resources`:
- `results/resources/mode_regime_summary.csv`
- `results/resources/signal_capture_fixed_cost.csv`
- `results/resources/naive_vs_swarm_ablation.csv` (only if `naive_trigger` is present in runs)

Optional sweep outputs used in deeper analysis:
- `results/resources/near_threshold_micro_sweep.csv`
- `results/resources/swarm_profile_tradeoff.csv`
- `results/resources/trigger_tuning_precision.csv`

## Tests

```bash
python -m pytest -q
```
