# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare raw Dart collection assembly with real Python functions (AD-400)."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from archkeel.analyzer.dart.collect import _Collection
from archkeel.analyzer.dart.parse import parse
from archkeel.analyzer.dart.resolve import ResolvedSite, Resolver
from archkeel.analyzer.dart.snapshot import Snapshot, read_snapshot
from archkeel.analyzer.dart.syntax import DefinitionKind, DirectiveKind, SiteKind, Syntax
from archkeel.ir.facts_codec import _target_payload

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dart_declarations_parity as declarations  # noqa: E402
from dart_discovery_parity import (  # noqa: E402
    FIXTURES,
    ROOT,
    Corpus,
    build,
    configured,
    demo_variants,
    request,
)


class CachedResolver(Resolver):
    """Keep real site answers for one input instead of repeating the quadratic Python walk."""

    def __init__(self, snapshot: Snapshot, syntax: dict[str, Syntax]) -> None:
        super().__init__(snapshot, syntax)
        self.site_answers: dict[str, tuple[ResolvedSite, ...]] = {}

    def resolved_sites(self, rel_path: str) -> tuple[ResolvedSite, ...]:
        if rel_path not in self.site_answers:
            self.site_answers[rel_path] = super().resolved_sites(rel_path)
        return self.site_answers[rel_path]


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=sorted
    )


def layer_input(c: _Collection) -> dict[str, Any]:
    prepared = declarations.layer_input(c)
    constructors = {file["rel"]: file["constructors"] for file in prepared["files"]}
    files = []
    directives, names, sites, constructions = [], {}, [], []
    for source in c.snapshot.sources:
        rel = source.rel_path
        syntax = c.syntax[rel]
        files.append(
            {
                "file": {
                    "rel": rel,
                    "module": source.module,
                    "source_len": len(source.content),
                    "first_line": next(
                        iter(source.content.decode("utf-8", "replace").splitlines()), None
                    ),
                    "syntax": dataclasses.asdict(syntax),
                    "constructors": constructors.get(rel, []),
                },
                "content": source.content.decode("utf-8", "replace"),
                "owner": c.resolver.module_for(rel),
            }
        )
        if rel not in c.parsed:
            continue
        for directive in syntax.directives:
            if directive.kind in {DirectiveKind.IMPORT, DirectiveKind.EXPORT}:
                directives.append(
                    {
                        "rel": rel,
                        "start": directive.span.start_byte,
                        "targets": [
                            dataclasses.asdict(value)
                            for value in c.resolver.resolve_directive(rel, directive)
                        ],
                    }
                )
        for definition in syntax.definitions:
            for name in (*definition.extends, *definition.with_types, *definition.implements):
                names[(rel, name)] = c.resolver.resolve_name(rel, name)
            if definition.kind == DefinitionKind.TYPEDEF and definition.alias is not None:
                names[(rel, definition.alias)] = c.resolver.resolve_name(rel, definition.alias)
        resolved = c.resolver.resolved_sites(rel)
        sites.append({"rel": rel, "sites": [dataclasses.asdict(value) for value in resolved]})
        for value in resolved:
            if value.site.kind in {SiteKind.CALL, SiteKind.CREATION}:
                constructions.append(
                    {
                        "rel": rel,
                        "start": value.site.span.start_byte,
                        "expression": value.site.expression,
                        "resolution": dataclasses.asdict(
                            c.resolver.resolve_construction(rel, value.site)
                        ),
                    }
                )
    unique_constructions = {
        (item["rel"], item["start"], item["expression"]): item for item in constructions
    }
    return {
        "files": files,
        "package_name": c.snapshot.package_name,
        "sdk_state": c.snapshot.sdk_constraint_state.value,
        "sdk": c.snapshot.sdk_constraint,
        "roots": c.snapshot.roots,
        "inputs": [dataclasses.asdict(item) for item in c.snapshot.inputs],
        "git_head": c.request.snapshot.git_head,
        "dirty": c.request.snapshot.dirty,
        "problems": [
            {"path": item.path, "kind": item.kind, "message": item.message, "span": None}
            for item in c.snapshot.problems
        ],
        "resolver": {
            "directives": directives,
            "names": [
                {"rel": rel, "name": name, "targets": targets}
                for (rel, name), targets in sorted(names.items())
            ],
            "sites": sites,
            "constructions": list(unique_constructions.values()),
            "problems": [
                {
                    "path": item.path,
                    "kind": "DirectiveError" if item.kind == "ImportError" else item.kind,
                    "message": item.message,
                    "span": None if item.span is None else dataclasses.asdict(item.span),
                }
                for item in c.resolver.problems
            ],
        },
    }


def python(c: _Collection) -> dict[str, Any]:
    reference = _Collection(c.request, c.snapshot, c.syntax, c.resolver)
    facts = reference.facts()
    return {
        "full_scope": facts.coverage.full_scope,
        "selected_files": facts.coverage.selected_files,
        "files_read": facts.coverage.files_read,
        "files_parsed": facts.coverage.files_parsed,
        "inputs": [dataclasses.asdict(item) for item in facts.inputs],
        "source_digest": facts.source.source_digest,
        "scope": facts.source.scope,
        "git_head": facts.source.git_head,
        "dirty": facts.source.dirty,
        "capabilities": dataclasses.asdict(facts.capabilities),
        "files": [dataclasses.asdict(item) for item in facts.files],
        "symbols": sorted(reference.symbols, key=lambda item: item["id"]),
        "imports": sorted(reference.imports, key=lambda item: item["id"]),
        "calls": sorted(reference.calls, key=lambda item: item["id"]),
        "references": sorted(reference.references, key=lambda item: item["id"]),
        "bindings": reference.bindings,
        "targets": [_target_payload(item) for item in reference.targets],
        "gaps": [item for _, item in sorted(reference.gaps.items())],
        "evidence": [item for _, item in sorted(reference.evidence.items())],
    }


def native(binary: Path, value: dict[str, Any]) -> dict[str, Any]:
    return native_rows(binary, [value])[0]


def native_rows(binary: Path, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run = subprocess.run(
        [str(binary), "--dump-collection"],
        input="".join(canonical(value) + "\n" for value in values),
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    if len(rows) != len(values):
        raise AssertionError("the collection dump dropped or added a result")
    return rows


def prepared(corpus: Corpus, binary: Path | None = None) -> _Collection:
    snapshot = read_snapshot(request(corpus))
    if binary is None:
        syntax = {source.rel_path: parse(source.content) for source in snapshot.sources}
    else:
        run = subprocess.run(
            [str(binary), "--dump-syntax"],
            input="".join(str(corpus.root / source.rel_path) + "\n" for source in snapshot.sources),
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        parsed = [json.loads(line)["syntax"] for line in run.stdout.splitlines()]
        syntax = {
            source.rel_path: declarations.decode(Syntax, value)
            for source, value in zip(snapshot.sources, parsed, strict=True)
        }
    result = _Collection(request(corpus), snapshot, syntax, CachedResolver(snapshot, syntax))
    result._prepare_sources()
    return result


def compare(binary: Path, c: _Collection) -> tuple[dict[str, Any], dict[str, Any]]:
    value = layer_input(c)
    actual = native(binary, value)
    actual.pop("work", None)
    return actual, python(c)


def timed_compare(binary: Path, c: _Collection) -> dict[str, Any]:
    sources = c.snapshot.sources
    shapes = list(c.syntax.values())
    result: dict[str, Any] = {
        "rel": sources[0].rel_path if len(sources) == 1 else "<project>",
        "files": len(sources),
        "bytes": sum(len(source.content) for source in sources),
        "definitions": sum(len(syntax.definitions) for syntax in shapes),
        "members": sum(
            len(definition.members) for syntax in shapes for definition in syntax.definitions
        ),
        "sites": sum(len(syntax.sites) for syntax in shapes),
    }
    print("START", canonical(result), flush=True)
    start = time.monotonic()
    value = layer_input(c)
    after_input = time.monotonic()
    print("INPUT-DONE", result["rel"], f"{after_input - start:.3f}s", flush=True)
    actual = native(binary, value)
    after_native = time.monotonic()
    result["work"] = actual.pop("work")
    expected = python(c)
    after_python = time.monotonic()
    result.update(
        input_seconds=after_input - start,
        native_seconds=after_native - after_input,
        python_seconds=after_python - after_native,
        wall_seconds=after_python - start,
    )
    named = [
        gap["data"]["message"]
        for gap in actual["gaps"]
        if gap["data"]["message"].startswith(
            ("CollectionWorkLimit:", "LanguageVersionOrderGap:", "LanguageVersionDigitLimit:")
        )
    ]
    result["status"] = (
        "equal" if canonical(actual) == canonical(expected) else "gap" if named else "different"
    )
    result["named_gaps"] = named
    if result["status"] == "different":
        result["different_sections"] = [
            key for key in actual if canonical(actual[key]) != canonical(expected[key])
        ]
    print("FINISH", canonical(result), flush=True)
    return result


def references(c: _Collection, whole: bool) -> Iterator[_Collection]:
    if whole:
        yield c
        return
    for source in c.snapshot.sources:
        snapshot = dataclasses.replace(
            c.snapshot,
            sources=(source,),
            inputs=tuple(
                item
                for item in c.snapshot.inputs
                if not item.path.endswith(".dart") or item.path == source.rel_path
            ),
        )
        resolver = copy.copy(c.resolver)
        resolver.problems = list(c.resolver.problems)
        if isinstance(resolver, CachedResolver):
            resolver.site_answers = {}
        reference = _Collection(
            c.request, snapshot, {source.rel_path: c.syntax[source.rel_path]}, resolver
        )
        reference._prepare_sources()
        yield reference


def checked_corpus(binary: Path, corpus: Corpus, output: Path | None) -> list[int]:
    print("CORPUS", corpus.name, "prepare", flush=True)
    c = prepared(corpus, binary)
    run = hashlib.sha256(
        binary.read_bytes()
        + Path(__file__).read_bytes()
        + canonical([dataclasses.asdict(item) for item in c.snapshot.inputs]).encode()
    ).hexdigest()
    path = None if output is None else output / f"{corpus.name.replace('/', '_')}.jsonl"
    done = {}
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            data = path.read_bytes()
            if data and not data.endswith(b"\n"):
                path.write_bytes(data[: data.rfind(b"\n") + 1])
            done = {
                row["rel"]: row
                for line in path.read_text().splitlines()
                if (row := json.loads(line))["run"] == run
            }
    totals = [0, 0, 0, 0]
    for reference in references(c, corpus.name in FIXTURES or corpus.name == "demo variants"):
        rel = (
            reference.snapshot.sources[0].rel_path
            if len(reference.snapshot.sources) == 1
            else "<project>"
        )
        row = done.get(rel)
        if row is None:
            row = {"run": run, **timed_compare(binary, reference)}
            if path is not None:
                with path.open("a") as stream:
                    stream.write(canonical(row) + "\n")
        count = row["files"]
        totals[0] += count
        totals[{"equal": 1, "gap": 2, "different": 3}[row["status"]]] += count
        if row["wall_seconds"] > 60:
            print("OVER-60-SECONDS", canonical(row), flush=True)
        if row["status"] == "different":
            break
    return totals


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--demos", action="store_true")
    args.add_argument("--corpus", action="append", default=[])
    args.add_argument(
        "--output-dir",
        type=Path,
        help="Append per-file timings and resume matching inputs and binary",
    )
    options = args.parse_args()
    binary = build()
    rows: dict[str, list[int]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        corpora: list[Corpus] = []
        if options.demos:
            corpora.extend(configured(name, ROOT / "fixtures" / name) for name in FIXTURES)
            corpora.extend(demo_variants(Path(scratch)))
        for item in options.corpus:
            name, _, path = item.partition("=")
            corpora.append(Corpus(name, Path(path), (".",), "bench"))
        for corpus in corpora:
            row = rows.setdefault(corpus.name, [0, 0, 0, 0])
            measured = checked_corpus(binary, corpus, options.output_dir)
            row[:] = [a + b for a, b in zip(row, measured, strict=True)]
            print(corpus.name, row, flush=True)
            if row[3]:
                return 1
    return int(any(row[3] for row in rows.values()))


if __name__ == "__main__":
    raise SystemExit(main())
