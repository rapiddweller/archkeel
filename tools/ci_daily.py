# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print the daily CI line of the merge policy (epic #880).

The line has the median CI wall time, the median CI queue wait (the first job start minus the
run creation), the median Full wall time on `main`, the number of Full runs and the re-runs.
Red-main hours need the history of `main` and are not in this line. The data comes from
`gh run list` and `gh run view --json jobs`; `daily_line` takes both as values, so a test needs no
network.
"""

import json
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

Run = Mapping[str, object]
RUN_FIELDS = "databaseId,workflowName,headBranch,createdAt,updatedAt,attempt"


def _time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _median(values: Sequence[float]) -> str:
    return f"{statistics.median(values):.1f} min" if values else "n/a"


def daily_line(
    runs: Sequence[Run], jobs_of: Callable[[int], Sequence[Mapping[str, str]]], day: str
) -> str:
    """The line for the runs created on `day` (UTC, `YYYY-MM-DD`)."""
    today = [run for run in runs if str(run["createdAt"]).startswith(day)]
    ci = [run for run in today if run["workflowName"] == "CI"]
    full = [run for run in today if run["workflowName"] == "Full verification"]
    full_main = [run for run in full if run["headBranch"] == "main"]
    queues = []
    for run in ci:
        starts = [_time(job["startedAt"]) for job in jobs_of(int(str(run["databaseId"])))]
        if starts:
            queues.append((min(starts) - _time(run["createdAt"])).total_seconds() / 60)
    return (
        f"{day}: CI wall {_median(_walls(ci))} (median of {len(ci)}), "
        f"CI queue {_median(queues)}, "
        f"Full wall on main {_median(_walls(full_main))} ({len(full_main)} runs), "
        f"Full runs {len(full)}, "
        f"re-runs {sum(int(str(run['attempt'])) > 1 for run in today)}"
    )


def _walls(runs: Sequence[Run]) -> list[float]:
    return [
        (_time(run["updatedAt"]) - _time(run["createdAt"])).total_seconds() / 60 for run in runs
    ]


def _gh(*args: str) -> object:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def main() -> int:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    runs = _gh("run", "list", "--limit", "300", "--json", RUN_FIELDS)
    assert isinstance(runs, list)

    def jobs_of(run_id: int) -> list[dict[str, str]]:
        view = _gh("run", "view", str(run_id), "--json", "jobs")
        assert isinstance(view, dict)
        return [job for job in view["jobs"] if job.get("startedAt")]

    print(daily_line(runs, jobs_of, day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
