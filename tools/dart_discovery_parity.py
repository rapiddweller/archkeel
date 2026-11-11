# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the discovery and parse sections of the native Dart collector with Python (#880).

Slices 1 and 3a of PR 8: the native collector selects, reads and parses the sources and builds
the sections that they decide. The tool runs `archkeel-dart-collector --dump` and the Python
`collect` on each corpus, and compares these reply sections: the inputs, the source listing,
the selected files, the file facts, the gaps of the snapshot problems, the gaps of the parse
(`_prepare_sources`) and their evidence.

The Python collector also drops the file fact of a part with no owner and of a `part of` file,
whose facts belong to its library. Such a fact is "deferred" to slices 4a and 4b: it must
belong to a file with a Python `PartError` gap, or to a `part of` file.

`--discovery-only` does not run the Python parse, which is slow on a large corpus. Then a native
parse gap and the missing file fact of a source with a native `SyntaxError` gap are counted as
"checked per file": `tools/dart_syntax_parity.py` compares the parse of each file.

The output gives counts only, never a file name, so a private corpus stays private.

Usage:
    python tools/dart_discovery_parity.py --demos --corpus private=/path/to/app:lib:my_app
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from archkeel.analyzer.dart.collect import _Collection, _file_span, collect
from archkeel.analyzer.dart.parse import parse
from archkeel.analyzer.dart.resolve import Resolver
from archkeel.analyzer.dart.snapshot import SnapshotError, SnapshotProblemKind, read_snapshot
from archkeel.analyzer.dart.syntax import ConcernKind, DirectiveKind, Syntax
from archkeel.ir.facts import stable_id
from archkeel.ir.facts_codec import encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    DartSettings,
    SnapshotInput,
    SourceScope,
    collection_request,
)

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
BINARY = "archkeel-dart-collector"
FIXTURES = ("G-dart", "H-uml-dart", "I-flutter-shop", "J-compass")
# The gaps that the discovery decides: the kinds of `snapshot.SnapshotProblemKind`.
SNAPSHOT_KINDS = frozenset(kind.value for kind in SnapshotProblemKind)
# The Python gaps that remove a file fact, which slices 4a and 4b of #880 add.
DEFERRED_KINDS = frozenset({"PartError"})
# The gap kinds that `_prepare_sources` writes for the concerns of a parse.
PARSE_KINDS = frozenset(
    {"SyntaxError", "DirectiveError", "UnsupportedDeclaration"}
    | {kind.value for kind in ConcernKind}
)
JsonObject = dict[str, object]


@dataclass(frozen=True)
class Corpus:
    """One snapshot with the scan roots and the namespace of its configuration."""

    name: str
    root: Path
    roots: tuple[str, ...]
    namespace: str


@dataclass
class Result:
    """The parity of one or more snapshots of a corpus."""

    name: str
    files: int = 0
    equal_files: int = 0
    deferred: int = 0
    per_file: int = 0
    gaps: int = 0
    equal_gaps: int = 0
    parse_gaps: int = 0
    equal_parse_gaps: int = 0
    rust_nanos: int = 0
    python_nanos: int = 0
    problems: list[str] = field(default_factory=list)


def build(*, release: bool = True) -> Path:
    """Build the native collector and return the binary."""
    profile = ["--release"] if release else []
    # The test-only `dump` feature gets its own target dir: a plain build of the same crate
    # elsewhere (make native-check, another test) must never replace this binary.
    target = Path(os.environ.get("CARGO_TARGET_DIR", NATIVE / "target")) / "dart-dump"
    command = ["cargo", "build", "--locked", *profile, "-p", BINARY, "--features", "dump"]
    command += ["--target-dir", str(target)]
    subprocess.run(command, cwd=NATIVE, check=True, capture_output=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    return target / ("release" if release else "debug") / f"{BINARY}{suffix}"


def native(binary: Path, corpus: Corpus) -> JsonObject:
    command = [str(binary), "--dump", str(corpus.root), corpus.namespace, *corpus.roots]
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    value: JsonObject = json.loads(run.stdout)
    return value


def request(corpus: Corpus) -> CollectionRequest:
    snapshot = SnapshotInput(str(corpus.root), "parity", False)
    return collection_request(snapshot, SourceScope(corpus.roots, corpus.namespace), DartSettings())


def parse_gap_ids(rel: str, syntax: Syntax) -> list[str]:
    """The ids of the gaps that `_Collection._prepare_sources` writes for one parse."""
    ids = []
    if syntax.first_error is not None:
        message = "syntax errors prevent complete source facts"
        ids.append(stable_id("COVERAGE", rel, syntax.first_error.line, "SyntaxError", message))
    kinds = {
        ConcernKind.UNSUPPORTED_DIRECTIVE: "DirectiveError",
        ConcernKind.UNSUPPORTED_DECLARATION: "UnsupportedDeclaration",
    }
    for concern in syntax.concerns:
        if concern.kind == ConcernKind.SYNTAX_ERROR and syntax.first_error is not None:
            continue
        kind = kinds.get(concern.kind, concern.kind.value)
        ids.append(stable_id("COVERAGE", rel, concern.span.line, kind, concern.message))
    return ids


def python(
    corpus: Corpus, *, full: bool
) -> tuple[JsonObject | str, int, tuple[set[str], set[str]], JsonObject]:
    """The Python reply facts as JSON or the error text, the discovery time, the parts and the
    ids of the parse gaps.

    `full` runs the whole Python collection. Otherwise the Python records code runs without
    the parse, which takes most of the time on a large corpus: each source counts as a parsed
    library, as in the native slice 1, and only the snapshot problems give gaps.
    """
    started = time.perf_counter_ns()
    try:
        snapshot = read_snapshot(request(corpus))
    except SnapshotError as error:
        return str(error), time.perf_counter_ns() - started, (set(), set()), {}
    nanos = time.perf_counter_ns() - started
    package: JsonObject = {
        "package_name": snapshot.package_name,
        "sdk_constraint": snapshot.sdk_constraint,
        "sdk_state": snapshot.sdk_constraint_state.value,
    }
    parts: set[str] = set()
    parse_ids: set[str] = set()
    if full:
        for source in snapshot.sources:
            syntax = parse(source.content)
            parse_ids.update(parse_gap_ids(source.rel_path, syntax))
            if any(item.kind == DirectiveKind.PART_OF for item in syntax.directives):
                parts.add(source.rel_path)
        facts_value = collect(request(corpus))
    else:
        collection = _Collection(request(corpus), snapshot, {}, Resolver(snapshot, {}))
        collection.parsed = {source.rel_path for source in snapshot.sources}
        collection.modules = {source.rel_path: source.module for source in snapshot.sources}
        for problem in snapshot.problems:
            collection._gap(problem.path, _file_span(), problem.kind, problem.message)
        facts_value = collection._source_facts()
    payload = json.loads(encode_response(CollectionResponse(facts_value)))
    facts: JsonObject = payload["facts"]
    return facts, nanos, (parts, parse_ids), package


def by(items: object, key: str) -> dict[str, JsonObject]:
    assert isinstance(items, list)
    return {str(item[key]): item for item in items}


def compare(corpus: Corpus, binary: Path, result: Result, *, full: bool = True) -> None:
    rust = native(binary, corpus)
    reference, nanos, parsed, package = python(corpus, full=full)
    result.rust_nanos += int(str(rust["nanos"]))
    result.python_nanos += nanos
    if isinstance(reference, str) or "error" in rust:
        if not same_error(rust.get("error"), reference):
            result.problems.append("the collection errors differ")
        return
    for key, value in package.items():
        if rust[key] != value:
            result.problems.append(f"{key} differs")
    coverage = reference["coverage"]
    assert isinstance(coverage, Mapping)
    source = reference["source"]
    assert isinstance(source, Mapping)
    for key, expected in (
        ("source_digest", source["source_digest"]),
        ("scope", source["scope"]),
        ("selected_files", coverage["selected_files"]),
        ("inputs", reference["inputs"]),
    ):
        if rust[key] != expected:
            result.problems.append(f"{key} differs")
    compare_files(rust, reference, (coverage["gaps"], parsed, full), result)


def same_error(rust: object, python: object) -> bool:
    """Both stop. An OS error differs after its named prefix, such as `cannot resolve ...: `."""
    if not isinstance(rust, str) or not isinstance(python, str):
        return False
    prefix, separator, _ = rust.partition(": ")
    return rust == python or (bool(separator) and python.startswith(prefix + separator))


def compare_files(
    rust: JsonObject,
    reference: JsonObject,
    removed: tuple[object, tuple[set[str], set[str]], bool],
    result: Result,
) -> None:
    gaps, (parts, parse_ids), full = removed
    python_gaps = by(gaps, "id")
    snapshot_gaps = {key: gap for key, gap in python_gaps.items() if gap["kind"] in SNAPSHOT_KINDS}
    parse_gaps = {key: python_gaps[key] for key in parse_ids if key in python_gaps}
    if len(parse_gaps) != len(parse_ids):
        result.problems.append("a parse gap is not in the Python reply")
    rust_gaps = by(rust["gaps"], "id")
    result.gaps += len(snapshot_gaps)
    result.equal_gaps += sum(rust_gaps.get(key) == gap for key, gap in snapshot_gaps.items())
    result.parse_gaps += len(parse_gaps)
    result.equal_parse_gaps += sum(rust_gaps.get(key) == gap for key, gap in parse_gaps.items())
    extra = {key: gap for key, gap in rust_gaps.items() if key not in snapshot_gaps}
    if full and set(extra) != set(parse_gaps):
        result.problems.append("the set of parse gaps differs")
    if not full:
        result.per_file += len(extra)
        if any(gap["kind"] not in PARSE_KINDS for gap in extra.values()):
            result.problems.append("a native gap is neither a snapshot nor a parse gap")
    if not set(snapshot_gaps) <= set(rust_gaps):
        result.problems.append("a snapshot gap is missing")
    deferred_paths = parts | {
        str(gap["data"]["file"])  # type: ignore[index]
        for gap in python_gaps.values()
        if gap["kind"] in DEFERRED_KINDS
    }
    python_files = by(reference["files"], "rel_path")
    rust_files = by(rust["files"], "rel_path")
    python_evidence = by(reference["evidence"], "id")
    rust_evidence = by(rust["evidence"], "id")
    cited = [
        str(item["evidence_id"]) for item in python_files.values() if item["rel_path"] in rust_files
    ]
    for gap in [*snapshot_gaps.values(), *parse_gaps.values()]:
        cited += [str(key) for key in gap["evidence_ids"]]  # type: ignore[attr-defined]
    if any(python_evidence[key] != rust_evidence.get(key) for key in cited):
        result.problems.append("the evidence of a file or a gap differs")
    for path, fact in rust_files.items():
        result.files += 1
        if path in python_files:
            result.equal_files += python_files[path] == fact
        elif path in deferred_paths:
            result.deferred += 1
        else:
            result.problems.append("a file fact is not in the Python reply and is not deferred")
    syntax_paths = {
        str(gap["data"]["file"])  # type: ignore[index]
        for gap in extra.values()
        if gap["kind"] == "SyntaxError"
    }
    missing = set(python_files) - set(rust_files)
    if full and missing:
        result.problems.append("a Python file fact is missing")
    if not full and missing - syntax_paths:
        result.problems.append("a Python file fact is missing and native has no SyntaxError gap")


def configured(name: str, root: Path) -> Corpus:
    scan = tomllib.loads((root / "archkeel.toml").read_text(encoding="utf-8"))["scan"]
    return Corpus(name, root, tuple(scan["roots"]), scan["namespace"])


def demo_variants(scratch: Path) -> Iterator[Corpus]:
    """Each Dart and Flutter demo variant as a copy of its fixture with the overlay applied."""
    sys.path.insert(0, str(ROOT))
    for name, fixture in (("dart", "G-dart"), ("flutter", "I-flutter-shop")):
        catalog = importlib.import_module(f"fixtures.demo_catalog_{name}")
        for index, variant in enumerate(catalog.VARIANTS):
            root = scratch / f"{name}-{index}"
            shutil.copytree(ROOT / "fixtures" / fixture, root)
            apply_overlay(root, variant.files)
            yield configured("demo variants", root)


def apply_overlay(root: Path, files: Mapping[str, str | None]) -> None:
    for relative, text in files.items():
        path = root / relative
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")


def named(item: str) -> Corpus:
    """`NAME=PATH[:ROOT[:NAMESPACE]]`; without a root, the `archkeel.toml` of PATH decides."""
    name, _, spec = item.partition("=")
    path, _, rest = spec.partition(":")
    if not rest:
        return configured(name, Path(path))
    root, _, namespace = rest.partition(":")
    return Corpus(name, Path(path), (root,), namespace or "bench")


def corpora(demos: bool, items: Sequence[str], scratch: Path) -> Iterator[Corpus]:
    if demos:
        yield from (configured(name, ROOT / "fixtures" / name) for name in FIXTURES)
        yield from demo_variants(scratch)
    yield from (named(item) for item in items)


def run(binary: Path, demos: bool, items: Sequence[str], *, full: bool = True) -> list[Result]:
    results: dict[str, Result] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for corpus in corpora(demos, items, Path(scratch)):
            result = results.setdefault(corpus.name, Result(corpus.name))
            compare(corpus, binary, result, full=full)
    return list(results.values())


def report(result: Result) -> str:
    return (
        f"{result.name}: files {result.equal_files}/{result.files} equal "
        f"({result.deferred} deferred to slices 4a and 4b), snapshot gaps "
        f"{result.equal_gaps}/{result.gaps} equal, parse gaps "
        f"{result.equal_parse_gaps}/{result.parse_gaps} equal"
        f"{f' ({result.per_file} checked per file)' if result.per_file else ''}; Rust "
        f"{result.rust_nanos / 1e6:.1f} ms, Python {result.python_nanos / 1e6:.1f} ms"
        + "".join(f"\n  problem: {problem}" for problem in sorted(set(result.problems)))
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--demos", action="store_true", help="the Dart fixtures and demos")
    arguments.add_argument("--corpus", action="append", default=[], metavar="NAME=PATH[:ROOT]")
    arguments.add_argument(
        "--discovery-only",
        action="store_true",
        help="no Python parse (fast on a large corpus); the parse is checked per file",
    )
    options = arguments.parse_args(argv)
    results = run(build(), options.demos, options.corpus, full=not options.discovery_only)
    for result in results:
        print(report(result))
    return 0 if all(not result.problems for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
