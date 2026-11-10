# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-3d): the time of the real collector on the shapes with a quadratic reply.

Consumer: `native/typescript/src/records.rs` and `native/wire/src/stream.rs`. The matrix times
the walk alone for these shapes (`--dump-count`); this file times the whole collector, by the time
for each byte of its reply, so that a loop of the record writers or of the encoder shows.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from scaling_shapes import SHAPES, SITE_TIMED, Shape
from scaling_walk_only import WALK_ONLY
from test_collector_native_scaling import (
    CAP,
    Timing,
    _prepare,
    _request,
    collector,  # noqa: F401
    measure,
)

# The reply of these shapes is quadratic by the data model, so the time of the real collector is
# bounded by the time for each byte of its reply: it may not grow with n. The reply grows with n
# squared and the walk with n, so the time for each byte falls with n; a loop that grows with the
# number of records of the reply makes it rise.
REAL_BYTE_RATIO = 2.0
# The reply of these shapes grows with n squared, so the real path starts at a fiftieth of the base
# and accepts a shorter first run: a size of 0.25 s makes a reply of 100 MB or more.
REAL_SCALE = "0.02"
REAL_TIMINGS = {
    "debug": Timing(measurable=0.08, min_time=0.04),
    "release": Timing(measurable=0.02, min_time=0.01),
}


def _reply_size(binary: Path, root: Path, shape: Shape, n: int) -> int:
    """The compressed size of the reply of the real collector for the file of `shape` and n."""
    case = _prepare(root, shape, n)
    done = subprocess.run(
        [str(binary)], input=_request(case), capture_output=True, check=True, timeout=CAP
    )
    return len(done.stdout)


def assert_real_time_per_byte_is_flat(tmp_path: Path, binary: Path, name: str) -> None:
    timing = REAL_TIMINGS[os.environ.get("ARCHKEEL_SCALING_PROFILE", "debug")]
    shape = SHAPES[name] if name in SHAPES else SITE_TIMED[name]
    n, first, second = measure(binary, tmp_path, shape, timing, scale=REAL_SCALE)
    small = _reply_size(binary, tmp_path, shape, n)
    large = _reply_size(binary, tmp_path, shape, 2 * n)
    per_byte = (second.cpu / large) / (first.cpu / small)
    print(
        f"REAL {name} n={n} t(n)={first.cpu:.3f} t(2n)={second.cpu:.3f} "
        f"bytes={small}/{large} per_byte_ratio={per_byte:.2f}"
    )
    assert first.cpu >= timing.min_time, f"{name}: {first.cpu:.3f} s CPU is too short to measure"
    assert second.cpu < CAP, f"{name}: {second.cpu:.1f} s CPU for n={2 * n}"
    assert per_byte < REAL_BYTE_RATIO, (
        f"{name}: n={n} {first.cpu:.3f} s for {small} bytes, 2n {second.cpu:.3f} s for "
        f"{large} bytes, ratio {per_byte:.2f}"
    )


@pytest.mark.parametrize("name", sorted(WALK_ONLY))
def test_the_real_collector_time_for_each_byte_of_the_reply_stays_flat(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
) -> None:
    assert_real_time_per_byte_is_flat(tmp_path, collector, name)
