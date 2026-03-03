from __future__ import annotations

import argparse
import copy
import csv
import itertools
import math
from pathlib import Path
from typing import Any

from signal2noise.calibration import calibrate_from_csv, write_calibrated
from signal2noise.config import dict_to_config, load_config_file, save_json, set_nested
from signal2noise.engine import run_many
from signal2noise.jira_calibration import derive_from_jira_sql
from signal2noise.logger import write_cascades, write_events, write_runs_summary, write_timeseries
from signal2noise.resources import generate_resources


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_generic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("\n")
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_common_outputs(
    out: Path,
    runs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cascades: list[dict[str, Any]],
    timeseries: list[dict[str, Any]],
    write_events_flag: bool,
) -> None:
    for legacy_name in ["agg_by_policy.csv", "phase_diagram.csv", "cascade_histogram.csv", "timeseries_sample_run.csv"]:
        legacy_path = out / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()

    write_runs_summary(out / "runs_summary.csv", runs)
    write_cascades(out / "cascades.csv", cascades)
    write_timeseries(out / "timeseries.csv", timeseries)
    if write_events_flag:
        write_events(out / "events.csv", events)


def _run_single(raw_cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cfg = dict_to_config(raw_cfg)
    return run_many(cfg)


def _expand_grid(multiple_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    sweep_grid = multiple_cfg.get("sweep", {})
    if not isinstance(sweep_grid, dict) or not sweep_grid:
        sweep_combos: list[dict[str, Any]] = [{}]
    else:
        keys = list(sweep_grid.keys())
        values = [v if isinstance(v, list) else [v] for v in sweep_grid.values()]
        sweep_combos = [dict(zip(keys, combo)) for combo in itertools.product(*values)]

    ladder = multiple_cfg.get("stress_ladder", {})
    if not isinstance(ladder, dict) or not ladder.get("enabled", False):
        return sweep_combos

    multipliers_raw = ladder.get("multipliers", [1.0])
    if not isinstance(multipliers_raw, list) or not multipliers_raw:
        multipliers_raw = [1.0]
    multipliers = [float(m) for m in multipliers_raw]

    parameters = ladder.get("parameters", {})
    if not isinstance(parameters, dict) or not parameters:
        return sweep_combos

    stress_profiles: list[dict[str, Any]] = []
    for m in multipliers:
        profile: dict[str, Any] = {"stress_multiplier": m}
        for dotted_key, spec in parameters.items():
            if isinstance(spec, dict):
                if "anchor" not in spec:
                    raise ValueError(f"stress_ladder.parameters.{dotted_key} must contain 'anchor'")
                anchor = float(spec["anchor"])
                low = float(spec.get("min", -math.inf))
                high = float(spec.get("max", math.inf))
            else:
                anchor = float(spec)
                low = -math.inf
                high = math.inf
            value = max(low, min(high, anchor * m))
            profile[str(dotted_key)] = value
        stress_profiles.append(profile)

    out: list[dict[str, Any]] = []
    for base in sweep_combos:
        for profile in stress_profiles:
            merged = dict(base)
            for k, v in profile.items():
                if k in merged and merged[k] != v:
                    raise ValueError(
                        f"Conflict for parameter '{k}' between sweep and stress_ladder; "
                        "remove one source of truth."
                    )
                merged[k] = v
            out.append(merged)
    return out


def _run_multiple(multiple_cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if "base_config" in multiple_cfg:
        base_cfg_raw = load_config_file(multiple_cfg["base_config"])
    else:
        base_cfg_raw = copy.deepcopy(multiple_cfg)
        base_cfg_raw.pop("sweep", None)

    all_runs: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    all_cascades: list[dict[str, Any]] = []
    all_timeseries: list[dict[str, Any]] = []

    run_id_offset = 0
    for combo_idx, combo in enumerate(_expand_grid(multiple_cfg)):
        cfg_raw = copy.deepcopy(base_cfg_raw)
        for k, v in combo.items():
            set_nested(cfg_raw, k, v)

        cfg = dict_to_config(cfg_raw)
        runs, events, cascades, timeseries = run_many(cfg)

        run_id_map: dict[int, int] = {}
        for r in runs:
            old = int(r["run_id"])
            new = old + run_id_offset
            run_id_map[old] = new
            r["run_id"] = new
            r["seed_run_id"] = old
            r["multiple_point"] = combo_idx
            for k, v in combo.items():
                r[k] = v
            all_runs.append(r)

        for e in events:
            e["run_id"] = run_id_map[int(e["run_id"])]
            for k, v in combo.items():
                e[k] = v
            all_events.append(e)

        for c in cascades:
            c["run_id"] = run_id_map[int(c["run_id"])]
            c["multiple_point"] = combo_idx
            for k, v in combo.items():
                c[k] = v
            all_cascades.append(c)

        for ts in timeseries:
            old_ts_run_id = int(ts["run_id"])
            ts["run_id"] = run_id_map[old_ts_run_id]
            ts["seed_run_id"] = old_ts_run_id
            ts["multiple_point"] = combo_idx
            for k, v in combo.items():
                ts[k] = v
            all_timeseries.append(ts)

        run_id_offset += cfg.n_runs

    return all_runs, all_events, all_cascades, all_timeseries


def run_command(config_path: str, out_dir: str = "results", write_events_flag: bool = True) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_cfg = load_config_file(config_path)
    is_multiple = isinstance(raw_cfg, dict) and "sweep" in raw_cfg

    if is_multiple:
        runs, events, cascades, timeseries = _run_multiple(raw_cfg)
        _write_common_outputs(out, runs, events, cascades, timeseries, write_events_flag)
        save_json(out / "multiple_config_resolved.json", raw_cfg)
    else:
        runs, events, cascades, timeseries = _run_single(raw_cfg)
        _write_common_outputs(out, runs, events, cascades, timeseries, write_events_flag)
        save_json(out / "config_resolved.json", raw_cfg)


def analyze_command(in_dir: str, out_dir: str = "results") -> None:
    # Lean analysis delegates to paper/resource table generation.
    generate_resources(in_dir, out_dir)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="s2n", description="Rework propagation ABM simulator")
    sub = p.add_subparsers(dest="command", required=True)

    runp = sub.add_parser("run", help="Run single or multiple experiment config")
    runp.add_argument("--config", required=True)
    runp.add_argument("--out", default="results", help="Output directory (default: results)")
    runp.add_argument("--no-events", action="store_true")

    ap = sub.add_parser("analyze", help="Generate lean summary tables from prior outputs")
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", default="results", help="Output directory (default: results)")

    cp = sub.add_parser("calibrate", help="Fit baseline parameters from external CSV")
    cp.add_argument("--in", dest="in_csv", required=True)
    cp.add_argument("--out", required=True)

    jp = sub.add_parser("calibrate-jira", help="Build calibration dataset directly from Jira SQL dump")
    jp.add_argument("--sql", required=True, help="Path to emotion_dataset_jira.sql")
    jp.add_argument("--out-csv", required=True, help="Derived CSV path (e.g., data/derived/jira_calibration.csv)")
    jp.add_argument("--out-stats", required=True, help="Stats JSON path (e.g., results/calibration_stats.json)")
    jp.add_argument("--out-summary", required=True, help="Summary Markdown path (e.g., results/calibration_summary.md)")
    jp.add_argument("--window-days", type=int, default=3, help="Cascade proxy horizon in days")

    rp = sub.add_parser("resources", help="Generate paper tables and tradespace resources from run outputs")
    rp.add_argument("--in", dest="in_dir", default="results", help="Run output directory (default: results)")
    rp.add_argument(
        "--out",
        default="results/resources",
        help="Resources output directory (default: results/resources)",
    )

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        run_command(args.config, args.out, write_events_flag=not args.no_events)
    elif args.command == "analyze":
        analyze_command(args.in_dir, args.out)
    elif args.command == "calibrate":
        calibrated = calibrate_from_csv(args.in_csv)
        write_calibrated(args.out, calibrated)
    elif args.command == "calibrate-jira":
        derive_from_jira_sql(
            sql_path=args.sql,
            out_csv=args.out_csv,
            out_stats_json=args.out_stats,
            out_summary_md=args.out_summary,
            window_days=args.window_days,
        )
    elif args.command == "resources":
        generate_resources(args.in_dir, args.out)
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
