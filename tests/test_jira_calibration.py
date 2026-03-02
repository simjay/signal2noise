from __future__ import annotations

import csv
import json
from pathlib import Path

from signal2noise.jira_calibration import derive_from_jira_sql


def test_derive_from_jira_sql(tmp_path: Path) -> None:
    sql = tmp_path / "jira.sql"
    sql.write_text(
        "\n".join(
            [
                "INSERT INTO jira_issue_report (id, created, description, key, priority, project, project_name, repositoryname, resolution, resolved, status, title, type, updated, votes, watchers, assignee_id, reporter_id) VALUES (1, '2020-01-01 00:00:00', 'line1",
                "line2', 'P-1', 'Major', 'P', 'Project P', 'R', 'Fixed', '2020-01-02 00:00:00', 'Closed', 't1', 'Bug', '2020-01-02 00:00:00', 0, 0, NULL, 10);",
                "INSERT INTO jira_issue_report (id, created, description, key, priority, project, project_name, repositoryname, resolution, resolved, status, title, type, updated, votes, watchers, assignee_id, reporter_id) VALUES (2, '2020-01-01 00:00:00', '', 'P-2', 'Major', 'P', 'Project P', 'R', 'Fixed', '2020-01-03 00:00:00', 'Closed', 't2', 'Bug', '2020-01-03 00:00:00', 0, 0, NULL, 11);",
                "INSERT INTO jira_issue_changelog_item (id, date, field_name, new_value, original_value, author_id, issue_report_id) VALUES (101, '2020-01-02 01:00:00', 'status', 'In Progress', 'Closed', 1, 1);",
                "INSERT INTO jira_issue_changelog_item (id, date, field_name, new_value, original_value, author_id, issue_report_id) VALUES (102, '2020-01-04 00:00:00', 'status', 'In Progress', 'Closed', 1, 2);",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_csv = tmp_path / "jira_calibration.csv"
    out_stats = tmp_path / "stats.json"
    out_summary = tmp_path / "summary.md"

    stats = derive_from_jira_sql(sql, out_csv, out_stats, out_summary, window_days=3)

    assert out_csv.exists()
    assert out_stats.exists()
    assert out_summary.exists()
    assert stats["n_issues_resolved"] == 2

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_id = {int(r["root_issue_id"]): r for r in rows}

    assert int(by_id[1]["post_done_change"]) == 1
    assert int(by_id[1]["rework"]) == 1
    assert int(by_id[1]["cascade_size"]) == 1

    data = json.loads(out_stats.read_text(encoding="utf-8"))
    assert "calibrated_params" in data
    assert data["window_days"] == 3
