"""Pre-configured experiment setups matching the CAS 2026 paper."""

from __future__ import annotations

from typing import Any

from signal2noise.core.simulation import SimulationConfig
from signal2noise.experiments.runner import run_replications
from signal2noise.experiments.sweep import ParameterSweep
from signal2noise.metrics.summary import aggregate_summary


# ---------------------------------------------------------------------------
# Paper preset constants
# ---------------------------------------------------------------------------

PAPER_PRESET: dict[str, Any] = {
    "name": "cas2026_paper",
    "description": "Replicates the 3-group comparison from the CAS 2026 paper",
    "configs": [
        # Group A: Async Only
        {
            "protocol": "async_only",
            "num_agents": 5,
            "num_tasks": 20,
            "graph_topology": "tree",
        },
        # Group B: Sync Always
        {
            "protocol": "sync_always",
            "num_agents": 5,
            "num_tasks": 20,
            "graph_topology": "tree",
            "s_min": 0.2,
        },
        # Group C: Adaptive (sweep τ)
        {
            "protocol": "adaptive",
            "num_agents": 5,
            "num_tasks": 20,
            "graph_topology": "tree",
            "tau": [
                0.05, 0.10, 0.15, 0.20, 0.25,
                0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80,
            ],
        },
    ],
    "runs_per_config": 100,
    "random_seed_base": 42,
}


# ---------------------------------------------------------------------------
# Preset functions
# ---------------------------------------------------------------------------

def cas2026_paper(runs_per_config: int = 100, seed_base: int = 42) -> list[dict]:
    """Run the full CAS 2026 paper experiment (3-group comparison).

    Runs Groups A, B, and C with the default parameters from the paper.
    Group C sweeps τ from 0.05 to 0.80.

    Parameters
    ----------
    runs_per_config:
        Number of replications per configuration. Default 100.
    seed_base:
        Base random seed for reproducibility. Default 42.

    Returns
    -------
    list[dict]
        One entry per group/τ combination with protocol label and
        aggregate metrics.
    """
    results: list[dict] = []

    # Group A
    base_a = SimulationConfig(
        protocol="async_only",
        num_agents=5,
        num_tasks=20,
        graph_topology="tree",
    )
    runs_a = run_replications(base_a, n_runs=runs_per_config, seed_base=seed_base)
    results.append({"group": "A", "protocol": "async_only", "tau": None, **aggregate_summary(runs_a)})

    # Group B
    base_b = SimulationConfig(
        protocol="sync_always",
        num_agents=5,
        num_tasks=20,
        graph_topology="tree",
        s_min=0.2,
    )
    runs_b = run_replications(base_b, n_runs=runs_per_config, seed_base=seed_base)
    results.append({"group": "B", "protocol": "sync_always", "tau": None, **aggregate_summary(runs_b)})

    # Group C — τ sweep
    # Use the SAME seed_base as Groups A and B so every group faces
    # identical exogenous perturbation sequences and task graphs,
    # making the comparison fair (only the protocol differs).
    tau_values = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]
    for tau in tau_values:
        cfg_c = SimulationConfig(
            protocol="adaptive",
            tau=tau,
            num_agents=5,
            num_tasks=20,
            graph_topology="tree",
        )
        runs_c = run_replications(cfg_c, n_runs=runs_per_config, seed_base=seed_base)
        results.append(
            {
                "group": "C",
                "protocol": "adaptive",
                "tau": tau,
                **aggregate_summary(runs_c),
            }
        )

    return results


def tau_sweep(
    tau_min: float = 0.05,
    tau_max: float = 0.80,
    tau_step: float = 0.05,
    runs_per_config: int = 100,
    seed_base: int = 42,
) -> list[dict]:
    """Sweep τ from *tau_min* to *tau_max* in steps of *tau_step*.

    Parameters
    ----------
    tau_min:
        Lower bound for τ sweep.
    tau_max:
        Upper bound for τ sweep (inclusive).
    tau_step:
        Step size.
    runs_per_config:
        Replications per τ value.
    seed_base:
        Base random seed.

    Returns
    -------
    list[dict]
        One entry per τ with aggregate metrics.
    """
    import numpy as np

    tau_values = list(np.arange(tau_min, tau_max + tau_step / 2, tau_step))
    base = SimulationConfig(
        protocol="adaptive",
        num_agents=3,
        num_tasks=15,
        graph_topology="linear",
    )
    sweep = ParameterSweep(
        base_config=base,
        sweep_params={"tau": tau_values},
        runs_per_config=runs_per_config,
        seed_base=seed_base,
    )
    return sweep.run()


def team_size_comparison(
    team_sizes: list[int] | None = None,
    runs_per_config: int = 100,
    seed_base: int = 42,
) -> list[dict]:
    """Compare Groups A/B/C across multiple team sizes.

    Parameters
    ----------
    team_sizes:
        Team sizes to compare. Default [3, 5, 8].
    runs_per_config:
        Replications per configuration.
    seed_base:
        Base random seed.

    Returns
    -------
    list[dict]
        Results for all (team_size × protocol) combinations.
    """
    if team_sizes is None:
        team_sizes = [3, 5, 8]

    base = SimulationConfig(num_tasks=15, graph_topology="linear")
    sweep = ParameterSweep(
        base_config=base,
        sweep_params={
            "num_agents": team_sizes,
            "protocol": ["async_only", "sync_always", "adaptive"],
        },
        runs_per_config=runs_per_config,
        seed_base=seed_base,
    )
    return sweep.run()
