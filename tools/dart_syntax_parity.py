# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the per-file Dart syntax of the native collector with Python `parse` (#880).

Slice 3 of PR 8: `archkeel-dart-collector --dump-syntax` prints the syntax of each file:
the definitions, the directives, the sites, the concerns, the first error, `complete` and the
language version. The tool compares it with `dataclasses.asdict(parse(content))`, as canonical
JSON, byte for byte.

The Python parse is slow, so `--budget` stops a corpus after that many seconds of Python time.
The files of a corpus are compared in a fixed shuffled order, so a partial run is a sample.
A file where Python stops with `RecursionError` is the closed exception of AD-369: native must
give the deep-nesting concern. A file with a code point that Unicode 14 does not assign is the
stricter difference of L-27: native gives a named gap, so the file is counted, not compared.
A file where the native site walks pass their work limit is the stricter difference of AD-376:
native gives a named gap, so the file is counted, not compared. The report gives the highest
share of the work limit that a file used.

The oracle is Python 3.11 with Unicode 14.0.0 (L-27): the tool refuses another interpreter.

The output gives counts only, never a file name, so a private corpus stays private.

Usage:
    python tools/dart_syntax_parity.py --demos --corpus bench=/path/to/repo --budget 60
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archkeel.analyzer.dart.parse import parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dart_discovery_parity import (  # noqa: E402
    FIXTURES,
    ROOT,
    build,
    demo_variants,
)

EXCLUDED = frozenset({".dart_tool", "pubcache", ".pub-cache", ".git"})
DEEP = "Dart source nests deeper than"
UNASSIGNED = "Dart source holds a code point that Unicode 14 does not assign."
STOPPED = "The site analysis of this Dart source stops: "
ORACLE = ((3, 11), "14.0.0")


@dataclass
class Result:
    """The parity of the files of one corpus."""

    name: str
    files: int = 0
    equal: int = 0
    total: int = 0
    deep: int = 0
    unassigned: int = 0
    stopped: int = 0
    work_permille: int = 0
    rust_nanos: int = 0
    python_nanos: int = 0
    problems: list[str] = field(default_factory=list)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def python_syntax(content: bytes) -> tuple[str | None, int]:
    """The canonical JSON of the Python syntax, or None on `RecursionError`."""
    started = time.perf_counter_ns()
    try:
        value = dataclasses.asdict(parse(content))
    except RecursionError:
        return None, time.perf_counter_ns() - started
    return canonical(value), time.perf_counter_ns() - started


def native_rows(binary: Path, paths: Sequence[Path]) -> list[dict[str, Any]]:
    """One JSON object for each path: the syntax, the parse time and the share of work."""
    command = [str(binary), "--dump-syntax"]
    text = "".join(f"{path}\n" for path in paths)
    run = subprocess.run(command, input=text, capture_output=True, text=True, check=True)
    # `str.splitlines` also splits at U+2028, which a JSON string can hold.
    return [json.loads(line) for line in run.stdout.split("\n") if line]


def native_syntax(binary: Path, paths: Sequence[Path]) -> list[tuple[str, int, object]]:
    lines = native_rows(binary, paths)
    return [(canonical(line["syntax"]), int(line["nanos"]), line["syntax"]) for line in lines]


def dart_files(root: Path) -> list[Path]:
    found = [
        path
        for path in root.rglob("*.dart")
        if path.is_file()
        and not path.is_symlink()
        and not EXCLUDED.intersection(path.relative_to(root).parts)
    ]
    found.sort()
    random.Random(880).shuffle(found)
    return found


def compare(binary: Path, root: Path, result: Result, budget: float | None) -> None:
    files = dart_files(root)
    result.total += len(files)
    spent = result.python_nanos
    batch = 64
    for start in range(0, len(files), batch):
        if budget is not None and spent / 1e9 >= budget:
            return
        chunk = files[start : start + batch]
        rows = native_rows(binary, chunk)
        for path, row in zip(chunk, rows, strict=True):
            value = row["syntax"]
            text, nanos = canonical(value), int(row["nanos"])
            result.work_permille = max(result.work_permille, int(row["work_permille"]))
            if budget is not None and spent / 1e9 >= budget:
                return
            expected, python_nanos = python_syntax(path.read_bytes())
            spent += python_nanos
            result.python_nanos += python_nanos
            result.rust_nanos += nanos
            result.files += 1
            concerns = value["concerns"]
            if any(item["message"] == UNASSIGNED for item in concerns):
                result.unassigned += 1
            elif any(item["message"].startswith(STOPPED) for item in concerns):
                result.stopped += 1
            elif expected is None:
                result.deep += 1
                if any(DEEP in item["message"] for item in concerns):
                    result.equal += 1
                else:
                    result.problems.append("Python stops with RecursionError, native has no gap")
            elif expected == text:
                result.equal += 1
            else:
                result.problems.append(difference(expected, text))


def difference(expected: str, actual: str) -> str:
    """The first differing key path, never the content."""
    left, right = json.loads(expected), json.loads(actual)

    def walk(a: object, b: object, path: str) -> str | None:
        if type(a) is not type(b):
            return path or "/"
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    return f"{path}/{key}"
                found = walk(a[key], b[key], f"{path}/{key}")
                if found:
                    return found
            return None
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return f"{path}[len]"
            for index, (x, y) in enumerate(zip(a, b, strict=True)):
                found = walk(x, y, f"{path}[{index}]")
                if found:
                    return found
            return None
        return None if a == b else path

    return f"the syntax differs at {walk(left, right, '')}"


def corpora(demos: bool, items: Sequence[str], scratch: Path) -> Iterator[tuple[str, Path]]:
    if demos:
        yield from ((name, ROOT / "fixtures" / name) for name in FIXTURES)
        yield from ((corpus.name, corpus.root) for corpus in demo_variants(scratch))
    for item in items:
        name, _, path = item.partition("=")
        yield name, Path(path)


def report(result: Result) -> str:
    return (
        f"{result.name}: {result.equal}/{result.files} files equal "
        f"(of {result.total}; {result.deep} with RecursionError in Python, "
        f"{result.unassigned} named by L-27, {result.stopped} stopped by the site work limit; "
        f"site work at most {result.work_permille / 10:.1f} % of the limit); "
        f"parse Rust {result.rust_nanos / 1e6:.1f} ms, Python {result.python_nanos / 1e6:.1f} ms"
        + "".join(f"\n  problem: {problem}" for problem in sorted(set(result.problems)))
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--demos", action="store_true", help="the Dart fixtures and demos")
    arguments.add_argument("--corpus", action="append", default=[], metavar="NAME=PATH")
    arguments.add_argument("--budget", type=float, help="Python seconds for each corpus")
    arguments.add_argument("--debug", action="store_true", help="a debug build of the binary")
    options = arguments.parse_args(argv)
    if (sys.version_info[:2], unicodedata.unidata_version) != ORACLE:
        print("the oracle is Python 3.11 with Unicode 14.0.0 (L-27)", file=sys.stderr)
        return 2
    print(f"oracle: Python {sys.version.split()[0]}, Unicode {unicodedata.unidata_version}")
    binary = build(release=not options.debug)
    results: dict[str, Result] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for name, root in corpora(options.demos, options.corpus, Path(scratch)):
            result = results.setdefault(name, Result(name))
            compare(binary, root, result, options.budget)
    for result in results.values():
        print(report(result))
    return 0 if all(not result.problems for result in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
