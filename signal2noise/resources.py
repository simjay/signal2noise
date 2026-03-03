from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


CORE_METRICS = ["bounce_rate", "eta", "false_alarm_rate", "missed_escalation_rate"]
MODE_REGIME_METRICS = [
    "bounce_rate",
    "eta",
    "false_alarm_rate",
    "missed_escalation_rate",
    "trigger_precision",
    "trigger_recall",
    "trigger_f1",
    "trigger_specificity",
    "trigger_balanced_accuracy",
    "avg_cascade_size",
    "max_cascade_size",
    "cascade_run_ge_1",
    "cascade_run_ge_2",
    "C_load_per_ticket",
    "coordination_cost",
]
CORE_CLAIM_METRICS = [
    "trigger_f1",
    "missed_escalation_rate",
    "bounce_rate",
    "cascade_run_ge_2",
    "C_load_per_ticket",
]
FIXED_COST_MAX_REL_GAP = 0.10


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _coerce_run_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numeric = {"run_id", "seed_run_id", "stress_multiplier", *MODE_REGIME_METRICS}
    out: list[dict[str, Any]] = []
    for row in rows:
        nr = dict(row)
        for k in numeric:
            if k in nr and nr[k] != "":
                nr[k] = _to_float(nr[k], default=0.0)
        if "stress_multiplier" not in nr or nr["stress_multiplier"] == "":
            nr["stress_multiplier"] = 1.0
        out.append(nr)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _bootstrap_ci(values: list[float], seed: int, n_boot: int = 400) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    n = len(values)
    samples: list[float] = []
    for _ in range(n_boot):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(_mean(draw))
    samples.sort()
    lo_idx = int(math.floor(0.025 * (n_boot - 1)))
    hi_idx = int(math.ceil(0.975 * (n_boot - 1)))
    return samples[lo_idx], samples[hi_idx]


def _build_stress_regime_map(rows: list[dict[str, Any]]) -> dict[float, str]:
    vals = sorted({float(_to_float(r.get("stress_multiplier", 1.0), 1.0)) for r in rows})
    if not vals:
        return {1.0: "low"}
    if len(vals) == 1:
        return {vals[0]: "low"}
    labels = ["low", "near_threshold", "high"]
    mapping: dict[float, str] = {}
    for i, val in enumerate(vals):
        if i < len(labels):
            mapping[val] = labels[i]
        else:
            mapping[val] = f"stress_{val:g}"
    return mapping


def _group_rows(rows: list[dict[str, Any]], keys: list[str]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(k) for k in keys)].append(row)
    return grouped


def _build_mode_regime_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stress_to_regime = _build_stress_regime_map(rows)
    tagged: list[dict[str, Any]] = []
    for row in rows:
        nr = dict(row)
        stress = float(_to_float(row.get("stress_multiplier", 1.0), 1.0))
        nr["regime"] = stress_to_regime.get(stress, f"stress_{stress:g}")
        tagged.append(nr)

    grouped = _group_rows(tagged, ["regime", "policy"])
    out: list[dict[str, Any]] = []
    for idx, ((regime, policy), sub) in enumerate(
        sorted(grouped.items(), key=lambda x: (str(x[0][0]), str(x[0][1])))
    ):
        rec: dict[str, Any] = {
            "regime": str(regime),
            "policy": str(policy),
            "n_runs": len(sub),
            "stress_multiplier_mean": _mean([float(_to_float(r.get("stress_multiplier", 1.0), 1.0)) for r in sub]),
        }
        for m_idx, m in enumerate(MODE_REGIME_METRICS):
            vals = [float(_to_float(r.get(m, 0.0), 0.0)) for r in sub]
            rec[f"{m}_mean"] = _mean(vals)
            low, high = _bootstrap_ci(vals, seed=1000 + idx * 100 + m_idx)
            rec[f"{m}_ci95_low"] = low
            rec[f"{m}_ci95_high"] = high
        out.append(rec)
    return out


def _build_naive_vs_swarm_ablation(mode_regime: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(str(r["regime"]), str(r["policy"])): r for r in mode_regime}
    preferred_regime = "near_threshold"

    if (preferred_regime, "swarm") in by_key and (preferred_regime, "naive_trigger") in by_key:
        regimes = [preferred_regime]
    else:
        regimes = sorted({str(r["regime"]) for r in mode_regime})

    out: list[dict[str, Any]] = []
    for regime in regimes:
        swarm = by_key.get((regime, "swarm"))
        naive = by_key.get((regime, "naive_trigger"))
        if swarm is None or naive is None:
            continue
        out.append(
            {
                "regime": regime,
                "eta_gain_swarm_vs_naive": float(swarm["eta_mean"]) - float(naive["eta_mean"]),
                "bounce_rate_reduction_swarm_vs_naive": float(naive["bounce_rate_mean"])
                - float(swarm["bounce_rate_mean"]),
                "false_alarm_reduction_swarm_vs_naive": float(naive["false_alarm_rate_mean"])
                - float(swarm["false_alarm_rate_mean"]),
                "missed_escalation_reduction_swarm_vs_naive": float(naive["missed_escalation_rate_mean"])
                - float(swarm["missed_escalation_rate_mean"]),
            }
        )
    return out


def _build_signal_capture_fixed_cost(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stress_to_regime = _build_stress_regime_map(rows)
    tagged: list[dict[str, Any]] = []
    for row in rows:
        nr = dict(row)
        stress = float(_to_float(row.get("stress_multiplier", 1.0), 1.0))
        nr["regime"] = stress_to_regime.get(stress, f"stress_{stress:g}")
        tagged.append(nr)

    out: list[dict[str, Any]] = []
    by_regime = _group_rows(tagged, ["regime"])
    for regime_key, regime_rows in sorted(by_regime.items(), key=lambda x: str(x[0][0])):
        regime = str(regime_key[0])
        async_rows = [r for r in regime_rows if str(r.get("policy")) == "async_only"]
        swarm_rows = [r for r in regime_rows if str(r.get("policy")) == "swarm"]
        if not async_rows or not swarm_rows:
            continue

        bounce_gains: list[float] = []
        eta_gains: list[float] = []
        rel_cost_gaps: list[float] = []
        n_candidates = len(swarm_rows)

        for sw in swarm_rows:
            sw_cost = float(_to_float(sw.get("C_load_per_ticket", 0.0), 0.0))
            sw_bounce = float(_to_float(sw.get("bounce_rate", 0.0), 0.0))
            sw_eta = float(_to_float(sw.get("eta", 0.0), 0.0))

            match = min(
                async_rows,
                key=lambda ar: abs(float(_to_float(ar.get("C_load_per_ticket", 0.0), 0.0)) - sw_cost),
            )
            as_cost = float(_to_float(match.get("C_load_per_ticket", 0.0), 0.0))
            as_bounce = float(_to_float(match.get("bounce_rate", 0.0), 0.0))
            as_eta = float(_to_float(match.get("eta", 0.0), 0.0))
            rel_gap = abs(sw_cost - as_cost) / max(1e-9, as_cost)
            if rel_gap > FIXED_COST_MAX_REL_GAP:
                continue

            bounce_gains.append(as_bounce - sw_bounce)
            eta_gains.append(sw_eta - as_eta)
            rel_cost_gaps.append(rel_gap)

        if not bounce_gains:
            continue

        low_b, high_b = _bootstrap_ci(bounce_gains, seed=3400 + len(out))
        low_e, high_e = _bootstrap_ci(eta_gains, seed=3600 + len(out))
        out.append(
            {
                "regime": regime,
                "n_swarm_candidates": n_candidates,
                "n_pairs": len(bounce_gains),
                "pairing_coverage": len(bounce_gains) / max(1, n_candidates),
                "max_relative_cost_gap_allowed": FIXED_COST_MAX_REL_GAP,
                "signal_capture_bounce_gain_swarm_vs_async": _mean(bounce_gains),
                "signal_capture_bounce_gain_ci95_low": low_b,
                "signal_capture_bounce_gain_ci95_high": high_b,
                "eta_gain_swarm_vs_async_fixed_cost": _mean(eta_gains),
                "eta_gain_fixed_cost_ci95_low": low_e,
                "eta_gain_fixed_cost_ci95_high": high_e,
                "mean_relative_cost_gap_to_async_match": _mean(rel_cost_gaps),
            }
        )
    return out


def _build_core_claim_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stress_to_regime = _build_stress_regime_map(rows)
    tagged: list[dict[str, Any]] = []
    for row in rows:
        nr = dict(row)
        stress = float(_to_float(row.get("stress_multiplier", 1.0), 1.0))
        nr["regime"] = stress_to_regime.get(stress, f"stress_{stress:g}")
        tagged.append(nr)

    out: list[dict[str, Any]] = []
    grouped = _group_rows(tagged, ["regime", "policy"])
    regimes = sorted({str(r["regime"]) for r in tagged})
    for regime in regimes:
        key_async = (regime, "async_only")
        key_swarm = (regime, "swarm")
        key_sync = (regime, "always_sync")
        if key_async not in grouped or key_swarm not in grouped or key_sync not in grouped:
            continue

        def _metric_mean(rows_sub: list[dict[str, Any]], metric: str) -> float:
            vals = [float(_to_float(r.get(metric, 0.0), 0.0)) for r in rows_sub]
            return _mean(vals)

        def _pair_id(row: dict[str, Any]) -> int:
            if "seed_run_id" in row:
                return int(_to_float(row.get("seed_run_id", 0.0), 0.0))
            return int(_to_float(row.get("run_id", 0.0), 0.0))

        def _paired_deltas(
            left_rows: list[dict[str, Any]],
            right_rows: list[dict[str, Any]],
            metric: str,
        ) -> list[float]:
            left = {_pair_id(r): float(_to_float(r.get(metric, 0.0), 0.0)) for r in left_rows}
            right = {_pair_id(r): float(_to_float(r.get(metric, 0.0), 0.0)) for r in right_rows}
            common = sorted(set(left).intersection(right))
            return [left[k] - right[k] for k in common]

        async_rows = grouped[key_async]
        swarm_rows = grouped[key_swarm]
        sync_rows = grouped[key_sync]

        async_means = {m: _metric_mean(async_rows, m) for m in CORE_CLAIM_METRICS}
        swarm_means = {m: _metric_mean(swarm_rows, m) for m in CORE_CLAIM_METRICS}
        sync_means = {m: _metric_mean(sync_rows, m) for m in CORE_CLAIM_METRICS}

        d_bounce = _paired_deltas(async_rows, swarm_rows, "bounce_rate")
        d_cascade2 = _paired_deltas(async_rows, swarm_rows, "cascade_run_ge_2")
        d_cost = _paired_deltas(sync_rows, swarm_rows, "C_load_per_ticket")
        d_f1 = _paired_deltas(swarm_rows, async_rows, "trigger_f1")
        d_missed = _paired_deltas(async_rows, swarm_rows, "missed_escalation_rate")
        n_pairs = min(len(d_bounce), len(d_cascade2), len(d_cost), len(d_f1), len(d_missed))

        d_bounce_lo, d_bounce_hi = _bootstrap_ci(d_bounce, seed=5100 + len(out)) if d_bounce else (0.0, 0.0)
        d_c2_lo, d_c2_hi = _bootstrap_ci(d_cascade2, seed=5200 + len(out)) if d_cascade2 else (0.0, 0.0)
        d_cost_lo, d_cost_hi = _bootstrap_ci(d_cost, seed=5300 + len(out)) if d_cost else (0.0, 0.0)
        d_f1_lo, d_f1_hi = _bootstrap_ci(d_f1, seed=5400 + len(out)) if d_f1 else (0.0, 0.0)
        d_miss_lo, d_miss_hi = _bootstrap_ci(d_missed, seed=5500 + len(out)) if d_missed else (0.0, 0.0)

        pass_reliability = (d_f1_lo > 0.0) and (d_miss_lo > 0.0)
        pass_cascade = (d_bounce_lo > 0.0) and (d_c2_lo >= 0.0)
        pass_cost = d_cost_lo > 0.0
        claim_supported = pass_reliability and pass_cascade and pass_cost

        out.append(
            {
                "regime": regime,
                "n_paired_runs": n_pairs,
                "swarm_trigger_f1_mean": swarm_means["trigger_f1"],
                "swarm_missed_escalation_rate_mean": swarm_means["missed_escalation_rate"],
                "swarm_bounce_rate_mean": swarm_means["bounce_rate"],
                "swarm_cascade_run_ge_2_mean": swarm_means["cascade_run_ge_2"],
                "swarm_C_load_per_ticket_mean": swarm_means["C_load_per_ticket"],
                "swarm_vs_async_f1_gain_mean": _mean(d_f1),
                "swarm_vs_async_f1_gain_ci95_low": d_f1_lo,
                "swarm_vs_async_f1_gain_ci95_high": d_f1_hi,
                "swarm_vs_async_missed_reduction_mean": _mean(d_missed),
                "swarm_vs_async_missed_reduction_ci95_low": d_miss_lo,
                "swarm_vs_async_missed_reduction_ci95_high": d_miss_hi,
                "swarm_vs_async_bounce_reduction_mean": _mean(d_bounce),
                "swarm_vs_async_bounce_reduction_ci95_low": d_bounce_lo,
                "swarm_vs_async_bounce_reduction_ci95_high": d_bounce_hi,
                "swarm_vs_async_cascade_ge_2_reduction_mean": _mean(d_cascade2),
                "swarm_vs_async_cascade_ge_2_reduction_ci95_low": d_c2_lo,
                "swarm_vs_async_cascade_ge_2_reduction_ci95_high": d_c2_hi,
                "swarm_vs_always_sync_cost_reduction_mean": _mean(d_cost),
                "swarm_vs_always_sync_cost_reduction_ci95_low": d_cost_lo,
                "swarm_vs_always_sync_cost_reduction_ci95_high": d_cost_hi,
                "claim_pass_reliability": int(pass_reliability),
                "claim_pass_cascade": int(pass_cascade),
                "claim_pass_cost": int(pass_cost),
                "claim_supported": int(claim_supported),
            }
        )
    return out


def generate_resources(in_dir: str = "results", out_dir: str = "results/resources") -> None:
    src = Path(in_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Remove stale legacy artifacts from prior resource schema versions.
    for legacy_name in [
        "paper_table_policy_stress.csv",
        "paper_table_policy_stress_coupling.csv",
        "swarm_delta_vs_async.csv",
        "tradespace_points.csv",
        "pareto_frontier.csv",
        "plots_skipped.txt",
    ]:
        legacy_path = out / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()

    runs_raw = _read_csv(src / "runs_summary.csv")
    runs = _coerce_run_rows(runs_raw)
    if not runs:
        raise RuntimeError(f"No run rows found at {src / 'runs_summary.csv'}")

    mode_regime = _build_mode_regime_summary(runs)
    _write_csv(
        out / "mode_regime_summary.csv",
        mode_regime,
        fieldnames=list(mode_regime[0].keys()),
    )

    naive_vs_swarm = _build_naive_vs_swarm_ablation(mode_regime)
    if naive_vs_swarm:
        _write_csv(
            out / "naive_vs_swarm_ablation.csv",
            naive_vs_swarm,
            fieldnames=list(naive_vs_swarm[0].keys()),
        )

    fixed_cost_signal_capture = _build_signal_capture_fixed_cost(runs)
    if fixed_cost_signal_capture:
        _write_csv(
            out / "signal_capture_fixed_cost.csv",
            fixed_cost_signal_capture,
            fieldnames=list(fixed_cost_signal_capture[0].keys()),
        )

    core_claim = _build_core_claim_evidence(runs)
    if core_claim:
        _write_csv(
            out / "core_claim_evidence.csv",
            core_claim,
            fieldnames=list(core_claim[0].keys()),
        )
