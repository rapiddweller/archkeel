# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare raw Dart collection assembly with real Python functions (AD-400)."""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from archkeel.analyzer.dart.collect import _Collection
from archkeel.analyzer.dart.resolve import Resolver
from archkeel.analyzer.dart.snapshot import read_snapshot
from archkeel.analyzer.dart.syntax import DefinitionKind, DirectiveKind, SiteKind, Syntax
from archkeel.ir.facts_codec import _target_payload

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dart_declarations_parity as declarations  # noqa: E402
from dart_discovery_parity import Corpus, FIXTURES, ROOT, build, configured, demo_variants, request  # noqa: E402


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=sorted)


def layer_input(c: _Collection) -> dict[str, Any]:
    prepared = declarations.layer_input(c)
    constructors = {file["rel"]: file["constructors"] for file in prepared["files"]}
    files = []
    directives, names, sites, constructions = [], {}, [], []
    for source in c.snapshot.sources:
        rel = source.rel_path
        syntax = c.syntax[rel]
        files.append({"file": {
            "rel": rel, "module": source.module, "source_len": len(source.content),
            "first_line": next(iter(source.content.decode("utf-8", "replace").splitlines()), None),
            "syntax": dataclasses.asdict(syntax), "constructors": constructors.get(rel, []),
        }, "content": source.content.decode("utf-8", "replace"), "owner": c.resolver.module_for(rel)})
        if rel not in c.parsed:
            continue
        for directive in syntax.directives:
            if directive.kind in {DirectiveKind.IMPORT, DirectiveKind.EXPORT}:
                directives.append({"rel": rel, "start": directive.span.start_byte,
                    "targets": [dataclasses.asdict(value) for value in c.resolver.resolve_directive(rel, directive)]})
        for definition in syntax.definitions:
            for name in (*definition.extends, *definition.with_types, *definition.implements):
                names[(rel, name)] = c.resolver.resolve_name(rel, name)
            if definition.kind == DefinitionKind.TYPEDEF and definition.alias is not None:
                names[(rel, definition.alias)] = c.resolver.resolve_name(rel, definition.alias)
        resolved = c.resolver.resolved_sites(rel)
        sites.append({"rel": rel, "sites": [dataclasses.asdict(value) for value in resolved]})
        for value in resolved:
            if value.site.kind in {SiteKind.CALL, SiteKind.CREATION}:
                constructions.append({"rel": rel, "start": value.site.span.start_byte,
                    "expression": value.site.expression,
                    "resolution": dataclasses.asdict(c.resolver.resolve_construction(rel, value.site))})
    unique_constructions = {(item["rel"], item["start"], item["expression"]): item for item in constructions}
    return {"files": files, "package_name": c.snapshot.package_name,
        "sdk_state": c.snapshot.sdk_constraint_state.value, "sdk": c.snapshot.sdk_constraint,
        "roots": c.snapshot.roots, "inputs": [dataclasses.asdict(item) for item in c.snapshot.inputs],
        "git_head": c.request.snapshot.git_head, "dirty": c.request.snapshot.dirty,
        "problems": [{"path": item.path, "kind": item.kind, "message": item.message, "span": None} for item in c.snapshot.problems],
        "resolver": {"directives": directives,
            "names": [{"rel": rel, "name": name, "targets": targets} for (rel, name), targets in sorted(names.items())],
            "sites": sites, "constructions": list(unique_constructions.values()),
            "problems": [{"path": item.path, "kind": "DirectiveError" if item.kind == "ImportError" else item.kind,
                "message": item.message, "span": None if item.span is None else dataclasses.asdict(item.span)} for item in c.resolver.problems]}}


def python(c: _Collection) -> dict[str, Any]:
    reference = _Collection(c.request, c.snapshot, c.syntax, c.resolver)
    facts = reference.facts()
    return {"full_scope": facts.coverage.full_scope,
        "selected_files": facts.coverage.selected_files, "files_read": facts.coverage.files_read,
        "files_parsed": facts.coverage.files_parsed, "inputs": [dataclasses.asdict(item) for item in facts.inputs],
        "source_digest": facts.source.source_digest, "scope": facts.source.scope,
        "git_head": facts.source.git_head, "dirty": facts.source.dirty,
        "capabilities": dataclasses.asdict(facts.capabilities),
        "files": [dataclasses.asdict(item) for item in facts.files],
        "symbols": sorted(reference.symbols, key=lambda item: item["id"]),
        "imports": sorted(reference.imports, key=lambda item: item["id"]),
        "calls": sorted(reference.calls, key=lambda item: item["id"]),
        "references": sorted(reference.references, key=lambda item: item["id"]),
        "bindings": reference.bindings, "targets": [_target_payload(item) for item in reference.targets],
        "gaps": [item for _, item in sorted(reference.gaps.items())],
        "evidence": [item for _, item in sorted(reference.evidence.items())]}


def native(binary: Path, value: dict[str, Any]) -> dict[str, Any]:
    run = subprocess.run([str(binary), "--dump-collection"], input=canonical(value) + "\n",
        capture_output=True, text=True, check=True, timeout=120)
    return json.loads(run.stdout)


def prepared(corpus: Corpus, binary: Path | None = None) -> _Collection:
    snapshot = read_snapshot(request(corpus))
    if binary is None:
        syntax = {source.rel_path: declarations.parse(source.content) for source in snapshot.sources}
    else:
        run = subprocess.run([str(binary), "--dump-syntax"],
            input="".join(str(corpus.root / source.rel_path) + "\n" for source in snapshot.sources),
            capture_output=True, text=True, check=True, timeout=600)
        parsed = [json.loads(line)["syntax"] for line in run.stdout.splitlines()]
        syntax = {source.rel_path: declarations.decode(Syntax, value)
            for source, value in zip(snapshot.sources, parsed, strict=True)}
    return declarations.collection(corpus, snapshot, syntax)


def compare(binary: Path, c: _Collection) -> tuple[dict[str, Any], dict[str, Any]]:
    value = layer_input(c)
    actual = native(binary, value)
    actual.pop("work", None)
    return actual, python(c)


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--demos", action="store_true")
    args.add_argument("--corpus", action="append", default=[])
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
            c = prepared(corpus, binary)
            row = rows.setdefault(corpus.name, [0, 0, 0, 0])
            references = [c]
            if corpus.name not in FIXTURES and corpus.name != "demo variants":
                references = []
                for source in c.snapshot.sources:
                    snapshot = dataclasses.replace(c.snapshot, sources=(source,), inputs=tuple(
                        item for item in c.snapshot.inputs if not item.path.endswith(".dart") or item.path == source.rel_path))
                    reference = _Collection(c.request, snapshot, {source.rel_path: c.syntax[source.rel_path]}, c.resolver)
                    reference._prepare_sources()
                    references.append(reference)
            for reference in references:
                actual, expected = compare(binary, reference)
                count = len(reference.snapshot.sources)
                row[0] += count
                if canonical(actual) == canonical(expected): row[1] += count
                elif any(gap["data"]["message"].startswith(("CollectionWorkLimit:", "LanguageVersionOrderGap:")) for gap in actual["gaps"]): row[2] += count
                else:
                    row[3] += count
                    print("DIFFERENT", corpus.name, reference.snapshot.sources[0].rel_path, flush=True)
                    Path(tempfile.gettempdir(), "dart4c-actual.json").write_text(canonical(actual))
                    Path(tempfile.gettempdir(), "dart4c-expected.json").write_text(canonical(expected))
                    return 1
                if row[0] % 100 == 0: print(corpus.name, row, flush=True)
            print(corpus.name, row, flush=True)
    return int(any(row[3] for row in rows.values()))


if __name__ == "__main__":
    raise SystemExit(main())
