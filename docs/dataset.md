# Dataset Analysis

Calibration data for the simulation is derived from a public Jira issue-tracking dataset.

## Source

- Raw: `data/jira-social-repository/emotion_dataset_jira.sql`
- Derived features: `data/derived/jira_calibration.csv`

## Coverage

| Stat | Value |
|------|-------|
| Resolved issues | 586,084 |
| Time span | 2002-07-16 to 2014-01-06 |
| `fix_time` availability | 99.997% |

## Derived columns

| Column | Definition |
|--------|-----------|
| `fix_time` | Days from issue created to resolved |
| `rework` | 1 if issue was reopened after done/resolved, else 0 |
| `post_done_change` | 1 if issue changed after done/resolved, else 0 |
| `cascade_size` | Proxy count of nearby reopen events in same project/time window |

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
- All reworked issues had a post-done change (`P(post_done_change | rework) = 1.0`)

### Cascades are extremely sparse

- Zero-cascade rows: **99.918%**
- Only 478 rows (0.08%) have cascade >= 1
- Max cascade observed: 44
- `P(cascade >= 1 | post_done_change) = 0.14%`
- `P(rework | cascade >= 1) = 31.8%`

### Interpretation

Many issues keep changing after "done," but only a tiny fraction lead to actual rework. Cascade proxy values are almost always zero, so direct fitting produces very low baseline propagation. Fix-time has a huge long tail that does not map cleanly to per-task simulation effort.

## Extracted parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| `rework_rate` | 0.000495 | Direct from data |
| `mean_cascade_size` | 0.00380 | Direct from data |
| `post_done_change_rate` | 0.5977 | Direct from data |
| `p_change_per_day` | 0.001531 | SQL pass using active done-days |
| `task_effort_distribution` | lognormal(mean=1.93, sigma=3.57) | Calibrated candidate |
| `defect_rate` | fixed 0.001 | Calibrated candidate |
| `base_propagation` | 0.05 | Floor-clamped |

## Adjustments for simulation

The raw/calibrated values needed several adjustments before use:

**`p_change`**: The row-average post-done change rate (0.5977) is not a per-tick probability. We use the per-day hazard rate (0.001531) instead, which is appropriate for simulation tick scale.

**`base_propagation`**: Kept at the floor value (0.05) because the cascade proxy is too sparse for meaningful fitting.

**`defect_rate`**: Changed from fixed 0.001 to `beta(a=2.0, b=20.0)` to maintain heterogeneity across agents and avoid a near-zero defect regime.

**`task_effort_distribution`**: Changed from lognormal(1.93, 3.57) to lognormal(2.0, 0.35). The Jira lifecycle times are much broader than per-task coding effort; direct use would produce unreasonable run durations.

**Experiment structure parameters** (team size, task count, tick count, sweep grid) are design choices, not Jira-fitted values.
