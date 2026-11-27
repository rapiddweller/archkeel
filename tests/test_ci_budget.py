# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-341, AD-1251: the aggregate jobs report the time of each job; no limit warns or fails."""

import io
import json
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


def test_the_table_names_the_times_and_no_limit() -> None:
    table = report(complete_jobs(LINES))
    assert table.startswith("Critical path without queue: 8.5 min. Longest queue: 3.0")
    assert "| Tests: collectors | 8.5 | 3.0 |" in table and "budget" not in table
    assert report([]) == "No complete job.\n"


def test_the_tool_never_fails_and_writes_the_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "summary.md"
    for lines in (LINES, []):
        monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines)))
        assert main(["--summary", str(summary)]) == 0
    assert summary.read_text().count("| Job | Run (min) | Queue (min) |") == 1
