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
from scaling_shapes import SHAPES, SITE_PARTS, SITE_TIMED
from scaling_walk_only import WALK_ONLY
from test_collector_native_scaling import (
    MEMORY_CAP,
    SITE_PREFIX,
    _peak_memory,
    assert_time_grows_linearly,
    collector,  # noqa: F401
    dump_binary,  # noqa: F401
)


def test_every_site_shape_is_a_part_of_exactly_one_timed_shape() -> None:
    parts = [name for names in SITE_PARTS.values() for name in names]
    assert sorted(parts) == sorted(n for n in SHAPES if n.startswith(SITE_PREFIX))


@pytest.mark.parametrize("name", sorted(SITE_TIMED))
def test_time_grows_linearly_with_the_size(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    dump_binary: Path,  # noqa: F811
    name: str,
) -> None:
    assert_time_grows_linearly(tmp_path, collector, name, dump_binary)


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
    dump_binary: Path,  # noqa: F811
    name: str,
    count: int,
) -> None:
    # A nest of named definitions has a quadratic reply by the data model: its walk is measured.
    walk = name in WALK_ONLY
    binary = dump_binary if walk else collector
    first = _peak_memory(tmp_path, binary, name, count, walk)
    second = _peak_memory(tmp_path, binary, name, 2 * count, walk)
    print(f"MEMORY {name} n={count} {first / 2**20:.0f} MiB 2n {second / 2**20:.0f} MiB")
    assert second < MEMORY_CAP, f"{name} n={2 * count}: {second / 2**20:.0f} MiB"
    assert second <= MEMORY_GROWTH * first, (
        f"{name}: n={count} {first / 2**20:.0f} MiB, 2n {second / 2**20:.0f} MiB"
    )


# The real collector, on the shapes whose reply is quadratic by the data model: the qualified name
# of each nested definition is in every record inside it, so the reply and the table of symbols
# grow with n squared. `writes-distinct-names` with n = 8 000 gives a reply of 397 MB and a peak of
# 474 MiB (it was 1 302 MiB before the table shared its names). The growth cannot tell a copy of a
# name for each record from the data model, so the guard is an absolute cap at a size that the real
# collector meets: the evidence of the reply is complete only after the last record, and `evidence`
# comes before `sections` in the reply (as in Python), so the compressed records wait in memory
# until the evidence is written. The peak is the walk plus the compressed reply. The measured peaks
# (release build, MiB) are 261 for `writes-distinct-names` n = 4 000, 96 and 96 for the two import
# shapes n = 2 000, and 265 for `sites-calls-at-depth` n = 4 000; they were 133, 61, 62 and 134
# before the records waited. The cap is a fifth more than the largest of them. The copy that it
# must catch is the old table, which peaked at 255 MiB for `writes-distinct-names` n = 4 000 before
# the records waited (1 302 MiB at 8 000): with the wait of about 130 MiB it is above the cap.
REAL_MEMORY_CAP = 320 * 1024 * 1024
REAL_MEMORY_CASES = (
    ("writes-distinct-names", 4_000),
    ("writes-imports-all-at-bottom", 2_000),
    ("writes-import-at-own-depth", 2_000),
    ("sites-calls-at-depth", 4_000),
)


@pytest.mark.parametrize(("name", "count"), REAL_MEMORY_CASES)
def test_the_real_collector_keeps_the_memory_of_a_quadratic_reply_bounded(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
    count: int,
) -> None:
    assert name in WALK_ONLY
    peak = _peak_memory(tmp_path, collector, name, count)
    print(f"REALMEMORY {name} n={count} {peak / 2**20:.0f} MiB")
    assert peak < REAL_MEMORY_CAP, f"{name} n={count}: {peak / 2**20:.0f} MiB"
