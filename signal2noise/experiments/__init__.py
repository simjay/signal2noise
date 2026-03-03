"""Experiment infrastructure: runners, parameter sweeps, and paper presets."""

from signal2noise.experiments import presets
from signal2noise.experiments.runner import run_replications, run_single
from signal2noise.experiments.sweep import ParameterSweep

__all__ = [
    "ParameterSweep",
    "presets",
    "run_replications",
    "run_single",
]
