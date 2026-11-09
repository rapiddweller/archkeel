# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The time of a collector child, as CPU time and as wall time.

The ratio tests of the native collector assert on the CPU time of the child: the user and system
time that the kernel charges to the process. A shared runner or a loaded machine stretches the
wall time of a run and does not change its CPU time much, so the CPU time gives a stable ratio.
The wall time is returned too, so that a test can report it next to the CPU time.

The CPU time comes from `getrusage(RUSAGE_CHILDREN)`, which is available on Unix only. On Windows
the timing tests skip, because the PR gate and the Windows collector safety job do not run them.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import time
from collections.abc import Callable, Sequence

import pytest

if sys.platform != "win32":
    import resource

# The runs of one size. The least time of these runs is the time of the size (AD-323).
RUNS = 3


@dataclasses.dataclass(frozen=True)
class Taken:
    """One run, or the least of several runs: the CPU time and the wall time, in seconds."""

    cpu: float
    wall: float


def least_of(measure: Callable[[], Taken], rounds: int = RUNS) -> Taken:
    """Call `measure` `rounds` times and return the least CPU time and the least wall time."""
    best = Taken(cpu=float("inf"), wall=float("inf"))
    for _ in range(rounds):
        sample = measure()
        best = Taken(cpu=min(best.cpu, sample.cpu), wall=min(best.wall, sample.wall))
    return best


def _children_cpu() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def timed_run(
    command: Sequence[str],
    payload: bytes,
    preexec_fn: Callable[[], None] | None = None,
) -> tuple[float, float, subprocess.CompletedProcess[bytes]]:
    """Run `command` with `payload` on stdin and return `(wall, cpu, done)` in seconds.

    The CPU time is the change of the CPU time of all waited children of this process. The
    runs of a test are sequential, so the change belongs to `command` alone.
    """
    if sys.platform == "win32":
        pytest.skip("the CPU time of a child needs the Unix resource module")
    before = _children_cpu()
    begin = time.perf_counter()
    done = subprocess.run(
        list(command),
        input=payload,
        capture_output=True,
        check=False,
        preexec_fn=preexec_fn,
    )
    wall = time.perf_counter() - begin
    return wall, _children_cpu() - before, done
