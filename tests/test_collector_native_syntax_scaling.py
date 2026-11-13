# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the time of the native syntax port on the shapes that made a loop quadratic.

Consumer: `native/typescript/src/walk.rs` and its tests. The method is the one of
`test_collector_native_scaling.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from collector_timing import Taken, interleaved_least, timed_run
from scaling_walk_only import WALK_ONLY
from test_collector_native_syntax import (
    _shape,
)

from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

# The time of the collector process (the debug build) grows linearly with the size: time(2n) over
# time(n) is about 2 for a linear walk and about 4 for a quadratic one. The facts of each definition
# once decoded the line before it and the whole text of its node, and kept the qualified name of
# each scope as a copy of its whole chain. In the release build 40 000 functions on one line took
# 33.6 s, 4 000 nested classes 14.9 s and 8 000 nested classes 61 s (1.3 GB), against 0.2 s and
# under 0.1 s for the collector of PR 4.2. The CPU time of the process, not the dump, is timed: the
# dump prints the qualified name of each definition, and that output is quadratic in the depth in
# Python too.
# `test_collector_native_scaling.py` runs the same method on every construct class.
PATHOLOGICAL = (("one-line", 20_000), ("nested-functions", 4_000), ("nested-classes", 4_000))
# The ratio of the times, and an absolute guard against a machine that is far too slow.
RATIO_BOUND = 3.0
GUARD_SECONDS = 60.0


def _prepare(root: Path, name: str, count: int) -> Path:
    """Write the file of `name` with `count` constructs into a root of its own, and return it."""
    case = root / f"n{count}"
    (case / "src").mkdir(parents=True, exist_ok=True)
    (case / "tsconfig.json").write_text('{"include":["src"]}')
    (case / "src/a.ts").write_bytes(_shape(name, count))
    return case


def _run(binary: Path, case: Path, walk: bool = False) -> Taken:
    """One run of the collector on the prepared root `case`; `walk` times the walk alone."""
    payload = encode_request(
        CollectionRequest(
            SnapshotInput(str(case), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings("tsconfig.json", False),
            ProtocolVersion.V8,
        )
    )
    command = [str(binary)]
    if walk:  # the reply of a nest is quadratic by the data model: only the walk is timed
        payload = json.dumps({"rel": "src/a.ts", "file": str(case / "src/a.ts")}).encode() + b"\n"
        command.append("--dump-count")
    wall, cpu, done = timed_run(command, payload)
    assert done.returncode == 0, done.stderr[-300:]
    return Taken(cpu=cpu, wall=wall)


@pytest.mark.parametrize(("name", "count"), PATHOLOGICAL)
def test_pathological_shapes_grow_linearly(
    tmp_path: Path,
    native_binary: Path,
    dump_binary: Path,  # noqa: F811
    name: str,
    count: int,
) -> None:
    walk = name in WALK_ONLY
    binary = dump_binary if walk else native_binary
    cases = {count: _prepare(tmp_path, name, count), 2 * count: _prepare(tmp_path, name, 2 * count)}
    small, large = interleaved_least(lambda size: _run(binary, cases[size], walk), count, 2 * count)
    # The wall times are printed for comparison only; the assertions use the CPU time.
    print(
        f"SYNTAX {name} n={count} cpu={small.cpu:.3f} 2n_cpu={large.cpu:.3f} "
        f"ratio={large.cpu / small.cpu:.2f} wall_ratio={large.wall / small.wall:.2f}"
    )
    assert large.cpu < GUARD_SECONDS, f"{name} {2 * count}: {large.cpu:.1f} s CPU"
    assert large.cpu / small.cpu < RATIO_BOUND, (
        f"{name} {count}: CPU {small.cpu:.2f} s, 2n {large.cpu:.2f} s; "
        f"wall {small.wall:.2f} s, 2n {large.wall:.2f} s"
    )
