# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the time of the native collector is linear in the size of each construct class.

Consumer: every later phase of the native collector, which reads the facts of the walk. The method
is a scaling matrix, not a list of shapes. For each construct class of `scaling_shapes.SHAPES` the
test builds a file with n and with 2n of the construct, times the collector process (the minimum
of three runs) and bounds time(2n) / time(n). Linear is about 2 and quadratic is about 4, so the
bound is 3. A shape that takes less than 0.3 s doubles n first, so that the start of the process
does not hide the growth. The shapes that stress each loop of the walk (the run of comments before
a member, the frames above a write, the line before a column) were quadratic once; the matrix
fails on those versions (see AD-323).

`ARCHKEEL_SCALING_BINARY` names another collector, to run the matrix against an older build, and
`ARCHKEEL_SCALING_SCALE` multiplies every n (an older build that is quadratic needs a smaller n).
A second test compares the dump with `parse.parse()` for each shape at small sizes, so that each
shape holds the construct that it claims.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scaling_shapes import COVERAGE, FIELD_COVERAGE, KIND_CLASSES, SHAPES, Shape
from test_collector_native_syntax import FIELDS, compare, dump_binary  # noqa: F401

from archkeel.analyzer.typescript.syntax import Definition
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

# The least time of the first size, in seconds, below which n doubles (debug build).
MEASURABLE = 0.25
# A file may not be larger than this: the collector reads at most 4 MiB (AD-319).
MAX_BYTES = 3_500_000
# The bound of time(2n) / time(n): linear is about 2, quadratic is about 4.
RATIO = 3.0
# A guard for a machine that is far too slow: the biggest case may not take longer.
CAP = 60.0
RUNS = 3
# A first size below this time says that the shape is too cheap: the ratio would be noise.
MIN_TIME = 0.1
MAX_DOUBLINGS = 6


@pytest.fixture(scope="session")
def collector(native_binary: Path) -> Path:
    other = os.environ.get("ARCHKEEL_SCALING_BINARY")
    return Path(other) if other else native_binary


def _request(root: Path) -> bytes:
    return encode_request(
        CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings("tsconfig.json", False),
            ProtocolVersion.V8,
        )
    )


def _time(binary: Path, root: Path, shape: Shape, n: int) -> float:
    (root / "tsconfig.json").write_text('{"compilerOptions":{"allowJs":true},"include":["src"]}')
    (root / "src").mkdir(exist_ok=True)
    for old in (root / "src").iterdir():
        old.unlink()
    (root / "src" / f"a{shape.suffix}").write_bytes(shape.make(n))
    payload = _request(root)
    best = float("inf")
    for _ in range(RUNS):
        begin = time.perf_counter()
        done = subprocess.run([str(binary)], input=payload, capture_output=True, check=False)
        best = min(best, time.perf_counter() - begin)
        assert done.returncode == 0, done.stderr[-300:]
    return best


def measure(binary: Path, root: Path, shape: Shape) -> tuple[int, float, float]:
    """`(n, time(n), time(2n))` with the least n whose time is measurable."""
    n = max(1, int(shape.base * float(os.environ.get("ARCHKEEL_SCALING_SCALE", "1"))))
    first = _time(binary, root, shape, n)
    for _ in range(MAX_DOUBLINGS):
        # The file of 2n after the doubling must still be readable: 4n of the old n.
        if first >= MEASURABLE or len(shape.make(4 * n)) > MAX_BYTES:
            break
        n *= 2
        first = _time(binary, root, shape, n)
    return n, first, _time(binary, root, shape, 2 * n)


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_time_grows_linearly_with_the_size(tmp_path: Path, collector: Path, name: str) -> None:
    n, first, second = measure(collector, tmp_path, SHAPES[name])
    ratio = second / first
    print(f"SCALING {name} n={n} t(n)={first:.3f} t(2n)={second:.3f} ratio={ratio:.2f}")
    assert len(SHAPES[name].make(2 * n)) <= MAX_BYTES, (
        f"{name}: the file is too large for n={2 * n}"
    )
    assert first >= MIN_TIME, f"{name}: {first:.3f} s for n={n} is too short to measure"
    assert second < CAP, f"{name}: {second:.1f} s for n={2 * n}"
    assert ratio < RATIO, f"{name}: n={n} {first:.3f} s, 2n {second:.3f} s, ratio {ratio:.2f}"


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_each_shape_equals_the_python_parser_at_small_sizes(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    name: str,
) -> None:
    shape = SHAPES[name]
    files = []
    for count in (1, 3, 12):
        path = tmp_path / f"s{count}{shape.suffix}"
        path.write_bytes(shape.make(count))
        files.append((f"src/{path.name}", path))
    result = compare(dump_binary, files)
    assert result.native_failed == []
    assert result.differences == [], "\n".join(result.differences[:10])
    assert result.python_failed == 0


# The peak memory of the collector, in bytes, for n nested functions that write n different names.
# The memo of the write lookup once kept n squared entries: 1.5 GB at n = 8 000 (release build).
MEMORY_N = 8_000
MEMORY_CAP = 300 * 1024 * 1024
_RUSAGE = (
    "import resource, subprocess, sys\n"
    "subprocess.run([sys.argv[1]], stdin=open(sys.argv[2], 'rb'), stdout=subprocess.DEVNULL,"
    " check=True)\n"
    "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
)


def test_distinct_name_writes_keep_the_memory_bounded(tmp_path: Path, collector: Path) -> None:
    shape = SHAPES["writes-distinct-names"]
    (tmp_path / "tsconfig.json").write_text('{"include":["src"]}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_bytes(shape.make(MEMORY_N))
    request = tmp_path / "request.bin"
    request.write_bytes(_request(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", _RUSAGE, str(collector), str(request)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-300:]
    # `ru_maxrss` is in kilobytes on Linux and in bytes on macOS.
    peak = int(done.stdout) * (1 if sys.platform == "darwin" else 1024)
    assert peak < MEMORY_CAP, f"{peak / 2**20:.0f} MiB for n={MEMORY_N}"


def _kinds() -> list[str]:
    source = (Path(__file__).parents[1] / "native/typescript/src/kinds.rs").read_text()
    body = source[source.index("pub enum K {") :].split("\n}\n", 1)[0]
    return re.findall(r"^    (\w+),", body, flags=re.MULTILINE)


def test_every_shape_the_table_names_exists() -> None:
    named = {name for shapes in (*COVERAGE.values(), *FIELD_COVERAGE.values()) for name in shapes}
    assert sorted(named - SHAPES.keys()) == []
    # A shape that no class names holds no construct that anyone promised.
    assert sorted(SHAPES.keys() - named) == []


def test_every_kind_of_the_port_is_in_one_construct_class_with_shapes() -> None:
    kinds = [kind for kind in _kinds() if kind != "Other"]
    assert len(kinds) > 100
    placed = [kind for names in KIND_CLASSES.values() for kind in names]
    assert sorted(set(kinds) - set(placed)) == [], "a kind of kinds.rs has no construct class"
    assert sorted(set(placed) - set(kinds)) == [], "a class names a kind that does not exist"
    assert len(placed) == len(set(placed)), "a kind is in two classes"
    assert KIND_CLASSES.keys() <= COVERAGE.keys()
    assert all(COVERAGE[name] for name in KIND_CLASSES)


def test_every_fact_and_every_definition_field_has_shapes() -> None:
    fields = {field.name for field in dataclasses.fields(Definition)}
    assert sorted((set(FIELDS) | fields) - FIELD_COVERAGE.keys()) == []
    assert sorted(FIELD_COVERAGE.keys() - (set(FIELDS) | fields)) == []
