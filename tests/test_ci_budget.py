# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-338: the aggregate jobs report each job time against the time budget and never fail."""

import io
import json
import re
from pathlib import Path

import pytest

from tools.ci_budget import complete_jobs, main, report

ROOT = Path(__file__).parents[1]


def _job(name: str, created: str, started: str | None, completed: str | None) -> str:
    day = "2026-11-09T10:"
    return json.dumps(
        {
            "name": name,
            "created_at": f"{day}{created}Z",
            "started_at": started and f"{day}{started}Z",
            "completed_at": completed and f"{day}{completed}Z",
        }
    )


LINES = [
    _job("Tests: collectors", "00:00", "03:00", "11:30"),
    _job("Lint, types and architecture", "00:00", "00:00", "05:30"),
    _job("All checks passed", "11:30", "11:40", None),
    "",
]


def test_only_complete_jobs_count_and_the_longest_comes_first() -> None:
    jobs = complete_jobs(LINES)
    assert [(job.name, job.queue, job.run) for job in jobs] == [
        ("Tests: collectors", 3.0, 8.5),
        ("Lint, types and architecture", 0.0, 5.5),
    ]


def test_a_job_and_the_critical_path_over_the_budget_are_warnings() -> None:
    table, warnings = report(complete_jobs(LINES), job_minutes=7, path_minutes=8)
    assert table.startswith("Critical path without queue: 8.5 min (budget 8). Longest queue: 3.0")
    assert "| Tests: collectors | 8.5 | 3.0 |" in table
    assert warnings == [
        "Tests: collectors ran 8.5 min; the budget of a job is 7 min.",
        "The critical path is 8.5 min; the budget is 8 min.",
    ]
    assert report(complete_jobs(LINES), job_minutes=9, path_minutes=9)[1] == []


def test_the_tool_never_fails_and_writes_the_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    summary = tmp_path / "summary.md"
    for lines in (LINES, []):
        monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines)))
        argv = ["--job-minutes", "7", "--path-minutes", "10", "--summary", str(summary)]
        assert main(argv) == 0
    out = capsys.readouterr().out
    assert "::warning title=Time budget (AD-338)::Tests: collectors ran 8.5 min" in out
    assert "::warning title=Time budget (AD-338)::No complete job" in out
    assert summary.read_text().count("| Job | Run (min) | Queue (min) |") == 1


@pytest.mark.parametrize(
    ("workflow", "aggregate", "limits"),
    [
        ("ci.yml", "check", "--job-minutes 7 --path-minutes 10"),
        ("full-verification.yml", "verified", "--job-minutes 15 --path-minutes 30"),
    ],
)
def test_each_aggregate_reports_its_run_before_it_requires_every_job(
    workflow: str, aggregate: str, limits: str
) -> None:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    body = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    jobs = dict(zip(body[1::2], body[2::2], strict=True))
    steps = jobs[aggregate]
    assert "      actions: read\n" in steps
    budget = steps.index("tools/ci_budget.py")
    assert steps.index("continue-on-error: true") < budget < steps.index("run: |")
    assert f"python3 tools/ci_budget.py {limits}" in steps
