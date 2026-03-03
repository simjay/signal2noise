"""Phase transition detection: compute ∂η/∂τ across sweep results."""

from __future__ import annotations

import numpy as np

from signal2noise.core.types import RunSummary


def compute_phase_derivative(
    tau_values: list[float],
    eta_values: list[float],
) -> list[dict]:
    """Compute the numerical derivative ∂η/∂τ from a τ sweep.

    A sharp peak in the derivative indicates a phase transition — a critical
    threshold τ* where switching from async to sync becomes net-positive for
    system efficiency.

    Parameters
    ----------
    tau_values:
        Ordered list of τ threshold values used in the sweep.
    eta_values:
        Mean η values corresponding to each τ.  Must be the same length as
        ``tau_values``.

    Returns
    -------
    list[dict]
        Each entry contains ``{"tau": float, "eta": float, "deta_dtau": float}``.
        The derivative is undefined at the endpoints and is set to 0.0 there.
    """
    if len(tau_values) != len(eta_values):
        raise ValueError(
            f"tau_values (len={len(tau_values)}) and eta_values "
            f"(len={len(eta_values)}) must have the same length."
        )
    n = len(tau_values)
    taus = np.array(tau_values, dtype=float)
    etas = np.array(eta_values, dtype=float)

    results: list[dict] = []
    for i in range(n):
        if i == 0 or i == n - 1:
            deriv = 0.0
        else:
            dt = taus[i + 1] - taus[i - 1]
            deriv = float((etas[i + 1] - etas[i - 1]) / dt) if dt != 0 else 0.0
        results.append({"tau": float(taus[i]), "eta": float(etas[i]), "deta_dtau": deriv})
    return results


def find_critical_tau(phase_data: list[dict]) -> float:
    """Return τ* — the tau value where |∂η/∂τ| is maximised.

    Parameters
    ----------
    phase_data:
        Output of :func:`compute_phase_derivative`.

    Returns
    -------
    float
        The τ value at which the absolute derivative is largest.
        Returns 0.0 if ``phase_data`` is empty.
    """
    if not phase_data:
        return 0.0
    peak = max(phase_data, key=lambda d: abs(d["deta_dtau"]))
    return float(peak["tau"])


def summarise_sweep(
    tau_values: list[float],
    run_groups: list[list[RunSummary]],
) -> list[dict]:
    """Summarise a τ sweep into mean η ± std per τ value.

    Parameters
    ----------
    tau_values:
        Ordered list of τ values.
    run_groups:
        List of run-result lists, one per τ value.  Each inner list contains
        the ``RunSummary`` objects from multiple replications at that τ.

    Returns
    -------
    list[dict]
        Each entry: ``{"tau", "eta_mean", "eta_std", "n_runs"}``.
    """
    if len(tau_values) != len(run_groups):
        raise ValueError("tau_values and run_groups must have the same length.")
    summary: list[dict] = []
    for tau, runs in zip(tau_values, run_groups):
        etas = np.array([r.efficiency_ratio for r in runs], dtype=float)
        summary.append(
            {
                "tau": float(tau),
                "eta_mean": float(np.mean(etas)),
                "eta_std": float(np.std(etas)),
                "n_runs": len(runs),
            }
        )
    return summary
