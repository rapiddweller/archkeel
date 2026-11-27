# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Report the time of each job of a workflow run (AD-341, AD-1251).

The input is one JSON job on each line, as `gh api .../attempts/<n>/jobs --jq '.jobs[]'` writes
it. The aggregate job that runs this tool is not complete yet, so it is not in the table. All jobs
of a run start in parallel, so the longest job is the critical path when no job waits in the queue.
The tool states the times and no limit: it never warns and never fails.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    queue: float
    run: float


def _minutes(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60


def complete_jobs(lines: Sequence[str]) -> list[Job]:
    """The jobs that started and completed, the longest first."""
    jobs = []
    for line in lines:
        if not line.strip():
            continue
        job = json.loads(line)
        if job.get("started_at") and job.get("completed_at"):
            jobs.append(
                Job(
                    job["name"],
                    _minutes(job["created_at"], job["started_at"]),
                    _minutes(job["started_at"], job["completed_at"]),
                )
            )
    return sorted(jobs, key=lambda job: (-job.run, job.name))


def report(jobs: Sequence[Job]) -> str:
    """Return the Markdown table of the job times."""
    if not jobs:
        return "No complete job.\n"
    rows = [
        f"Critical path without queue: {jobs[0].run:.1f} min. "
        f"Longest queue: {max(job.queue for job in jobs):.1f} min.",
        "",
        "| Job | Run (min) | Queue (min) |",
        "|---|---:|---:|",
        *(f"| {job.name} | {job.run:.1f} | {job.queue:.1f} |" for job in jobs),
    ]
    return "\n".join(rows) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, help="append the table to this file")
    args = parser.parse_args(argv)
    table = report(complete_jobs(sys.stdin.read().splitlines()))
    print(table, end="")
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as summary:
            summary.write(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
