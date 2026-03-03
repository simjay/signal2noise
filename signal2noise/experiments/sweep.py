"""Parameter sweep orchestration: parallel runs across configurations."""

from __future__ import annotations

import copy
import itertools
from typing import Any

from signal2noise.core.simulation import SimulationConfig
from signal2noise.core.types import RunSummary
from signal2noise.experiments.runner import run_replications
from signal2noise.metrics.summary import aggregate_summary


class ParameterSweep:
    """Orchestrates a grid sweep over one or more configuration parameters.

    Generates all combinations of the provided parameter values, runs
    ``runs_per_config`` replications for each combination, and returns the
    full result set.

    Parameters
    ----------
    base_config:
        Base ``SimulationConfig`` used as a starting point for all combos.
    sweep_params:
        Mapping from SimulationConfig attribute name to a list of values to
        sweep.  For example::

            {"protocol": ["async_only", "adaptive"], "tau": [0.1, 0.3, 0.5]}

        All combinations are expanded into a Cartesian product.
    runs_per_config:
        Number of replications per configuration point. Default 100.
    seed_base:
        Base seed for reproducibility. Default 42.
    n_jobs:
        Number of parallel workers.  -1 uses all available CPUs.
        Parallelism is implemented via :mod:`joblib` if available; falls
        back to serial execution otherwise. Default -1.
    """

    def __init__(
        self,
        base_config: SimulationConfig,
        sweep_params: dict[str, list[Any]],
        runs_per_config: int = 100,
        seed_base: int = 42,
        n_jobs: int = -1,
    ) -> None:
        self.base_config = base_config
        self.sweep_params = sweep_params
        self.runs_per_config = runs_per_config
        self.seed_base = seed_base
        self.n_jobs = n_jobs

    def _build_configs(self) -> list[tuple[dict[str, Any], SimulationConfig]]:
        """Expand the sweep_params grid into a list of (combo, config) pairs."""
        keys = list(self.sweep_params.keys())
        value_lists = [
            v if isinstance(v, list) else [v]
            for v in self.sweep_params.values()
        ]
        configs: list[tuple[dict[str, Any], SimulationConfig]] = []
        for combo in itertools.product(*value_lists):
            overrides = dict(zip(keys, combo))
            cfg = _apply_overrides(self.base_config, overrides)
            configs.append((overrides, cfg))
        return configs

    def run(self) -> list[dict]:
        """Execute the full parameter sweep.

        Returns
        -------
        list[dict]
            One entry per configuration combination.  Each dict contains the
            override parameters plus aggregated statistics from all
            replications:
            ``{"tau": 0.3, "protocol": "adaptive", "eta_mean": ..., ...}``.
        """
        config_pairs = self._build_configs()
        results: list[dict] = []

        def _run_one(idx: int, overrides: dict, cfg: SimulationConfig) -> dict:
            seed = self.seed_base + idx * self.runs_per_config
            runs = run_replications(cfg, n_runs=self.runs_per_config, seed_base=seed)
            agg = aggregate_summary(runs)
            return {**overrides, **agg, "_raw_runs": runs}

        try:
            from joblib import Parallel, delayed  # type: ignore

            raw = Parallel(n_jobs=self.n_jobs)(
                delayed(_run_one)(idx, overrides, cfg)
                for idx, (overrides, cfg) in enumerate(config_pairs)
            )
            results = list(raw)
        except ImportError:
            for idx, (overrides, cfg) in enumerate(config_pairs):
                results.append(_run_one(idx, overrides, cfg))

        return results


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _apply_overrides(
    base: SimulationConfig, overrides: dict[str, Any]
) -> SimulationConfig:
    """Return a copy of *base* with the given field overrides applied."""
    cfg = copy.copy(base)
    for k, v in overrides.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg
