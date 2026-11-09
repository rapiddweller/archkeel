# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Report the time of each job of a workflow run against the time budget (AD-338).

The input is one JSON job on each line, as `gh api .../attempts/<n>/jobs --jq '.jobs[]'` writes
it. The aggregate job that runs this tool is not complete yet, so it is not in the table. All jobs
of a run start in parallel, so the longest job is the critical path when no job waits in the queue.
The tool writes a warning for each value over its limit. It never fails: the budget is a target.
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


def report(jobs: Sequence[Job], job_minutes: float, path_minutes: float) -> tuple[str, list[str]]:
    """Return the Markdown table and the warnings."""
    if not jobs:
        return "No complete job.\n", ["No complete job: the time budget is not checked."]
    path = jobs[0].run
    rows = [
        f"Critical path without queue: {path:.1f} min (budget {path_minutes:g}). "
        f"Longest queue: {max(job.queue for job in jobs):.1f} min.",
        "",
        "| Job | Run (min) | Queue (min) |",
        "|---|---:|---:|",
        *(f"| {job.name} | {job.run:.1f} | {job.queue:.1f} |" for job in jobs),
    ]
    warnings = [
        f"{job.name} ran {job.run:.1f} min; the budget of a job is {job_minutes:g} min."
        for job in jobs
        if job.run > job_minutes
    ]
    if path > path_minutes:
        warnings.append(f"The critical path is {path:.1f} min; the budget is {path_minutes:g} min.")
    return "\n".join(rows) + "\n", warnings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-minutes", type=float, required=True)
    parser.add_argument("--path-minutes", type=float, required=True)
    parser.add_argument("--summary", type=Path, help="append the table to this file")
    args = parser.parse_args(argv)
    table, warnings = report(
        complete_jobs(sys.stdin.read().splitlines()), args.job_minutes, args.path_minutes
    )
    print(table, end="")
    for warning in warnings:
        print(f"::warning title=Time budget (AD-338)::{warning}")
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as summary:
            summary.write(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
