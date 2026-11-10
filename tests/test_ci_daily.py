# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The daily CI line of the merge policy (epic #880) is computed from recorded `gh` JSON."""

from tools.ci_daily import daily_line

DAY = "2026-11-10"


def _run(
    run_id: int,
    workflow: str,
    created: str,
    updated: str,
    branch: str = "feature",
    attempt: int = 1,
    day: str = DAY,
) -> dict[str, object]:
    return {
        "databaseId": run_id,
        "workflowName": workflow,
        "headBranch": branch,
        "createdAt": f"{day}T{created}Z",
        "updatedAt": f"{day}T{updated}Z",
        "attempt": attempt,
    }


RUNS = [
    _run(1, "CI", "10:00:00", "10:10:00"),
    _run(2, "CI", "11:00:00", "11:30:00", attempt=2),
    _run(3, "CI", "12:00:00", "12:20:00"),
    _run(4, "Full verification", "02:17:00", "02:47:00", branch="main"),
    _run(5, "Full verification", "09:00:00", "09:40:00", branch="main"),
    _run(6, "Full verification", "13:00:00", "13:20:00"),
    _run(7, "CI", "10:00:00", "10:05:00", day="2026-11-09"),
]
STARTS = {1: "10:02:00", 2: "11:06:00", 3: "12:04:00"}


def _jobs(run_id: int) -> list[dict[str, str]]:
    start = STARTS[run_id]
    return [
        {"startedAt": f"{DAY}T{start[:-2]}59Z"},
        {"startedAt": f"{DAY}T{start}Z"},
    ]


def test_the_line_has_the_medians_the_counts_and_the_re_runs() -> None:
    line = daily_line(RUNS, _jobs, DAY)
    assert line == (
        "2026-11-10: CI wall 20.0 min (median of 3), CI queue 4.0 min, "
        "Full wall on main 35.0 min (2 runs), Full runs 3, re-runs 1"
    )


def test_a_day_without_runs_gives_n_a_and_no_error() -> None:
    line = daily_line([], _jobs, DAY)
    assert line == (
        "2026-11-10: CI wall n/a (median of 0), CI queue n/a, "
        "Full wall on main n/a (0 runs), Full runs 0, re-runs 0"
    )


def test_a_draft_pr_runs_no_job_and_a_ready_pr_starts_ci() -> None:
    import re
    from pathlib import Path

    root = Path(__file__).parents[1]
    for name, aggregate in (("ci.yml", "check"), ("full-verification.yml", "verified")):
        text = (root / ".github/workflows" / name).read_text()
        assert "types: [opened, synchronize, reopened, ready_for_review]" in text
        jobs = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
        for job, body in zip(jobs[1::2], jobs[2::2], strict=True):
            guard = "github.event.pull_request.draft != true"
            assert re.search(rf"^    if: .*{re.escape(guard)}$", body, re.MULTILINE), (name, job)
            assert ("if: always() && " in body) == (job == aggregate)
