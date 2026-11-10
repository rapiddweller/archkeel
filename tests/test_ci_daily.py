# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The daily CI line of the merge policy (epic #880) is computed from recorded `gh` JSON."""

import re
from datetime import UTC, datetime
from pathlib import Path

from tools.ci_daily import daily_line

DAY = "2026-11-10"
ZERO = "0001-01-01T00:00:00Z"


def _run(
    run_id: int,
    workflow: str,
    created: str,
    updated: str,
    branch: str = "feature",
    attempt: int = 1,
    conclusion: str = "success",
) -> dict[str, object]:
    return {
        "databaseId": run_id,
        "workflowName": workflow,
        "headBranch": branch,
        "createdAt": f"{DAY}T{created}Z",
        "updatedAt": f"{DAY}T{updated}Z",
        "attempt": attempt,
        "conclusion": conclusion,
    }


def _job(start: str, conclusion: str = "success") -> dict[str, str]:
    return {
        "startedAt": ZERO if conclusion == "skipped" else f"{DAY}T{start}Z",
        "conclusion": conclusion,
    }


# Run 1: job A starts at +0:10 and job B at +23:00, so the queue is 23.0 (not the first start).
# Run 2: a skipped job with the zero date is ignored. Run 3: a draft run, all jobs skipped.
# Run 4: a re-run (attempt 2) is excluded from wall and queue and counted as a re-run.
JOBS = {
    1: [_job("10:00:10"), _job("10:23:00")],
    2: [_job("11:01:00"), _job("00:00:00", "skipped")],
    3: [_job("00:00:00", "skipped")],
    4: [_job("12:30:00")],
}
RUNS = [
    _run(1, "CI", "10:00:00", "10:30:00"),
    _run(2, "CI", "11:00:00", "11:10:00"),
    _run(3, "CI", "12:00:00", "12:00:05"),
    _run(4, "CI", "12:00:00", "12:40:00", attempt=2),
    _run(5, "Full verification", "02:17:00", "02:47:00", branch="main", conclusion="failure"),
    _run(6, "Full verification", "05:17:00", "05:47:00", branch="main"),
    _run(7, "Full verification", "13:00:00", "13:20:00"),
]
NOW = datetime(2026, 11, 10, 20, tzinfo=UTC)


def test_the_line_uses_the_slowest_starting_job_and_drops_skipped_work() -> None:
    line = daily_line(RUNS, lambda run_id: JOBS.get(run_id, []), DAY, NOW)
    assert line == (
        "2026-11-10: CI wall 20.0 min (median of 2), "
        "CI queue median 12.0 min, p90 23.0 min, max 23.0 min, "
        "Full wall on main 30.0 min (2 runs), Full runs 3, re-runs 1, red main 3.0 h"
    )


def test_an_open_red_run_counts_to_now_and_a_day_without_runs_gives_n_a() -> None:
    open_red = [_run(5, "Full verification", "18:00:00", "18:30:00", "main", conclusion="failure")]
    assert "red main 2.0 h" in daily_line(open_red, lambda run_id: [], DAY, NOW)
    assert daily_line([], lambda run_id: [], DAY, NOW) == (
        "2026-11-10: CI wall n/a (median of 0), CI queue median n/a, p90 n/a, max n/a, "
        "Full wall on main n/a (0 runs), Full runs 0, re-runs 0, red main 0.0 h"
    )


def test_a_draft_pr_runs_no_job_and_a_ready_pr_starts_ci() -> None:
    """Exactly the draft guard on a job; `always() &&` only on the aggregate (AD-348)."""
    guard = "github.event.pull_request.draft != true"
    for path in (Path(__file__).parents[1] / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
        guarded = path.name in ("ci.yml", "full-verification.yml")
        assert ("types: [opened, synchronize, reopened, ready_for_review]" in text) == guarded
        for job, body in zip(parts[1::2], parts[2::2], strict=True):
            found = re.findall(r"^    if: (.+)$", body, flags=re.MULTILINE)
            aggregate = job in ("check", "verified")
            expected = [f"always() && {guard}"] if aggregate else [guard]
            assert found == (expected if guarded else []), f"{path.name} job {job}: {found}"


def test_a_draft_run_and_a_ready_run_use_two_concurrency_groups() -> None:
    """A skipped draft run must never cancel the real run of the same PR (AD-348)."""
    split = "-${{ github.event.pull_request.draft == true && 'draft' || 'ready' }}"
    for name in ("ci.yml", "full-verification.yml"):
        text = (Path(__file__).parents[1] / ".github/workflows" / name).read_text()
        group = re.search(r"^  group: (.+)$", text, flags=re.MULTILINE)
        assert group is not None and group[1].endswith(split), name
