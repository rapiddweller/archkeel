# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print the daily CI line of the merge policy (epic #880).

The line has the median CI wall time; the median, p90 and maximum CI queue wait (the wait of the
slowest-starting job that ran: its start minus the run creation); the median Full wall time on
`main`; the number of Full runs; the re-runs; and the hours that `main` was red (from the first
failed Full run to the next green one). A re-run (attempt above 1) and a run with only skipped jobs
(a draft PR) are not in the CI wall and queue. The data comes from
`gh run list` and `gh run view --json jobs`; `daily_line` takes both as values, so a test needs no
network.
"""

import json
import math
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta

Run = Mapping[str, object]
Job = Mapping[str, str]
RUN_FIELDS = "databaseId,workflowName,headBranch,createdAt,updatedAt,attempt,conclusion"
HOUR = 3600


def _time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _stat(values: Sequence[float], how: str) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    pick = {
        "median": statistics.median(ordered),
        "p90": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "max": ordered[-1],
    }[how]
    return f"{pick:.1f} min"


def _walls(runs: Sequence[Run]) -> list[float]:
    return [
        (_time(run["updatedAt"]) - _time(run["createdAt"])).total_seconds() / 60 for run in runs
    ]


def _queue(run: Run, jobs: Sequence[Job]) -> float:
    """The wait of the slowest-starting job that ran, never below 0 minutes."""
    starts = [_time(job["startedAt"]) for job in jobs]
    return max(0.0, max(start - _time(run["createdAt"]) for start in starts).total_seconds() / 60)


def red_hours(full_main: Sequence[Run], day: str, now: datetime) -> float:
    """Hours of `day` between the first failure and the next success of Full on main.

    An open red run counts to `now`. A cancelled run changes nothing.
    """
    start = datetime.fromisoformat(f"{day}T00:00:00+00:00")
    end = min(now, start + timedelta(days=1))
    seconds = 0.0
    red_since: datetime | None = None
    for run in sorted(full_main, key=lambda run: str(run["createdAt"])):
        created = _time(run["createdAt"])
        if run["conclusion"] == "failure" and red_since is None:
            red_since = created
        elif run["conclusion"] == "success" and red_since is not None:
            seconds += max(0.0, (min(created, end) - max(red_since, start)).total_seconds())
            red_since = None
    if red_since is not None:
        seconds += max(0.0, (end - max(red_since, start)).total_seconds())
    return seconds / HOUR


def daily_line(
    runs: Sequence[Run], jobs_of: Callable[[int], Sequence[Job]], day: str, now: datetime
) -> str:
    """The line for `day` (UTC, `YYYY-MM-DD`).

    CI wall and queue count only first attempts with a job that ran: a re-run keeps the creation
    time of the first attempt, and an all-skipped run is a draft PR. Both are not CI work.
    """
    today = [run for run in runs if str(run["createdAt"]).startswith(day)]
    ci = []
    queues = []
    for run in today:
        if run["workflowName"] != "CI" or int(str(run["attempt"])) > 1:
            continue
        jobs = [
            job for job in jobs_of(int(str(run["databaseId"]))) if job["conclusion"] != "skipped"
        ]
        if jobs:
            ci.append(run)
            queues.append(_queue(run, jobs))
    full = [run for run in today if run["workflowName"] == "Full verification"]
    full_main = [run for run in full if run["headBranch"] == "main"]
    return (
        f"{day}: CI wall {_stat(_walls(ci), 'median')} (median of {len(ci)}), "
        f"CI queue median {_stat(queues, 'median')}, p90 {_stat(queues, 'p90')}, "
        f"max {_stat(queues, 'max')}, "
        f"Full wall on main {_stat(_walls(full_main), 'median')} ({len(full_main)} runs), "
        f"Full runs {len(full)}, "
        f"re-runs {sum(int(str(run['attempt'])) > 1 for run in today)}, "
        f"red main {red_hours(full_main, day, now):.1f} h"
    )


def _gh(*args: str) -> object:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def main() -> int:
    now = datetime.now(UTC)
    day = now.strftime("%Y-%m-%d")
    runs = _gh("run", "list", "--limit", "300", "--json", RUN_FIELDS)
    assert isinstance(runs, list)

    def jobs_of(run_id: int) -> list[dict[str, str]]:
        view = _gh("run", "view", str(run_id), "--json", "jobs")
        assert isinstance(view, dict)
        return [job for job in view["jobs"] if job.get("startedAt")]

    print(daily_line(runs, jobs_of, day, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
