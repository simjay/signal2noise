"""Publication-quality plots: phase diagrams, demand/supply curves, comparisons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Matplotlib is an optional dependency (listed under [project.optional-dependencies]).
# All plotting functions raise ImportError with a clear message if it is absent.
try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np

    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False

if TYPE_CHECKING:
    from signal2noise.core.types import RunSummary


def _require_mpl() -> None:
    if not _MPL_AVAILABLE:
        raise ImportError(
            "matplotlib is required for plotting. "
            "Install it with: pip install signal2noise[notebooks]"
        )


# ---------------------------------------------------------------------------
# Phase diagram
# ---------------------------------------------------------------------------

def phase_diagram(sweep_results: list[dict], ax: Any = None) -> Any:
    """Plot η vs. τ for adaptive protocol sweep results.

    Includes a vertical dashed line at τ* (the point of maximum |∂η/∂τ|).

    Parameters
    ----------
    sweep_results:
        Output of :func:`~signal2noise.experiments.presets.tau_sweep` or any
        list of dicts with ``"tau"`` and ``"efficiency_ratio_mean"`` keys.
    ax:
        Existing matplotlib Axes to draw on.  If None, a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
    """
    _require_mpl()

    from signal2noise.metrics.phase import compute_phase_derivative, find_critical_tau

    tau_vals = [r["tau"] for r in sweep_results]
    eta_vals = [r["efficiency_ratio_mean"] for r in sweep_results]

    phase_data = compute_phase_derivative(tau_vals, eta_vals)
    tau_star = find_critical_tau(phase_data)

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5))

    ax.plot(tau_vals, eta_vals, marker="o", linewidth=2, label="η (efficiency ratio)")
    ax.axvline(tau_star, linestyle="--", color="red", alpha=0.7, label=f"τ* = {tau_star:.2f}")

    if any(r.get("efficiency_ratio_std") for r in sweep_results):
        stds = [r.get("efficiency_ratio_std", 0.0) for r in sweep_results]
        ax.fill_between(
            tau_vals,
            np.array(eta_vals) - np.array(stds),
            np.array(eta_vals) + np.array(stds),
            alpha=0.2,
        )

    ax.set_xlabel("Rework threshold τ", fontsize=12)
    ax.set_ylabel("Efficiency ratio η", fontsize=12)
    ax.set_title("Phase diagram: η vs. τ", fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Group comparison box plot
# ---------------------------------------------------------------------------

def group_comparison(results: list[dict], ax: Any = None) -> Any:
    """Box plots comparing Groups A, B, and C efficiency ratios.

    Parameters
    ----------
    results:
        List of dicts with at least ``"protocol"`` and ``"_raw_runs"`` keys
        (raw RunSummary objects stored by sweep/runner).
    ax:
        Existing Axes.  If None, a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
    """
    _require_mpl()

    groups: dict[str, list[float]] = {}
    for entry in results:
        label = str(entry.get("protocol", "unknown"))
        raw = entry.get("_raw_runs", [])
        if raw:
            etas = [r.efficiency_ratio for r in raw]
            groups.setdefault(label, []).extend(etas)

    if not groups:
        raise ValueError("No _raw_runs data found in results.")

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5))

    labels = sorted(groups.keys())
    data = [groups[lbl] for lbl in labels]

    ax.boxplot(data, labels=labels, patch_artist=True)
    ax.set_xlabel("Protocol", fontsize=12)
    ax.set_ylabel("Efficiency ratio η", fontsize=12)
    ax.set_title("Group comparison: A vs B vs C", fontsize=14)
    ax.grid(True, axis="y", alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Demand/supply time series
# ---------------------------------------------------------------------------

def demand_supply_timeseries(result: "RunSummary", ax: Any = None) -> Any:
    """Plot D(t) and rework rate over simulation ticks.

    Parameters
    ----------
    result:
        A single ``RunSummary`` with ``tick_snapshots`` populated.
    ax:
        Existing Axes.  If None, a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
    """
    _require_mpl()

    snapshots = result.tick_snapshots
    if not snapshots:
        raise ValueError("RunSummary has no tick_snapshots.")

    ticks = [s.tick for s in snapshots]
    demand = [s.total_demand for s in snapshots]
    rework_rate = [s.rework_rate for s in snapshots]
    sync_active = [s.sync_active for s in snapshots]

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 5))

    ax2 = ax.twinx()
    ax.plot(ticks, demand, color="steelblue", label="Total demand D(t)")
    ax2.plot(ticks, rework_rate, color="tomato", linestyle="--", alpha=0.8, label="Rework rate R(t)")

    # Shade sync windows
    for s in snapshots:
        if s.sync_active:
            ax.axvspan(s.tick - 0.5, s.tick + 0.5, alpha=0.08, color="orange")

    ax.set_xlabel("Simulation tick", fontsize=12)
    ax.set_ylabel("Demand (tasks)", fontsize=12)
    ax2.set_ylabel("Rework rate R(t)", fontsize=12)
    ax.set_title("Demand and rework rate over time", fontsize=14)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=10)
    ax.grid(True, alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Cognitive load heatmap
# ---------------------------------------------------------------------------

def cognitive_load_heatmap(result: "RunSummary", ax: Any = None) -> Any:
    """Heatmap of per-agent cognitive load over simulation ticks.

    Parameters
    ----------
    result:
        A single ``RunSummary`` with ``tick_snapshots`` populated.
    ax:
        Existing Axes.  If None, a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
    """
    _require_mpl()

    snapshots = result.tick_snapshots
    if not snapshots:
        raise ValueError("RunSummary has no tick_snapshots.")

    agent_ids = sorted(snapshots[0].agent_cognitive_loads.keys())
    ticks = [s.tick for s in snapshots]
    matrix = np.array(
        [[s.agent_cognitive_loads.get(aid, 0.0) for aid in agent_ids] for s in snapshots]
    ).T  # shape (n_agents, n_ticks)

    if ax is None:
        _, ax = plt.subplots(figsize=(12, max(3, len(agent_ids))))

    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1,
                   extent=[ticks[0], ticks[-1], -0.5, len(agent_ids) - 0.5])
    ax.set_yticks(range(len(agent_ids)))
    ax.set_yticklabels(agent_ids)
    ax.set_xlabel("Simulation tick", fontsize=12)
    ax.set_ylabel("Agent", fontsize=12)
    ax.set_title("Cognitive load over time", fontsize=14)
    plt.colorbar(im, ax=ax, label="Cognitive load")
    return ax


# ---------------------------------------------------------------------------
# Rework cascade network
# ---------------------------------------------------------------------------

def rework_cascade_network(result: "RunSummary") -> Any:
    """Visualise rework propagation using a spring-layout network.

    Nodes are tasks; edges indicate rework cascade connections; node colour
    encodes rework count.  Requires ``networkx``.

    Parameters
    ----------
    result:
        Not currently used (placeholder for future integration with cascade
        event data).  Pass the ``RunSummary`` for API consistency.

    Returns
    -------
    matplotlib.axes.Axes
    """
    _require_mpl()

    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError("networkx is required for rework_cascade_network.") from exc

    raise NotImplementedError(
        "rework_cascade_network requires cascade event data not yet plumbed "
        "through RunSummary.  Use the existing signal2noise engine for "
        "cascade-level analysis."
    )
