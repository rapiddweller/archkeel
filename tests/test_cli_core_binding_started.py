# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2204: a write in the tick of the request start must not pass the nested-contract binding.

The core reads a nested contract itself, so the digest of a file that changed after the request
started matches its new bytes. Only `st_ctime` tells the write from an earlier one. A coarse
kernel clock stamps it with a time at or below the start, so the check is `>=`, and the start is
read on the clock that stamps the file times.
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
