# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the declaration boundary using typed syntax and real Python resolver inputs (AD-392).

Corpus runs use the native syntax as the common layer input, not as an oracle for parsing.
The separate syntax parity tools check parsing. Hostile tests use the real Python parse.
No declaration logic is copied here. The tool calls `_Collection._declarations`.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import subprocess
import sys
import tempfile
import types
import typing
from functools import cache
from pathlib import Path
from typing import Any

from archkeel.analyzer.dart.collect import _Collection
from archkeel.analyzer.dart.parse import parse
from archkeel.analyzer.dart.resolve import Resolver
from archkeel.analyzer.dart.snapshot import Snapshot, SnapshotError, read_snapshot
from archkeel.analyzer.dart.syntax import DefinitionKind, MemberKind, Syntax

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dart_discovery_parity import (  # noqa: E402
    FIXTURES,
    ROOT,
    Corpus,
    build,
    configured,
    demo_variants,
    request,
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@cache
def hints(kind: type) -> dict[str, Any]:
    return typing.get_type_hints(kind)


def decode(kind: Any, value: Any) -> Any:
    """Read the typed syntax dump. This does not decide a declaration or a resolution."""
    if value is None:
        return None
    origin = typing.get_origin(kind)
    args = typing.get_args(kind)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], item) for item in value)
        return tuple(decode(item_kind, item) for item_kind, item in zip(args, value, strict=True))
    if origin in (types.UnionType, typing.Union):
        return decode(next(item for item in args if item is not type(None)), value)
    if isinstance(kind, type) and dataclasses.is_dataclass(kind):
        return kind(
            **{name: decode(field_kind, value[name]) for name, field_kind in hints(kind).items()}
        )
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return kind(value)
    return value


def native(binary: Path, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run = subprocess.run(
        [str(binary), "--dump-declarations"],
        input="".join(canonical(item) + "\n" for item in inputs),
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    if len(rows) != len(inputs):
        raise AssertionError("the declaration dump dropped or added a result")
    return rows


def collection(corpus: Corpus, snapshot: Snapshot, syntax: dict[str, Syntax]) -> _Collection:
    result = _Collection(request(corpus), snapshot, syntax, Resolver(snapshot, syntax))
    result._prepare_sources()
    result.evidence.clear()
    result.gaps.clear()
    return result


def layer_input(collection: _Collection) -> dict[str, Any]:
    files = []
    for rel, syntax in collection.syntax.items():
        if rel not in collection.parsed:
            continue
        constructors = []
        for definition in syntax.definitions:
            if definition.kind not in {
                DefinitionKind.CLASS,
                DefinitionKind.INTERFACE,
                DefinitionKind.MIXIN,
                DefinitionKind.ENUM,
            }:
                continue
            parent = f"{collection.modules[rel]}.{definition.name}"
            owner = collection._owner_definition(rel, collection.modules[rel], parent)
            for member in definition.members:
                if member.kind == MemberKind.CONSTRUCTOR and owner is not None:
                    resolution = collection.resolver.resolve_parameters(rel, owner, member)
                    constructors.append(
                        {"start": member.span.start_byte, **dataclasses.asdict(resolution)}
                    )
        files.append(
            {
                "rel": rel,
                "module": collection.modules[rel],
                "source_len": len(collection.sources[rel].content),
                "syntax": dataclasses.asdict(syntax),
                "first_line": next(
                    iter(collection.sources[rel].content.decode("utf-8", "replace").splitlines()),
                    None,
                ),
                "constructors": constructors,
            }
        )
    return {"files": files}


def python(collection: _Collection) -> dict[str, Any]:
    collection._declarations()
    return {
        "symbols": collection.symbols,
        "evidence": [value for _, value in sorted(collection.evidence.items())],
        "gaps": [value for _, value in sorted(collection.gaps.items())],
        "definition_ids": sorted(collection.definition_ids.items()),
        "definition_names": sorted(collection.definition_names.items()),
        "scope_candidates": [
            (*scope[:4], dataclasses.asdict(scope[4]), *scope[5:])
            for scope in collection.scope_candidates
        ],
        "symbol_by_name": sorted(
            (name, record["id"]) for name, record in collection.symbol_by_name.items()
        ),
        "incomplete_inventory_ids": sorted(collection.incomplete_inventory_ids),
    }


def payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "work"}


def from_source(binary: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    corpus = Corpus("hostile", root, ("lib",), "shop")
    snapshot = read_snapshot(request(corpus))
    syntax = {source.rel_path: parse(source.content) for source in snapshot.sources}
    reference = collection(corpus, snapshot, syntax)
    actual = native(binary, [layer_input(reference)])[0]
    return actual, python(reference)


@dataclasses.dataclass
class Result:
    name: str
    files: int = 0
    equal: int = 0
    stricter: int = 0
    different: int = 0
    max_ratio: float = 0
    max_work: int = 0


def compare(binary: Path, corpus: Corpus, row: Result) -> None:
    try:
        snapshot = read_snapshot(request(corpus))
    except SnapshotError:
        raise AssertionError("a parity corpus must have readable root metadata") from None
    paths = [corpus.root / source.rel_path for source in snapshot.sources]
    run = subprocess.run(
        [str(binary), "--dump-syntax"],
        input="".join(str(path) + "\n" for path in paths),
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    parsed = [json.loads(line)["syntax"] for line in run.stdout.splitlines()]
    if len(parsed) != len(paths):
        raise AssertionError("the syntax dump dropped or added a file")
    syntax = {
        source.rel_path: decode(Syntax, value)
        for source, value in zip(snapshot.sources, parsed, strict=True)
    }
    prepared = collection(corpus, snapshot, syntax)
    # Keep the full resolver while comparing each file's declaration assembly separately.
    for start in range(0, len(snapshot.sources), 64):
        references = []
        for source in snapshot.sources[start : start + 64]:
            reference = _Collection(
                request(corpus),
                snapshot,
                {source.rel_path: syntax[source.rel_path]},
                prepared.resolver,
            )
            reference.parsed = prepared.parsed & {source.rel_path}
            reference.modules = prepared.modules
            references.append(reference)
        inputs = [layer_input(reference) for reference in references]
        rows = native(binary, inputs)
        for reference, actual, item in zip(references, rows, inputs, strict=True):
            row.max_ratio = max(row.max_ratio, actual["work"] / len(canonical(item).encode()))
            row.max_work = max(row.max_work, actual["work"])
            row.files += 1
            if row.files % 500 == 0:
                print(f"{row.name}: checked {row.files} layer inputs", file=sys.stderr, flush=True)
            if any("DeclarationWorkLimit:" in gap["data"]["message"] for gap in actual["gaps"]):
                assert not actual["symbols"] and len(actual["gaps"]) == 1
                print(f"{row.name}: work limit at input {row.files}", file=sys.stderr)
                row.stricter += 1
            elif canonical(payload(actual)) == canonical(python(reference)):
                row.equal += 1
            else:
                row.different += 1
                print(f"{row.name}: declaration difference at input {row.files}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demos", action="store_true")
    parser.add_argument("--corpus", action="append", default=[])
    args = parser.parse_args()
    binary = build()
    rows: dict[str, Result] = {}
    with tempfile.TemporaryDirectory() as scratch:
        corpora: list[Corpus] = []
        if args.demos:
            corpora.extend(configured(name, ROOT / "fixtures" / name) for name in FIXTURES)
            corpora.extend(demo_variants(Path(scratch)))
        for item in args.corpus:
            name, separator, path = item.partition("=")
            if not separator:
                parser.error("use NAME=PATH")
            corpora.append(Corpus(name, Path(path), (".",), "bench"))
        for corpus in corpora:
            row = rows.setdefault(corpus.name, Result(corpus.name))
            compare(binary, corpus, row)
            print(
                f"{row.name}: {row.equal} equal, {row.stricter} named limits, "
                f"{row.different} different",
                file=sys.stderr,
                flush=True,
            )
    print("set | files | equal | stricter (DeclarationWorkLimit) | different")
    for row in rows.values():
        print(
            f"{row.name} | {row.files} | {row.equal} | {row.stricter} | {row.different} "
            f"| max work {row.max_work}, work/byte {row.max_ratio:.2f}"
        )
    return int(any(row.different for row in rows.values()))


if __name__ == "__main__":
    raise SystemExit(main())
