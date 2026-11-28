# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2204, #2212: the binding refuses a write after the request start and binds a write before it.

The core reads a nested contract itself, so the digest of a file that changed after the request
started matches its new bytes. Only `st_ctime` tells the write from an earlier one. A coarse
kernel clock gives a write before and a write after the start in one tick the same time, so the
start waits for the next tick: a write before it is below the start, a write after is at or above.
"""

import hashlib
import sys
import time
from pathlib import Path

import pytest

from archkeel.cli.core_binding import _bind_inside, request_started_ns
from archkeel.cli.core_json import RequestMismatch


def _file(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "deep.json"
    path.write_bytes(b"{}")
    return path, hashlib.sha256(b"{}").hexdigest()


def test_a_change_time_equal_to_the_start_is_refused(tmp_path: Path) -> None:
    path, digest = _file(tmp_path)
    ctime = path.stat().st_ctime_ns
    # Equal times are the coarse-clock case: the write has the time of the start.
    with pytest.raises(RequestMismatch, match="changed after the request started"):
        _bind_inside(tmp_path, "deep.json", digest, 1 << 20, ctime)


def test_a_file_changed_before_the_start_binds(tmp_path: Path) -> None:
    path, digest = _file(tmp_path)
    assert _bind_inside(tmp_path, "deep.json", digest, 1 << 20, path.stat().st_ctime_ns + 1) == 2


def test_a_write_after_the_start_is_never_below_it(tmp_path: Path) -> None:
    for _ in range(2000):
        started = request_started_ns()
        path, _ = _file(tmp_path)
        assert path.stat().st_ctime_ns >= started


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the coarse clock is Linux")
def test_the_start_is_read_on_the_coarse_clock_of_file_times() -> None:
    assert request_started_ns() <= time.time_ns()


class _Clock:
    """A coarse clock that shows the given values one by one, then the last one for ever."""

    def __init__(self, *values: int) -> None:
        self.values, self.sleeps = list(values), 0

    def read(self, _clock: int) -> int:
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    def sleep(self, _seconds: float) -> None:
        self.sleeps += 1


def _linux(monkeypatch: pytest.MonkeyPatch, clock: _Clock, wait: float = 0.1) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(time, "clock_gettime_ns", clock.read)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr("archkeel.cli.core_binding._TICK_WAIT_S", wait)


@pytest.mark.parametrize(
    "ticks",
    [(4, 8, 12), (4, 4, 4, 8, 8, 12), (4, 8, 8, 8, 8, 8, 12, 12)],
    ids=["moving", "held at the first tick", "held at the second tick"],
)
def test_the_start_is_the_second_tick_after_the_call(
    monkeypatch: pytest.MonkeyPatch, ticks: tuple[int, ...]
) -> None:
    _linux(monkeypatch, _Clock(*(tick * 1_000_000 for tick in ticks)))
    # A file written in the first tick (4 ms) or the second (8 ms) is below the start 12 ms and
    # binds. A write after the call has the time of the first tick or later: it can be below the
    # start, which the second tick makes impossible for a fine stamp that lags (see the docstring).
    assert request_started_ns() == 12_000_000


def test_a_clock_that_does_not_move_gives_the_last_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _linux(monkeypatch, _Clock(4_000_000, 8_000_000), wait=0.0)
    # One tick and then a frozen clock: the tied time refuses a write of that tick, never misses it.
    assert request_started_ns() == 8_000_000


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the coarse clock is Linux")
def test_a_write_before_the_start_binds_and_a_write_after_it_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    for _ in range(1000):
        path.write_bytes(b"{}")
        before = path.stat().st_ctime_ns
        end = time.perf_counter_ns() + 100_000  # the draft files are written about 0.1 ms before
        while time.perf_counter_ns() < end:
            pass
        started = request_started_ns()
        assert before < started, "a write before the start must bind (#2212)"
        path.write_bytes(b"{} ")
        assert path.stat().st_ctime_ns >= started, "a write after the start must refuse (#2204)"
