# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure repeated runs of one command with `--timings` and state the spread (#659, AD-878).

The nightly run (`tests/test_cli_phase_timings_reference.py`) uses it on a pinned public project.
One run has three kinds of seconds and one memory figure, and they are never mixed:

- `cli_wall_seconds`: the monotonic time from the start of the command to its exit (interpreter
  start, Git state, the core, read and print of the frame);
- `core_seconds` and `phases`: the time inside the core, as it wrote them to the `--timings` file;
- `peak_rss_bytes`: the largest resident set of any one process of the command, not a sum (the
  core holds nearly all of it).

The summary gives the smallest, the median and the largest value of each figure, and the spread
`(largest - smallest) / median`. It sets no limit: a limit needs the spread of many runs of the
runner first.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from archkeel.cli.core_output import read_timings

# `ru_maxrss` of the finished child: bytes on macOS, kibibytes elsewhere.
_RSS_UNIT = 1 if sys.platform == "darwin" else 1024
PHASES = ("prepare", "collect", "validate", "evaluate", "render", "join")


@dataclass(frozen=True)
class Run:
    """One measured run: the exit code, the three kinds of seconds and the memory."""

    exit_code: int
    cli_wall_seconds: float
    peak_rss_bytes: int
    core_seconds: float
    phases: Mapping[str, float]


def measure(argv: Sequence[str], timings: Path, stdout: Path, env: Mapping[str, str]) -> Run:
    """Run the command once. The command must write the file `timings` (`--timings`) and may
    write much to standard output, which goes to the file `stdout`."""
    with stdout.open("wb") as out, os.fdopen(os.open(os.devnull, os.O_WRONLY), "wb") as quiet:
        started = monotonic()
        process = subprocess.Popen(list(argv), stdout=out, stderr=quiet, env=dict(env))
        _, status, usage = os.wait4(process.pid, 0)
        wall = monotonic() - started
    process.returncode = os.waitstatus_to_exitcode(status)
    line = read_timings(timings.read_bytes(), refused=False)
    document = json.loads(line or b"{}")
    return Run(
        exit_code=process.returncode,
        cli_wall_seconds=wall,
        peak_rss_bytes=usage.ru_maxrss * _RSS_UNIT,
        core_seconds=float(document["core_seconds"]),
        phases={name: float(document["phases"][name]) for name in PHASES},
    )


def _figures(run: Run) -> dict[str, float]:
    return {
        "cli_wall_seconds": run.cli_wall_seconds,
        "core_seconds": run.core_seconds,
        "outside_core_seconds": run.cli_wall_seconds - run.core_seconds,
        **{f"phase_{name}": run.phases[name] for name in PHASES},
        "peak_rss_bytes": float(run.peak_rss_bytes),
    }


def spread(runs: Sequence[Run]) -> dict[str, dict[str, float]]:
    """For each figure: the smallest, the median and the largest value, and the spread."""
    columns: dict[str, list[float]] = {}
    for run in runs:
        for name, value in _figures(run).items():
            columns.setdefault(name, []).append(value)
    found: dict[str, dict[str, float]] = {}
    for name, values in columns.items():
        middle = statistics.median(values)
        found[name] = {
            "min": min(values),
            "median": middle,
            "max": max(values),
            "spread": (max(values) - min(values)) / middle if middle else 0.0,
        }
    return found


def summary(
    runs: Sequence[Run], pin: Mapping[str, Any], environment: Mapping[str, Any]
) -> dict[str, Any]:
    """The receipt of a reference run: what ran, where, every run, and the spread. No limit."""
    return {
        "pin": dict(pin),
        "environment": dict(environment),
        "runs": [{"exit_code": run.exit_code, **_figures(run)} for run in runs],
        "spread": spread(runs),
        "limits": "none: the spread of many nightly runs on the runner is needed first",
    }


def markdown(receipt: Mapping[str, Any]) -> str:
    """A table of the spread for the job summary of a CI run."""
    pin = receipt["pin"]
    lines = [
        f"### Phase timings: {pin['name']} {pin['ref']} (`{pin['commit'][:12]}`), "
        f"{len(receipt['runs'])} runs",
        "",
        "| figure | min | median | max | spread |",
        "|---|---|---|---|---|",
    ]
    for name, found in receipt["spread"].items():
        scale, unit = (2**20, " MiB") if name == "peak_rss_bytes" else (1, " s")
        cells = (f"{found[key] / scale:.3f}{unit}" for key in ("min", "median", "max"))
        lines.append(f"| {name} | {' | '.join(cells)} | {found['spread']:.0%} |")
    lines += ["", "No limit is set: " + receipt["limits"], ""]
    return "\n".join(lines)
