# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335, AD-1252: the memory of the Rust collector is linear in the size of each shape.

Consumer: the entry criteria of slice 5b-1. For each shape the test builds a crate with n and with
2n of one construct and bounds the peak memory of 2n by 2.5 times the peak of n. No test here times
anything. The shapes: many `use` items, a long file of many functions, many attributes, many macro
calls with paths, many files, and trees of modules that are deep (each file declares the next).
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import zlib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

MEMORY_RATIO = 2.5

MANIFEST = '[package]\nname = "app"\nversion = "0.0.0"\n[dependencies]\nserde_json = "1"\n'


@dataclasses.dataclass(frozen=True)
class Shape:
    name: str
    base: int
    make: Callable[[int], dict[str, str]]


def _lines(count: int, line: Callable[[int], str]) -> str:
    return "\n".join(line(index) for index in range(count)) + "\n"


def _uses(n: int) -> dict[str, str]:
    return {"lib.rs": _lines(n, lambda i: f"use std::a{i}::b{i};\nuse serde_json::c{i}::d;")}


def _long_file(n: int) -> dict[str, str]:
    def body(i: int) -> str:
        return f"fn f{i}(x: u8) -> u8 {{ let y = serde_json::go{i}(x); y + std::cmp::max(x, 1) }}"

    return {"lib.rs": _lines(n, body)}


def _attributes(n: int) -> dict[str, str]:
    item = (
        '#[derive(Debug, Clone, serde::Serialize)]\n#[serde(with = "serde_json::codec{i}")]\n'
        "#[allow(dead_code)]\n#[cfg_attr(unix, allow(unused))]\n"
        "pub struct S{i} {{ #[serde(skip)] a: u8 }}"
    )
    return {"lib.rs": _lines(n, lambda i: item.format(i=i))}


def _macros(n: int) -> dict[str, str]:
    call = (
        'fn m{i}() {{ let _ = format!("{{}}", std::mem::size_of::<u8>());'
        ' serde_json::json!({{"a": serde_json::Value::Null}}); }}'
    )
    return {"lib.rs": _lines(n, lambda i: call.format(i=i))}


def _files(n: int) -> dict[str, str]:
    files = {"lib.rs": _lines(n, lambda i: f"mod m{i};")}
    files.update({f"m{i}.rs": f"use serde_json::x{i};\npub fn f() {{}}\n" for i in range(n)})
    return files


DEPTH = 12


def _chain(length: int, prefix: str = "c") -> dict[str, str]:
    """`length` files, each one declaring the next with a path attribute, so each is one deeper."""
    files = {}
    for i in range(length):
        tail = f'#[path = "{prefix}{i + 1}.rs"]\nmod {prefix}{i + 1};\n' if i + 1 < length else ""
        files[f"{prefix}{i}.rs"] = f"use serde_json::x;\n{tail}"
    return files


def _nested(n: int) -> dict[str, str]:
    # n expressions of 100 nested parentheses: below the limit of the walk, above `syn` defaults.
    body = "fn f{i}() {{ let x = " + "(" * 100 + "serde_json::go()" + ")" * 100 + "; }}"
    return {"lib.rs": _lines(n, lambda i: body.format(i=i))}


def _deep(n: int) -> dict[str, str]:
    # n trees of depth 12. Real code nests a few levels; the name of a module holds its whole path.
    files = {"lib.rs": _lines(n, lambda i: f'#[path = "t{i}_0.rs"]\nmod t{i};')}
    for i in range(n):
        files.update(_chain(DEPTH, f"t{i}_"))
    return files


SHAPES = {
    shape.name: shape
    for shape in (
        Shape("uses", 4000, _uses),
        Shape("long-file", 3000, _long_file),
        Shape("attributes", 2000, _attributes),
        Shape("macro-calls", 2000, _macros),
        Shape("many-files", 400, _files),
        Shape("deep-module-trees", 40, _deep),
        Shape("nested-parentheses", 400, _nested),
    )
}


@pytest.fixture(scope="session")
def collector(rust_binary: Path) -> Path:
    other = os.environ.get("ARCHKEEL_SCALING_BINARY")
    return Path(other) if other else rust_binary


def _build_files(root: Path, files: dict[str, str]) -> None:
    crate = root / "crate"
    if crate.exists():
        for old in sorted(crate.rglob("*"), reverse=True):
            old.unlink() if old.is_file() else old.rmdir()
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(MANIFEST)
    for name, text in files.items():
        (crate / "src" / name).write_text(text)


def _build(root: Path, shape: Shape, n: int) -> int:
    """Write the crate of `shape` with n constructs; return the bytes of its largest file."""
    files = shape.make(n)
    _build_files(root, files)
    return max(len(text) for text in files.values())


def _request(root: Path) -> bytes:
    return json.dumps(
        {
            "protocol_version": "8.0.0",
            "snapshot": {"root": str(root), "git_head": "a" * 40, "dirty": False},
            "scope": {"roots": ["crate"], "namespace": "app"},
            "resolver": {"language": "rust"},
        }
    ).encode()


_RUSAGE = (
    "import resource, subprocess, sys\n"
    "subprocess.run([sys.argv[1]], stdin=open(sys.argv[2], 'rb'), stdout=subprocess.DEVNULL,"
    " check=True)\n"
    "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
)


def _peak(binary: Path, root: Path, shape: Shape, n: int) -> int:
    _build(root, shape, n)
    request = root / "request.bin"
    request.write_bytes(_request(root))
    done = subprocess.run(
        [sys.executable, "-c", _RUSAGE, str(binary), str(request)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-300:]
    # `ru_maxrss` is in kilobytes on Linux and in bytes on macOS.
    return int(done.stdout) * (1 if sys.platform == "darwin" else 1024)


@pytest.mark.skipif(
    sys.platform == "win32", reason="the peak memory needs the Unix resource module"
)
@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_peak_memory_of_twice_the_size_is_at_most_two_and_a_half_times(
    tmp_path: Path, collector: Path, name: str
) -> None:
    shape = SHAPES[name]
    peaks = [
        max(_peak(collector, tmp_path, shape, n) for _ in range(3))
        for n in (shape.base * 2, shape.base * 4)
    ]
    print(f"MEMORY {name} peak(N)={peaks[0] / 2**20:.1f} MiB peak(2N)={peaks[1] / 2**20:.1f} MiB")
    assert peaks[1] <= MEMORY_RATIO * peaks[0], f"{name}: {peaks[0]} then {peaks[1]} bytes"


def test_every_shape_builds_a_crate_with_only_the_expected_expansion_gaps(
    tmp_path: Path, collector: Path
) -> None:
    for shape in SHAPES.values():
        _build(tmp_path, shape, 3)
        done = subprocess.run([str(collector)], input=_request(tmp_path), capture_output=True)
        assert done.returncode == 0, shape.name
        import zlib

        facts = json.loads(zlib.decompress(done.stdout))["facts"]
        gaps = facts["coverage"]["gaps"]
        # AD-662: the shape crate has no lock, so no registry identity proves `json!`.
        unread = (
            "The macro serde_json::json! is no macro_rules! of the workspace: "
            "the scan does not read its expansion"
        )
        expected = {
            "attributes": {
                "The attribute macro serde can add code that the scan does not read": 6,
                "The derive macro serde::Serialize can add code that the scan does not read": 3,
            },
            "macro-calls": {unread: 3},
        }.get(shape.name, {})
        assert Counter(gap["title"] for gap in gaps) == expected, shape.name
        assert facts["coverage"]["full_scope"] == (not gaps), shape.name


def test_a_chain_past_the_depth_limit_is_cut_and_its_reply_stays_small(
    tmp_path: Path, collector: Path
) -> None:
    # The name of a module holds its whole path, so the reply of a chain grows with the square
    # of the depth. The walk stops at 64 levels (AD-335), and the rest of the chain is UNKNOWN.
    _build_files(tmp_path, {"lib.rs": '#[path = "c0.rs"]\nmod c0;\n', **_chain(70)})
    done = subprocess.run([str(collector)], input=_request(tmp_path), capture_output=True)
    assert done.returncode == 0, done.stderr[-300:]
    facts = json.loads(zlib.decompress(done.stdout))["facts"]
    # The 64 levels, the library file, and the manifest of the crate.
    assert len(facts["files"]) == 66
    assert any("Modules nest deeper than 64" in gap["title"] for gap in facts["coverage"]["gaps"])
