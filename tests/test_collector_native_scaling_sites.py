# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the sites of the native walk are linear in time and in memory (PR 4.3a-2).

Consumer: the later phases of the native collector, which read the sites. The shapes are in
`scaling_shapes.py` (their names start with `sites-`), and the method is the one of
`test_collector_native_scaling.py`: the CPU time of n and 2n, with a ratio below 3. This file holds
the sites only, so that the matrix runs on two workers (a file stays on one worker with
`--dist=loadgroup`) and stays inside the time limit of the Full run. The equality of each shape
with `parse.parse()` and the tables stay in the first file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scaling_shapes import SHAPES
from test_collector_native_scaling import (
    MEMORY_CAP,
    SITE_PREFIX,
    _peak_memory,
    assert_time_grows_linearly,
    collector,  # noqa: F401
)


@pytest.mark.parametrize("name", sorted(n for n in SHAPES if n.startswith(SITE_PREFIX)))
def test_time_grows_linearly_with_the_size(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
) -> None:
    assert_time_grows_linearly(tmp_path, collector, name)


# The sites keep a chain, a path or a range of bytes for each node, and never a copy of the names
# above them. The shapes that stress each of these: a union of names for each site (n nested arrow
# functions with n sites at the bottom), a path for each member of a chain, the receiver text of
# each call of a chain, and the frames above each name. Their memory is bounded by a ratio: the
# peak for 2n is at most 2.5 times the peak for n (linear growth is below 2 with the fixed cost of
# the process; quadratic growth is 4).
MEMORY_GROWTH = 2.5
SITE_MEMORY_CASES = (
    ("sites-shadow-nest-arrows", 4_000),
    ("sites-calls-in-arrow-nest", 3_000),
    ("sites-many-shadowed-names", 30_000),
    ("sites-member-chain-call", 100_000),
    ("sites-chained-calls", 40_000),
    ("sites-computed-access", 100_000),
    ("sites-comparison-wrappers", 30_000),
    ("sites-publication-chain", 30_000),
    ("sites-many-bound-names", 8_000),
    ("sites-calls-at-depth", 8_000),
    ("sites-after-comment-run", 200_000),
    ("sites-script-wrapper-nest", 8_000),
)


@pytest.mark.parametrize(("name", "count"), SITE_MEMORY_CASES)
def test_sites_keep_the_memory_linear(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
    count: int,
) -> None:
    first = _peak_memory(tmp_path, collector, name, count)
    second = _peak_memory(tmp_path, collector, name, 2 * count)
    print(f"MEMORY {name} n={count} {first / 2**20:.0f} MiB 2n {second / 2**20:.0f} MiB")
    assert second < MEMORY_CAP, f"{name} n={2 * count}: {second / 2**20:.0f} MiB"
    assert second <= MEMORY_GROWTH * first, (
        f"{name}: n={count} {first / 2**20:.0f} MiB, 2n {second / 2**20:.0f} MiB"
    )
