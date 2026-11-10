# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-4): the real collector reads script facts in time and memory that grow
linearly with the script.

Consumer: `native/typescript/src/script*.rs`, which the production collector runs on every file.
Each shape of `scaling_script_shapes.py` has n of one construct. The tests compare the facts with
the Python parser at small sizes, bound the ratio of the CPU time of 2n to n, and bound the peak
memory by an absolute cap and by the ratio of 2n to n.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from scaling_script_shapes import SCRIPT_SHAPES
from test_collector_native_scaling import (
    _RUSAGE,
    CAP,
    MAX_BYTES,
    _limit_address_space,
    _prepare,
    _request,
    _run,
    collector,  # noqa: F401
    measure,
    timing_for_profile,
)
from test_collector_native_syntax import _assert_equal, compare, dump_binary  # noqa: F401

MEMORY_GROWTH = 2.5
# The peak of the real collector at 2n (debug build) is at most 105 MiB for the largest shape
# (`script-opaque-writes`, 2 400 constructs; 54 MiB before PR 4.3a-5 made a record, a target and a
# gap for each use of a global); the cap is about twice that.
MEMORY_CAP = 192 * 1024 * 1024
MEMORY_COUNT = 12_000
# A loop that searches the writes of a file for each write costs 2.6 times for twice the size, and
# the shared bound of 3 let it pass (review of PR 4.3a-5). The script shapes are held to 2.4;
# linear code measures 1.8 to 2.1.
SCRIPT_RATIO = 2.4
# The size at which a quadratic term shows over the fixed cost of the process (3 000 writes took
# 0.6 s, and 48 000 took 25 s while the loop was quadratic and 10 s after the fix).
LARGE_WRITES = 12_000


@pytest.mark.parametrize("name", sorted(SCRIPT_SHAPES))
def test_the_facts_equal_the_python_parser_at_small_sizes(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    name: str,
) -> None:
    shape = SCRIPT_SHAPES[name]
    files = []
    for count in (1, 2, 5, 40):
        path = tmp_path / f"{name}-{count}{shape.suffix}"
        path.write_bytes(shape.make(count))
        files.append((f"src/{path.name}", path))
    _assert_equal(compare(dump_binary, files), len(files))


@pytest.mark.parametrize("name", sorted(SCRIPT_SHAPES))
def test_the_time_grows_linearly_with_the_size_of_the_script(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
) -> None:
    timing = timing_for_profile()
    shape = SCRIPT_SHAPES[name]
    n, first, second = measure(collector, tmp_path, shape, timing)
    ratio = second.cpu / first.cpu
    print(f"SCRIPT {name} n={n} t(n)={first.cpu:.3f} t(2n)={second.cpu:.3f} ratio={ratio:.2f}")
    assert len(shape.make(2 * n)) <= MAX_BYTES, f"{name}: the file is too large for n={2 * n}"
    assert first.cpu >= timing.min_time, f"{name}: {first.cpu:.3f} s CPU is too short to measure"
    assert second.cpu < CAP, f"{name}: {second.cpu:.1f} s CPU for n={2 * n}"
    assert ratio < SCRIPT_RATIO, (
        f"{name}: n={n} {first.cpu:.3f} s, 2n {second.cpu:.3f} s, ratio {ratio:.2f}"
    )


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


def test_the_opaque_writes_of_a_large_file_cost_linear_time(
    tmp_path: Path,
    collector: Path,  # noqa: F811
) -> None:
    shape = SCRIPT_SHAPES["script-opaque-writes"]
    sizes = (LARGE_WRITES, 2 * LARGE_WRITES)
    cpu = [_run(collector, _prepare(tmp_path / f"n{n}", shape, n), shape).cpu for n in sizes]
    ratio = cpu[1] / cpu[0]
    print(f"OPAQUE n={sizes[0]} t(n)={cpu[0]:.2f} t(2n)={cpu[1]:.2f} ratio={ratio:.2f}")
    assert ratio < SCRIPT_RATIO, (
        f"n={sizes[0]} {cpu[0]:.2f} s, 2n {cpu[1]:.2f} s, ratio {ratio:.2f}"
    )
