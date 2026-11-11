# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the vendored Rust Dart grammar with the Python grammar on a corpus (AD-342).

The Python collector parses with `tree_sitter_dart` 0.1.0. The native crate
`archkeel-dart-grammar` vendors the C parser of the same release. This tool parses each `.dart`
file with both and compares the full trees: each node in preorder, with all anonymous nodes, its
field, its byte range and the missing and extra flags. It also adds up the parse time of each
side.

The output gives counts only, never a file name, so a private corpus stays private. Use
`--show-differences` to name the files that differ in a corpus that you can publish.

Usage:
    python tools/dart_grammar_parity.py --demos --corpus private=/path/to/app
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_dart
from tree_sitter import Language, Parser, Tree

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
EXAMPLE = "tree_digest"
# The Dart fixtures of the repository. The demo variants are added from the demo catalogs.
FIXTURES = ("G-dart", "H-uml-dart", "I-flutter-shop", "J-compass")


@dataclass(frozen=True)
class Parsed:
    """The tree digest and the parse time of one file on one side."""

    digest: str
    nanos: int


@dataclass(frozen=True)
class CorpusResult:
    """The parity of one corpus: equal files, all files and the parse time of each side."""

    name: str
    equal: int
    total: int
    rust_nanos: int
    python_nanos: int
    different: tuple[Path, ...]


def tree_text(tree: Tree) -> str:
    """The tree as text: one line per node, the same text as `examples/tree_digest.rs`."""
    lines = []
    cursor = tree.walk()
    depth = 0
    while True:
        node = cursor.node
        assert node is not None
        named, missing, extra = (
            int(flag) for flag in (node.is_named, node.is_missing, node.is_extra)
        )
        lines.append(
            f"{depth} {node.type} {named} {cursor.field_name or '-'} "
            f"{node.start_byte} {node.end_byte} {missing} {extra}\n"
        )
        if cursor.goto_first_child():
            depth += 1
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                return "".join(lines)
            depth -= 1


def parse_python(paths: Sequence[Path]) -> list[Parsed]:
    parser = Parser(Language(tree_sitter_dart.language()))
    parsed = []
    for path in paths:
        source = path.read_bytes()
        started = time.perf_counter_ns()
        tree = parser.parse(source)
        nanos = time.perf_counter_ns() - started
        parsed.append(Parsed(hashlib.sha256(tree_text(tree).encode()).hexdigest(), nanos))
    return parsed


def build_rust(*, release: bool = True) -> Path:
    """Build the Rust half and return it.

    The release build is the build of the collector binary, so its parse time is the number to
    report. A test that compares only the trees uses the faster debug build.
    """
    profile = ["--release"] if release else []
    command = ["cargo", "build", "--locked", *profile, "-p", "archkeel-dart-grammar"]
    subprocess.run([*command, "--example", EXAMPLE], cwd=NATIVE, check=True, capture_output=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", NATIVE / "target"))
    suffix = ".exe" if sys.platform == "win32" else ""
    return target / ("release" if release else "debug") / "examples" / f"{EXAMPLE}{suffix}"


def parse_rust(binary: Path, paths: Sequence[Path]) -> list[Parsed]:
    text = "".join(f"{path}\n" for path in paths)
    run = subprocess.run([binary], input=text, capture_output=True, text=True, check=True)
    parsed = []
    for line in run.stdout.splitlines():
        digest, nanos = line.split("\t")
        parsed.append(Parsed(digest, int(nanos)))
    if len(parsed) != len(paths):
        raise RuntimeError(f"the Rust half gave {len(parsed)} results for {len(paths)} files")
    return parsed


def compare(name: str, binary: Path, paths: Sequence[Path]) -> CorpusResult:
    rust = parse_rust(binary, paths)
    python = parse_python(paths)
    different = tuple(
        path for path, a, b in zip(paths, rust, python, strict=True) if a.digest != b.digest
    )
    return CorpusResult(
        name,
        len(paths) - len(different),
        len(paths),
        sum(item.nanos for item in rust),
        sum(item.nanos for item in python),
        different,
    )


def dart_files(root: Path) -> list[Path]:
    """The `.dart` files below `root`, without build output and hidden directories."""
    skipped = {"build", ".dart_tool", ".git", ".pub-cache", "node_modules"}
    files: list[Path] = []
    for directory, names, filenames in os.walk(root):
        names[:] = sorted(
            name for name in names if name not in skipped and not name.startswith(".")
        )
        files.extend(Path(directory, name) for name in sorted(filenames) if name.endswith(".dart"))
    return files


def demo_variant_files(destination: Path) -> list[Path]:
    """Write each distinct `.dart` text of the Dart and Flutter demo catalogs to `destination`."""
    # The catalogs live in `fixtures/`, which is not a package of the tools: load them by name.
    sys.path.insert(0, str(ROOT))
    catalogs = [
        importlib.import_module(f"fixtures.demo_catalog_{name}") for name in ("dart", "flutter")
    ]
    texts = {
        text
        for catalog in catalogs
        for variant in catalog.VARIANTS
        for relative, text in variant.files.items()
        if relative.endswith(".dart") and text is not None
    }
    paths = []
    for index, text in enumerate(sorted(texts)):
        path = destination / f"variant_{index}.dart"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def corpora(demos: bool, named: Iterable[str], scratch: Path) -> list[tuple[str, list[Path]]]:
    result: list[tuple[str, list[Path]]] = []
    if demos:
        result.extend((fixture, dart_files(ROOT / "fixtures" / fixture)) for fixture in FIXTURES)
        result.append(("demo variants", demo_variant_files(scratch)))
    for item in named:
        name, _, path = item.partition("=")
        result.append((name, dart_files(Path(path))))
    return result


def report(result: CorpusResult, show_differences: bool) -> str:
    line = (
        f"{result.name}: {result.equal}/{result.total} equal trees; parse time "
        f"Rust {result.rust_nanos / 1e6:.1f} ms, Python {result.python_nanos / 1e6:.1f} ms"
    )
    if show_differences:
        line += "".join(f"\n  differs: {path}" for path in result.different)
    return line


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--demos", action="store_true", help="the Dart fixtures and demos")
    arguments.add_argument("--corpus", action="append", default=[], metavar="NAME=PATH")
    arguments.add_argument("--show-differences", action="store_true")
    options = arguments.parse_args(argv)
    binary = build_rust()
    equal = True
    with tempfile.TemporaryDirectory() as scratch:
        for name, paths in corpora(options.demos, options.corpus, Path(scratch)):
            result = compare(name, binary, paths)
            equal = equal and result.equal == result.total
            print(report(result, options.show_differences))
    return 0 if equal else 1


if __name__ == "__main__":
    raise SystemExit(main())
