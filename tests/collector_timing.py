# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The time of a collector child, as CPU time and as wall time.

The ratio tests of the native collector assert on the CPU time of the child: the user and system
time that the kernel charges to the process. A shared runner or a loaded machine stretches the
wall time of a run and does not change its CPU time much, so the CPU time gives a stable ratio.
The wall time is returned too, so that a test can report it next to the CPU time.

The CPU time comes from `os.wait4`, which returns the rusage of one child only. On Windows the
timing tests skip, because the PR gate and the Windows collector safety job do not run them.
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence

import pytest

if sys.platform != "win32":
    import resource

# The runs of one size. The least time of these runs is the time of the size (AD-323).
RUNS = 3
# A child that runs longer than this fails its test. A hung collector then stops the test, not the
# CI job, which would otherwise wait for its job timeout.
CHILD_TIMEOUT = 300.0
# The time between two checks of a running child. It adds at most this much to the wall time.
POLL_SECONDS = 0.005


@dataclasses.dataclass(frozen=True)
class Taken:
    """One run, or the least of several runs: the CPU time and the wall time, in seconds."""

    cpu: float
    wall: float


NO_TIME = Taken(cpu=math.inf, wall=math.inf)


def _keep_least(best: Taken, sample: Taken) -> Taken:
    """The least CPU time and the least wall time of `best` and `sample`."""
    return Taken(cpu=min(best.cpu, sample.cpu), wall=min(best.wall, sample.wall))


def least_of(measure: Callable[[], Taken], rounds: int = RUNS) -> Taken:
    """Call `measure` `rounds` times and return the least CPU time and the least wall time."""
    best = NO_TIME
    for _ in range(rounds):
        best = _keep_least(best, measure())
    return best


def interleaved_least(
    measure: Callable[[int], Taken],
    small: int,
    large: int,
    rounds: int = RUNS,
    seed: Taken = NO_TIME,
) -> tuple[Taken, Taken]:
    """Return the least `Taken` of the size `small` and of the size `large`.

    The rounds alternate the sizes: small, large, small, large. A slow phase of a shared runner
    then slows both sizes, so the ratio stays fair. Measuring one size after the other lets a slow
    phase hit only one side (AD-323). `seed` is a sample of `small` that is already taken. It joins
    the least of the small side and costs no run.
    """
    best_small = seed
    best_large = NO_TIME
    for _ in range(rounds):
        best_small = _keep_least(best_small, measure(small))
        best_large = _keep_least(best_large, measure(large))
    return best_small, best_large


def _reap(pid: int) -> tuple[int, resource.struct_rusage]:
    """Wait for the child `pid`, reap it and return its exit status and rusage.

    Fails the test when the child runs longer than `CHILD_TIMEOUT`. The caller kills the child.
    """
    deadline = time.perf_counter() + CHILD_TIMEOUT
    while True:
        reaped, status, usage = os.wait4(pid, os.WNOHANG)
        if reaped:
            return status, usage
        if time.perf_counter() > deadline:
            pytest.fail(f"the collector ran more than {CHILD_TIMEOUT:g} s and was killed")
        time.sleep(POLL_SECONDS)


def _kill_and_reap(pid: int) -> None:
    """Kill the child `pid` and reap it, so that no run leaves a process behind."""
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):
        os.wait4(pid, 0)


def timed_run(
    command: Sequence[str],
    payload: bytes,
    preexec_fn: Callable[[], None] | None = None,
) -> tuple[float, float, subprocess.CompletedProcess[bytes]]:
    """Run `command` with `payload` on stdin and return `(wall, cpu, done)` in seconds.

    The CPU time is the user and system time of this child only. The pipes are temporary files,
    not pipes: `os.wait4` must reap the child itself, and `Popen.communicate` would reap it first.
    An exception, or `KeyboardInterrupt`, kills the child and reaps it before it propagates.
    """
    if sys.platform == "win32":
        pytest.skip("the CPU time of a child needs the Unix resource module")
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as out:
        with tempfile.TemporaryFile() as err:
            stdin.write(payload)
            stdin.seek(0)
            begin = time.perf_counter()
            process = subprocess.Popen(
                list(command), stdin=stdin, stdout=out, stderr=err, preexec_fn=preexec_fn
            )
            reaped: tuple[int, resource.struct_rusage] | None = None
            try:
                reaped = _reap(process.pid)
            finally:
                if reaped is None:
                    _kill_and_reap(process.pid)
            status, usage = reaped
            wall = time.perf_counter() - begin
            # The child is reaped here, so tell the Popen object its exit code.
            process.returncode = os.waitstatus_to_exitcode(status)
            out.seek(0)
            err.seek(0)
            done = subprocess.CompletedProcess(
                list(command), process.returncode, out.read(), err.read()
            )
    return wall, usage.ru_utime + usage.ru_stime, done
