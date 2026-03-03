# Signal-to-Noise

Agent-based simulation of adaptive coordination protocols in software teams.

Built for the CAS 2026 paper: *"Signal-to-Noise: Rework Propagation as a Phase Transition Trigger in Socio-Technical Systems"*

## Installation

```bash
pip install -e .
```

With development tools (pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

Requires Python >= 3.10.

## Quick Start

Run a single simulation:

```python
from signal2noise import Simulation, SimulationConfig

cfg = SimulationConfig(
    protocol="adaptive",
    tau=0.3,
    num_agents=5,
    num_tasks=20,
    random_seed=42,
)
result = Simulation(cfg).run()
print(f"eta* = {result.rework_adjusted_eta:.3f}")
```

Run the full CAS 2026 paper experiment:

```python
from signal2noise.experiments.presets import cas2026_paper

results = cas2026_paper(runs_per_config=100, seed_base=42)
```

Run a parameter sweep:

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

## Documentation

- [Dataset analysis](docs/dataset.md) -- Jira calibration data and extracted parameters
- [Experiment design](docs/experiment.md) -- ABM formulation, protocols, metrics, hypotheses
- [Results](docs/results.md) -- Experiment outcomes and implications for the paper

## Project Structure

```
signal2noise/
  core/           # Agent, Task, TaskGraph, Simulation engine
  demand/         # Dependency resolution, rework cascade propagation
  supply/         # Time-budget allocation, cognitive load dynamics
  protocols/      # AsyncOnly, SyncAlways, Adaptive (Communication Valve)
  metrics/        # eta*, TaskScore, phase transition detection
  experiments/    # Runner, parameter sweep, paper presets
  viz/            # Plotting utilities
tests/            # Test suite
docs/             # Documentation
```

## Testing

```bash
pytest
```

With coverage:

```bash
pytest --cov=signal2noise
```

## License

MIT
