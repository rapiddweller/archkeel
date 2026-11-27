# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323, AD-1252: the memory of the native collector on the shapes that made a loop quadratic.

Consumer: every later phase of the native collector, which reads the facts of the walk. For each
construct class of `scaling_shapes.SHAPES` a test builds a file with n of the construct. No test
here times anything: a time ratio depends on the runner. The memory cases bound the peak memory
of the collector on the nests that were quadratic once (see AD-323).

`ARCHKEEL_SCALING_BINARY` names another collector, to run the cases against an older build.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from collector_wire import request_bytes
from scaling_shape_kit import Shape
from scaling_shapes import SHAPES
from scaling_walk_only import WALK_ONLY

# A file may not be larger than this: the collector reads at most 4 MiB (AD-319).
MAX_BYTES = 3_500_000


@pytest.fixture(scope="session")
def collector(native_binary: Path) -> Path:
    other = os.environ.get("ARCHKEEL_SCALING_BINARY")
    return Path(other) if other else native_binary


def _request(root: Path) -> bytes:
    return request_bytes(root, "app", "tsconfig.json")


CONFIG = '{"compilerOptions":{"allowJs":true},"include":["src"]}'


def _walk_line(case: Path, shape: Shape) -> bytes:
    """The request of the test-only `--dump-count`: the file that the walk reads."""
    rel = f"src/a{shape.suffix}"
    return json.dumps({"rel": rel, "file": str(case / rel)}).encode() + b"\n"


def _prepare(root: Path, shape: Shape, n: int) -> Path:
    """Write the file of `shape` with n constructs into a root of its own, and return the root."""
    case = root / f"n{n}"
    (case / "src").mkdir(parents=True, exist_ok=True)
    (case / "tsconfig.json").write_text(CONFIG)
    (case / "src" / f"a{shape.suffix}").write_bytes(shape.make(n))
    return case


# The peak memory of the collector, in bytes, for nests that write many names. The memo of the write
# lookup once kept n squared entries (1.5 GB for 8 000 undeclared names, 3.7 GB for 8 000 imported
# names written at the bottom of 8 000 functions, release build), against under 300 MiB for 4.2.
MEMORY_CAP = 300 * 1024 * 1024
MEMORY_CASES = (
    ("writes-distinct-names", 8_000),
    ("writes-imports-all-at-bottom", 4_000),
    ("writes-import-at-own-depth", 4_000),
)
# A process may not take more address space than this on Linux (the limit of AD-319), so a
# regression ends in an error and not in minutes of swapping. macOS has no such limit, and the
# sizes above are small enough to end there.
ADDRESS_SPACE = 4 * 1024**3
_RUSAGE = (
    "import resource, subprocess, sys\n"
    "subprocess.run([sys.argv[1], *sys.argv[3:]], stdin=open(sys.argv[2], 'rb'),"
    " stdout=subprocess.DEVNULL, check=True)\n"
    "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
)


def _limit_address_space() -> None:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, ADDRESS_SPACE))


def _peak_memory(tmp_path: Path, collector: Path, name: str, count: int, walk: bool = False) -> int:
    """The peak resident memory of the collector, in bytes, for the file of `name` and `count`;
    `walk` measures the walk alone (`--dump-count`)."""
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"allowJs":true},"include":["src"]}'
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    for old in (tmp_path / "src").iterdir():
        old.unlink()
    (tmp_path / "src" / f"a{SHAPES[name].suffix}").write_bytes(SHAPES[name].make(count))
    request = tmp_path / "request.bin"
    request.write_bytes(_walk_line(tmp_path, SHAPES[name]) if walk else _request(tmp_path))
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _RUSAGE,
            str(collector),
            str(request),
            *(["--dump-count"] if walk else []),
        ],
        capture_output=True,
        text=True,
        check=False,
        preexec_fn=_limit_address_space if sys.platform == "linux" and not walk else None,
    )
    assert done.returncode == 0, done.stderr[-300:]
    # `ru_maxrss` is in kilobytes on Linux and in bytes on macOS.
    return int(done.stdout) * (1 if sys.platform == "darwin" else 1024)


@pytest.mark.parametrize(("name", "count"), MEMORY_CASES)
def test_writes_keep_the_memory_bounded(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    name: str,
    count: int,
) -> None:
    # These nests have a reply that is quadratic by the data model: the walk alone is measured.
    assert name in WALK_ONLY
    peak = _peak_memory(tmp_path, dump_binary, name, count, walk=True)
    assert peak < MEMORY_CAP, f"{name} n={count}: {peak / 2**20:.0f} MiB"


SITE_PREFIX = "sites-"
