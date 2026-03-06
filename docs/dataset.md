# Dataset Analysis

This document describes the public Jira dataset used to calibrate
simulation parameters: derived columns, key findings, and extracted
values.

## Source

- Raw: `data/jira-social-repository/emotion_dataset_jira.sql`
- Derived features: `data/derived/jira_calibration.csv`

## Derived columns

| Column | Definition |
|--------|-----------|
| `fix_time` | Days from issue created to resolved |
| `rework` | 1 if issue was reopened after done/resolved, else 0 |
| `post_done_change` | 1 if issue changed after done/resolved, else 0 |
| `cascade_size` | Count of other reopen events in the same project within a 7-day window; a proxy for propagation (direct causal links are unavailable) |

## Coverage

| Stat | Value |
|------|-------|
| Resolved issues | 586,084 |
| Time span | 2002-07-16 to 2014-01-06 |
| `fix_time` availability | 99.997% (fraction of rows with non-null value) |

## Key findings

### Fix time is heavily skewed

| Percentile | Days |
|-----------|------|
| Mean | 150.88 |
| Median (p50) | 12.02 |
| p90 | 477.95 |
| p95 | 832.01 |
| p99 | 1794.70 |
| Max | 4077.20 |

- 26% of issues resolve within 1 day
- 44% within 7 days
- 61% within 30 days
- 13% take longer than 1 year

### Rework is rare

- Rework rate: **0.0495%** (290 out of 586K rows)
- Too sparse to fit propagation parameters directly

### Post-done changes are common

- Post-done change rate: **59.77%** (350,316 rows)
- Every reworked issue also had a post-done change (`P(post_done_change | rework) = 1.0`)

### Cascades are extremely sparse

- Zero-cascade rows: **99.918%**
- Only 478 rows (0.08%) have cascade >= 1
- Max cascade observed: 44
- Of issues with a post-done change, only 0.14% have a cascade
- Of issues with cascade >= 1, 31.8% were reworked

### Interpretation

Most issues keep changing after "done," but very few lead to actual
rework. Cascade values are almost always zero, so direct fitting
produces very low baseline propagation. Fix-time has a long tail that
does not map cleanly to per-task simulation effort.

## Extracted parameters and simulation usage

Not all extracted values are used as simulation inputs. Some are
descriptive only, some are used directly, and some were replaced to suit
the simulation's mechanics. See [experiment.md](experiment.md) for model
definitions of *tick*, *agent*, and *cognitive load*.

| Parameter | Value (from data) | Used in sim? | Simulation value | Why | What it does | Unit |
|-----------|-------------------|--------------|------------------|-----|--------------|------|
| `rework_rate` | 0.000495 | No | - | Descriptive. Rework emerges from `base_error_rate`, `p_signal_change`, and `p_cascade`. | Fraction of issues reopened after done | - |
| `mean_cascade_size` | 0.00380 | No | - | Descriptive. Cascades controlled by `p_cascade` and `max_cascade_depth`. | Average cascade proxy per issue | - |
| `post_done_change_rate` | 0.5977 | No | - | Aggregate rate, not a per-tick probability. See `p_change_per_day`. | Fraction of issues that ever changed after done | - |
| `p_change_per_day` | 0.001531 | Yes | 0.001531 | Daily hazard rate is the correct form for per-tick simulation. Both this and `post_done_change_rate` come from the same data. | Probability a "done" issue changes on a given tick | per tick |
| `base_propagation` | 0.05 (floor-clamped from ~0.004) | Yes | 0.05 | Raw fitted value ~0.004 was too low for observable cascades; floor applied during extraction. | Probability rework propagates to an upstream dependency | per event |
| `defect_rate` | 0.001 (fixed) | Yes (replaced) | beta(a=2.0, b=20.0), E[x]~0.091 | Fixed value gives no agent heterogeneity and near-zero defects. Replaced with a distribution. | Base probability an agent introduces a defect | per validation |
| `task_effort_distribution` | lognormal(mu=1.93, sigma=3.57) | Yes (replaced) | lognormal(mu=2.0, sigma=0.35) | Fitted sigma reflects Jira lifecycle times (days to years), far broader than per-task coding effort. Tighter sigma concentrates values around exp(2.0) ~ 7.4. | Work units to complete a task | work units |

**Experiment structure parameters** (team size, task count, tick count, sweep grid) are design choices, not Jira-fitted values.
