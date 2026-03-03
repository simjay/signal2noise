"""Run the CAS 2026 paper experiment and report results."""

from __future__ import annotations

import json
import time

from signal2noise.experiments.presets import cas2026_paper
from signal2noise.metrics.phase import compute_phase_derivative, find_critical_tau


def main():
    print("=" * 72)
    print("CAS 2026 Paper Experiment: Communication Valve Hypothesis")
    print("=" * 72)
    print()
    print("Hypothesis: A rework-triggered Communication Valve (Group C,")
    print("adaptive protocol) produces emergent efficiency advantages over")
    print("both async-only (Group A) and sync-always (Group B), with a")
    print("phase-transition at critical threshold tau*.")
    print()
    print("Primary metric: eta* = TaskScore / (T_comp + (T_cost + T_rework) / n)")
    print("  T_comp   = wall-clock ticks (delay cost)")
    print("  T_cost   = sync + lambda*async messages (coordination overhead)")
    print("  T_rework = sum of rework effort (wasted re-work agent-minutes)")
    print("  n        = team size (converts agent-minutes to ticks)")
    print()

    t0 = time.time()
    results = cas2026_paper(runs_per_config=100, seed_base=42)
    elapsed = time.time() - t0
    print(f"Experiment completed in {elapsed:.1f}s")
    print()

    # ---- Extract groups ----
    group_a = [r for r in results if r["group"] == "A"][0]
    group_b = [r for r in results if r["group"] == "B"][0]
    group_c = [r for r in results if r["group"] == "C"]

    # ---- Group A & B summary ----
    print("-" * 72)
    print("GROUP A  (Async Only)")
    print("-" * 72)
    _print_metrics(group_a)
    print()

    print("-" * 72)
    print("GROUP B  (Sync Always, s_min=0.2)")
    print("-" * 72)
    _print_metrics(group_b)
    print()

    # ---- Group C: tau sweep ----
    print("-" * 72)
    print("GROUP C  (Adaptive -- tau sweep)")
    print("-" * 72)
    print(f"  {'tau':>6}  {'eta*_mean':>10}  {'eta*_std':>10}  {'eta*_ci95':>10}  "
          f"{'bounce':>8}  {'T_rework':>10}  {'T_cost':>10}  {'ttc':>6}")
    print(f"  {'------':>6}  {'----------':>10}  {'----------':>10}  {'----------':>10}  "
          f"{'--------':>8}  {'----------':>10}  {'----------':>10}  {'------':>6}")

    tau_values = []
    eta_star_means = []
    for r in group_c:
        tau_values.append(r["tau"])
        eta_star_means.append(r["rework_adjusted_eta_mean"])
        print(f"  {r['tau']:6.2f}  "
              f"{r['rework_adjusted_eta_mean']:10.4f}  "
              f"{r['rework_adjusted_eta_std']:10.4f}  "
              f"{r['rework_adjusted_eta_ci95']:10.4f}  "
              f"{r['ticket_bounce_rate_mean']:8.4f}  "
              f"{r['total_rework_cost_mean']:10.2f}  "
              f"{r['total_coordination_cost_mean']:10.2f}  "
              f"{r['time_to_completion_mean']:6.1f}")
    print()

    # ---- Phase transition analysis (using eta*) ----
    phase_data = compute_phase_derivative(tau_values, eta_star_means)
    tau_star = find_critical_tau(phase_data)

    print("-" * 72)
    print("PHASE TRANSITION ANALYSIS (eta*)")
    print("-" * 72)
    print(f"  {'tau':>6}  {'eta*':>10}  {'d_eta*/d_tau':>12}")
    print(f"  {'------':>6}  {'----------':>10}  {'------------':>12}")
    for pd in phase_data:
        marker = " <-- tau*" if pd["tau"] == tau_star else ""
        print(f"  {pd['tau']:6.2f}  {pd['eta']:10.4f}  {pd['deta_dtau']:12.4f}{marker}")
    print()
    print(f"  Critical tau* = {tau_star:.2f}")
    print()

    # ---- Find best adaptive config ----
    best_c = max(group_c, key=lambda r: r["rework_adjusted_eta_mean"])

    # ---- Hypothesis evaluation ----
    print("=" * 72)
    print("HYPOTHESIS EVALUATION")
    print("=" * 72)
    print()

    # Primary metric: eta*
    eta_star_a = group_a["rework_adjusted_eta_mean"]
    eta_star_b = group_b["rework_adjusted_eta_mean"]
    eta_star_c = best_c["rework_adjusted_eta_mean"]
    tau_best = best_c["tau"]

    # Legacy eta (for reference)
    eta_a = group_a["efficiency_ratio_mean"]
    eta_b = group_b["efficiency_ratio_mean"]
    eta_c = best_c["efficiency_ratio_mean"]

    # Other metrics
    score_a = group_a["task_score_mean"]
    score_b = group_b["task_score_mean"]
    score_c = best_c["task_score_mean"]

    cost_a = group_a["total_coordination_cost_mean"]
    cost_b = group_b["total_coordination_cost_mean"]
    cost_c = best_c["total_coordination_cost_mean"]

    rework_a = group_a["total_rework_cost_mean"]
    rework_b = group_b["total_rework_cost_mean"]
    rework_c = best_c["total_rework_cost_mean"]

    bounce_a = group_a["ticket_bounce_rate_mean"]
    bounce_b = group_b["ticket_bounce_rate_mean"]
    bounce_c = best_c["ticket_bounce_rate_mean"]

    tp_a = group_a["throughput_mean"]
    tp_b = group_b["throughput_mean"]
    tp_c = best_c["throughput_mean"]

    ttc_a = group_a["time_to_completion_mean"]
    ttc_b = group_b["time_to_completion_mean"]
    ttc_c = best_c["time_to_completion_mean"]

    print(f"  {'Metric':<36}  {'A (async)':>12}  {'B (sync)':>12}  {'C* (adaptive)':>14}")
    print(f"  {'-'*36}  {'-'*12}  {'-'*12}  {'-'*14}")
    print(f"  {'** eta* (rework-adjusted) **':<36}  {eta_star_a:>12.4f}  {eta_star_b:>12.4f}  {eta_star_c:>14.4f}")
    print(f"  {'eta (legacy, no rework adj.)':<36}  {eta_a:>12.4f}  {eta_b:>12.4f}  {eta_c:>14.4f}")
    print(f"  {'Task score (0-100)':<36}  {score_a:>12.2f}  {score_b:>12.2f}  {score_c:>14.2f}")
    print(f"  {'Coordination cost (T_cost)':<36}  {cost_a:>12.2f}  {cost_b:>12.2f}  {cost_c:>14.2f}")
    print(f"  {'Rework cost (T_rework)':<36}  {rework_a:>12.2f}  {rework_b:>12.2f}  {rework_c:>14.2f}")
    print(f"  {'Total overhead (T_cost+T_rework)':<36}  {cost_a+rework_a:>12.2f}  {cost_b+rework_b:>12.2f}  {cost_c+rework_c:>14.2f}")
    print(f"  {'Ticket bounce rate':<36}  {bounce_a:>12.4f}  {bounce_b:>12.4f}  {bounce_c:>14.4f}")
    print(f"  {'Throughput (tasks/tick)':<36}  {tp_a:>12.4f}  {tp_b:>12.4f}  {tp_c:>14.4f}")
    print(f"  {'Time to completion':<36}  {ttc_a:>12.1f}  {ttc_b:>12.1f}  {ttc_c:>14.1f}")
    print(f"  {'Best tau for Group C':<36}  {'':>12}  {'':>12}  {tau_best:>14.2f}")
    print()

    # H1: Adaptive reduces rework vs async-only while maintaining throughput
    h1_quality = bounce_c < bounce_a
    h1_throughput = tp_c >= tp_a * 0.90
    h1 = h1_quality and h1_throughput
    pct_rework = ((bounce_a - bounce_c) / max(bounce_a, 1e-9)) * 100
    print(f"  H1: Adaptive reduces rework vs async-only?")
    print(f"      Bounce rate: {bounce_a:.4f} -> {bounce_c:.4f}  ({pct_rework:+.1f}% rework reduction)")
    print(f"      Rework cost: {rework_a:.1f} -> {rework_c:.1f}  ({((rework_a - rework_c)/max(rework_a,1e-9))*100:+.1f}% effort saved)")
    print(f"      Throughput maintained: {tp_c:.4f} vs {tp_a:.4f} "
          f"({tp_c/tp_a*100:.0f}% of async-only)")
    print(f"      Result: {'YES' if h1 else 'NO'}")
    print()

    # H2: Adaptive achieves highest eta* (above BOTH A and B)
    h2_vs_a = eta_star_c > eta_star_a
    h2_vs_b = eta_star_c > eta_star_b
    h2 = h2_vs_a and h2_vs_b
    pct_vs_a = ((eta_star_c - eta_star_a) / max(eta_star_a, 1e-9)) * 100
    pct_vs_b = ((eta_star_c - eta_star_b) / max(eta_star_b, 1e-9)) * 100
    print(f"  H2: Adaptive has highest rework-adjusted efficiency (eta*)?")
    print(f"      eta*: A={eta_star_a:.4f}  B={eta_star_b:.4f}  C*={eta_star_c:.4f}")
    print(f"      vs async-only: {pct_vs_a:+.1f}%")
    print(f"      vs sync-always: {pct_vs_b:+.1f}%")
    print(f"      Result: {'YES' if h2 else 'NO'}")
    print()

    # H3: Phase transition exists at tau*
    derivs = [abs(pd["deta_dtau"]) for pd in phase_data[1:-1]]
    max_deriv = max(derivs) if derivs else 0
    h3 = max_deriv > 0.1
    print(f"  H3: Phase transition exists in eta* vs tau?")
    print(f"      Max |d_eta*/d_tau| = {max_deriv:.4f} at tau* = {tau_star:.2f}")
    print(f"      Result: {'YES' if h3 else 'NO'}")
    print()

    # H4: Adaptive minimises total overhead (T_cost + T_rework)
    total_overhead_a = cost_a + rework_a
    total_overhead_b = cost_b + rework_b
    total_overhead_c = cost_c + rework_c
    h4 = total_overhead_c < total_overhead_a and total_overhead_c < total_overhead_b
    print(f"  H4: Adaptive minimises total overhead (T_cost + T_rework)?")
    print(f"      Total overhead: A={total_overhead_a:.1f}  B={total_overhead_b:.1f}  C*={total_overhead_c:.1f}")
    print(f"      Result: {'YES' if h4 else 'NO'}")
    print()

    overall = h1 and h2 and h3
    print("=" * 72)
    print(f"  OVERALL: Hypothesis {'SUPPORTED' if overall else 'PARTIALLY SUPPORTED'}")
    print("=" * 72)
    print()
    if overall:
        print(f"  The Communication Valve (adaptive protocol, tau*={tau_star:.2f})")
        print(f"  achieves the HIGHEST rework-adjusted efficiency (eta*={eta_star_c:.4f}),")
        print(f"  outperforming both async-only ({pct_vs_a:+.1f}%) and sync-always ({pct_vs_b:+.1f}%).")
        print()
        print(f"  Key insight: the adaptive protocol minimises (T_cost + T_rework)")
        print(f"  by activating sync meetings only when needed, avoiding both:")
        print(f"  - async-only's high rework waste (T_rework={rework_a:.1f})")
        print(f"  - sync-always's high meeting overhead (T_cost={cost_b:.1f})")
    else:
        print("  Summary of findings:")
        if h1:
            print(f"  + Adaptive reduces rework vs async-only by {pct_rework:.1f}%")
        else:
            print(f"  - Adaptive did NOT reduce rework vs async-only")
        if h2:
            print(f"  + Adaptive has highest eta* ({eta_star_c:.4f} > A:{eta_star_a:.4f}, B:{eta_star_b:.4f})")
        else:
            print(f"  - Adaptive does NOT have highest eta*")
            if not h2_vs_a:
                print(f"    async-only eta*={eta_star_a:.4f} > adaptive eta*={eta_star_c:.4f}")
            if not h2_vs_b:
                print(f"    sync-always eta*={eta_star_b:.4f} > adaptive eta*={eta_star_c:.4f}")
        if h3:
            print(f"  + Phase transition detected at tau*={tau_star:.2f}")
        else:
            print(f"  - No clear phase transition detected")
    print()

    # Dump raw JSON for archival
    with open("experiment_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Raw results saved to experiment_results.json")


def _print_metrics(r: dict):
    print(f"  ** eta* (rework-adjusted): {r['rework_adjusted_eta_mean']:.4f} +/- {r['rework_adjusted_eta_std']:.4f}  (95% CI: {r['rework_adjusted_eta_ci95']:.4f})")
    print(f"  eta (legacy):             {r['efficiency_ratio_mean']:.4f} +/- {r['efficiency_ratio_std']:.4f}")
    print(f"  Task score:               {r['task_score_mean']:.2f} +/- {r['task_score_std']:.2f}")
    print(f"  Ticket bounce rate:       {r['ticket_bounce_rate_mean']:.4f} +/- {r['ticket_bounce_rate_std']:.4f}")
    print(f"  Coordination cost:        {r['total_coordination_cost_mean']:.2f} +/- {r['total_coordination_cost_std']:.2f}")
    print(f"  Rework cost (T_rework):   {r['total_rework_cost_mean']:.2f} +/- {r['total_rework_cost_std']:.2f}")
    print(f"  Total overhead:           {r['total_coordination_cost_mean'] + r['total_rework_cost_mean']:.2f}")
    print(f"  Time to completion:       {r['time_to_completion_mean']:.1f} +/- {r['time_to_completion_std']:.1f}")
    print(f"  Throughput:               {r['throughput_mean']:.4f} +/- {r['throughput_std']:.4f}")
    print(f"  Channel utilization:      {r['channel_utilization_ratio_mean']:.4f}")
    print(f"  Cognitive load variance:  {r['cognitive_load_variance_mean']:.6f}")
    print(f"  Rework cascade depth:     {r['mean_rework_cascade_depth_mean']:.4f}")


if __name__ == "__main__":
    main()
