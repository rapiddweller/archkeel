# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-4), AD-1252: the real collector reads script facts in memory that grows
linearly with the script.

Consumer: `native/typescript/src/script*.rs`, which the production collector runs on every file.
Each shape of `scaling_script_shapes.py` has n of one construct. The tests bound the peak memory
by an absolute cap and by the ratio of 2n to n. No test here times anything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from scaling_script_shapes import SCRIPT_SHAPES
from test_collector_native_scaling import (
    _RUSAGE,
    _limit_address_space,
    _prepare,
    _request,
    collector,  # noqa: F401
)

MEMORY_GROWTH = 2.5
# The peak of the real collector at 2n (debug build) is at most 105 MiB for the largest shape
# (`script-opaque-writes`, 2 400 constructs; 54 MiB before PR 4.3a-5 made a record, a target and a
# gap for each use of a global); the cap is about twice that.
MEMORY_CAP = 192 * 1024 * 1024
MEMORY_COUNT = 12_000


def _peak(tmp_path: Path, binary: Path, name: str, count: int) -> int:
    """The peak resident memory of the collector, in bytes, for the script of `name` and `count`."""
    case = _prepare(tmp_path, SCRIPT_SHAPES[name], count)
    request = case / "request.bin"
    request.write_bytes(_request(case))
    done = subprocess.run(
        [sys.executable, "-c", _RUSAGE, str(binary), str(request)],
        capture_output=True,
        text=True,
        check=False,
        preexec_fn=_limit_address_space if sys.platform == "linux" else None,
    )
    assert done.returncode == 0, done.stderr[-300:]
    return int(done.stdout) * (1 if sys.platform == "darwin" else 1024)


@pytest.mark.parametrize("name", sorted(SCRIPT_SHAPES))
def test_the_memory_grows_linearly_with_the_size_of_the_script(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
) -> None:
    count = MEMORY_COUNT // 10
    first = _peak(tmp_path, collector, name, count)
    second = _peak(tmp_path, collector, name, 2 * count)
    print(f"SCRIPTMEMORY {name} n={count} {first / 2**20:.0f} MiB 2n {second / 2**20:.0f} MiB")
    assert second < MEMORY_CAP, f"{name}: {second / 2**20:.0f} MiB"
    assert second <= MEMORY_GROWTH * first, f"{name}: {first / 2**20:.0f} -> {second / 2**20:.0f}"
