"""Single experiment runner: config → Simulation → RunSummary."""

from __future__ import annotations

import copy
from typing import Any

from signal2noise.core.simulation import Simulation, SimulationConfig
from signal2noise.core.types import RunSummary


def run_single(config: SimulationConfig) -> RunSummary:
    """Run one simulation and return its summary.

    Parameters
    ----------
    config:
        Complete simulation configuration.

    Returns
    -------
    RunSummary
        Aggregate metrics and tick-level snapshots from the run.
    """
    sim = Simulation(config)
    return sim.run()


def run_replications(
    config: SimulationConfig,
    n_runs: int = 100,
    seed_base: int = 42,
) -> list[RunSummary]:
    """Run *n_runs* replications of the same configuration.

    Each replication uses a deterministic seed derived from ``seed_base + run_idx``
    to ensure reproducibility while varying across runs.

    Parameters
    ----------
    config:
        Base configuration.  The ``random_seed`` field is overridden per run.
    n_runs:
        Number of independent replications.
    seed_base:
        Base integer seed; run *i* uses ``seed_base + i``.

    Returns
    -------
    list[RunSummary]
        One summary per replication, in order.
    """
    results: list[RunSummary] = []
    for i in range(n_runs):
        run_cfg = _clone_with_seed(config, seed_base + i)
        results.append(run_single(run_cfg))
    return results


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clone_with_seed(config: SimulationConfig, seed: int) -> SimulationConfig:
    """Return a shallow copy of *config* with ``random_seed`` set to *seed*."""
    cfg = copy.copy(config)
    cfg.random_seed = seed
    return cfg
