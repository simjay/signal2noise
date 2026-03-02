# Jira Dataset Analysis for Simulation Settings

## 1) Deep analysis of the Jira dataset

Source used:
- `data/jira-social-repository/emotion_dataset_jira.sql` (raw)
- `data/derived/jira_calibration.csv` (derived features used for calibration)

Dataset size and coverage:
- Rows analyzed: **586,084** resolved issues
- Time span (`root_event_time`): **2002-07-16** to **2014-01-06**
- `fix_time` availability: **586,064 / 586,084** rows (99.997% present)

What each derived column means:
- `fix_time`: days from issue created to resolved
- `rework`: 1 if issue was reopened after done/resolved, else 0
- `post_done_change`: 1 if issue changed after done/resolved, else 0
- `cascade_size`: proxy count of nearby reopen events in same project/time window

### Core findings:  
**Fix time is very skewed (long tail).**
- Mean: **150.88 days**
- Median (p50): **12.02 days**
- p90: **477.95 days**, p95: **832.01 days**, p99: **1794.70 days**
- Max: **4077.20 days**
- Share below 1 day: **26.10%**
- Share below 7 days: **44.03%**
- Share below 30 days: **60.95%**
- Share above 365 days: **12.65%**

**Reopen/rework is rare.**
- Rework rate: **0.000495** (0.0495%, 290 rows)

**Post-done changes are common.**
- Post-done change rate: **0.5977** (59.77%, 350,316 rows)

**Cascade proxy is extremely sparse.**
- Mean cascade size: **0.00380**
- p50/p90/p95/p99: **0 / 0 / 0 / 0**
- Zero-cascade rows: **99.918%**
- Rows with cascade >= 1: **478** (0.0816%)
- Max cascade size observed: **44**

Relationships in the derived data:
- `P(cascade >= 1 | post_done_change = 1) = 0.001364` (0.136%)
- `P(cascade >= 1 | post_done_change = 0) = 0.0`
- `P(rework = 1 | post_done_change = 1) = 0.000828` (0.0828%)
- `P(post_done_change = 1 | rework = 1) = 1.0`
- `P(rework = 1 | cascade >= 1) = 0.318`

Interpretation in plain terms:
- The dataset suggests many issues keep changing after “done,” but only a tiny fraction lead to reopen/rework.
- Most cascade proxy values are zero, so if we directly fit propagation from this signal, the model will naturally push toward very low baseline propagation.
- Fix-time has a huge long tail; using it directly as task effort needs care because issue lifecycle time is broader than per-task coding effort.

## 2) What we extract from Jira for experiment parameters

Parameters extracted from Jira-derived data:
- `propagation.p_change`
- `propagation.base_propagation`
- `agent_distributions.defect_rate` (candidate)
- `task_effort_distribution` (candidate)

Direct extracted values (from calibration logic):
- `rework_rate = 0.0004948096`
- `mean_cascade_size = 0.0038015029`
- `post_done_change_rate = 0.5977231933`
- `p_change_per_day = 0.001530666` (from SQL pass using active done-days)

Calibrated candidates produced by code:
- `task_effort_distribution = {kind: lognormal, mean: 1.9292, sigma: 3.5709}`
- `agent_distributions.defect_rate = {kind: fixed, value: 0.001}`
- `propagation.base_propagation = 0.05` (floor-clamped)
- `propagation.p_change` candidate from row mean = `0.5977`, then replaced by per-day proxy in Jira calibration flow

## 3) Adjustments we made before using settings in `config.yaml`

What we changed from raw/calibrated candidates to the current simulation config:

We used **per-day** change hazard for `p_change`.
- Why: row-average `post_done_change` (`0.5977`) is not a per-tick probability and is too large for simulation ticks.
- Final in config: `propagation.p_change = 0.001530666`.  

We kept `base_propagation` at the calibrated floor value.
- Why: cascade proxy is very sparse, so the fitted value bottoms out at the minimum clamp.
- Final in config: `propagation.base_propagation = 0.05`.

We did **not** use the calibrated fixed defect rate directly.
- Calibrated candidate: fixed `0.001`.
- Final in config: `agent_distributions.defect_rate = beta(a=2.0, b=20.0, scale=1.0)`.
- Why: keeps heterogeneity across agents and avoids an almost defect-free regime.

We did **not** use the calibrated effort distribution directly.
- Calibrated candidate: lognormal `(mean=1.9292, sigma=3.5709)`.
- Final in config: lognormal `(mean=2.0, sigma=0.35)`.
- Why: Jira issue lifecycle times are very heavy-tailed and broader than per-task simulation effort; direct use would over-stretch run durations and variance.

We kept experiment-structure settings as design choices, not Jira-fitted values.
- Examples: `team_size`, `n_tasks`, `ticks_per_run`, `policy thresholds`, and `sweep` grid.
- Why: these define the experimental regime to compare policies under controlled conditions.

Summary:
- Jira data is used as an anchor for change/rework/cascade realism.
- We then apply modeling adjustments so parameters are numerically stable and meaningful at simulation tick scale.
