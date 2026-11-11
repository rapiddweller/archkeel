# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the record sections of a persisted architecture.json that the payload needs (AD-361).

The reader decodes the columnar encoding itself. It never builds an Observation, and it never
reads `transitive_paths`, calls, references or any other section that is not listed here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SECTIONS = (
    "modules",
    "packages",
    "symbols",
    "imports",
    "dependency_edges",
    "declarations",
    "scope_observations",
    "cycles",
    "metrics",
)
COMPONENT_KINDS = frozenset({"component_responsibility", "inside_component_responsibility"})


@dataclass(frozen=True)
class Requires:
    component: str
    rationale: str | None


@dataclass(frozen=True)
class Component:
    id: str
    title: str
    parent_id: str | None
    exact_modules: tuple[str, ...]
    packages: tuple[str, ...]
    responsibilities: tuple[str, ...]
    forbidden: tuple[str, ...]
    decided_by: str | None
    provenance: tuple[str, ...]
    role: str | None
    public_api: tuple[str, ...] | None
    requires: tuple[Requires, ...]


@dataclass(frozen=True)
class RuleDeclaration:
    id: str
    kind: str
    title: str
    parent_id: str | None


@dataclass(frozen=True)
class Module:
    name: str
    file: str
    package: str | None


@dataclass(frozen=True)
class Symbol:
    id: str
    qualified_name: str
    module: str
    name: str
    kind: str
    class_kind: str | None
    parent: str | None
    visibility: str | None
    static: bool
    variants: tuple[str, ...]
    line: int
    decl: str


@dataclass(frozen=True)
class Import:
    id: str
    symbol: str | None
    origin: str | None
    reexport: bool
    line: int


@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class Records:
    """The typed rows of one architecture.json that the producer reads."""

    language: str
    git_head: str | None
    dirty: bool
    scope: tuple[str, ...]
    contract: tuple[str, str, str] | None
    coverage: tuple[int, int, int]
    modules: tuple[Module, ...]
    packages: tuple[str, ...]
    symbols: tuple[Symbol, ...]
    imports: Mapping[str, Import]
    module_edges: tuple[DependencyEdge, ...]
    components: tuple[Component, ...]
    rule_declarations: tuple[RuleDeclaration, ...]
    scopes: Mapping[str, tuple[str, ...]]
    cycles: tuple[tuple[str, tuple[str, ...]], ...]
    metrics: Mapping[str, int]


def _opt(mapping: Mapping[str, object], key: str) -> str | None:
    """Return the text field `key`, or None when the field is absent or not text."""
    found = mapping.get(key)
    return found if isinstance(found, str) else None


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class _Decoder:
    def __init__(self, document: Mapping[str, object]) -> None:
        encoding = document.get("encoding")
        if not isinstance(encoding, dict):
            raise ValueError("architecture.json has no columnar encoding")
        strings = document.get("string_table")
        self.strings: Sequence[object] = strings if isinstance(strings, list) else []
        record_fields = encoding.get("record_fields")
        self.record_fields = _texts(record_fields)
        data_fields = encoding.get("section_data_fields")
        self.data_fields: Mapping[str, object] = (
            data_fields if isinstance(data_fields, dict) else {}
        )
        evidence_fields = _texts(encoding.get("evidence_fields"))
        self.document = document
        self.evidence: dict[str, tuple[int, str]] = {}
        line_at = evidence_fields.index("line")
        excerpt_at = evidence_fields.index("excerpt")
        rows = document.get("evidence")
        for row in rows if isinstance(rows, list) else ():
            if isinstance(row, list):
                excerpt = self.value(row[excerpt_at])
                self.evidence[str(row[0])] = (
                    _int(row[line_at]),
                    excerpt if isinstance(excerpt, str) else "",
                )

    def value(self, raw: object) -> object:
        if isinstance(raw, str):
            if raw.startswith("$$"):
                return raw[1:]
            if raw == "$m":
                return None
            if raw.startswith("$") and raw[1:].isdigit():
                return self.strings[int(raw[1:])]
            return raw
        if isinstance(raw, list):
            return [self.value(item) for item in raw]
        if isinstance(raw, dict):
            return {key: self.value(item) for key, item in raw.items()}
        return raw

    def section(self, name: str) -> list[dict[str, object]]:
        fields = _texts(self.data_fields.get(name))
        rows = self.document.get(name)
        out: list[dict[str, object]] = []
        for raw in rows if isinstance(rows, list) else ():
            record = dict(
                zip(self.record_fields, raw if isinstance(raw, list) else (), strict=False)
            )
            decoded = self.value(record.get("data"))
            if isinstance(decoded, list):
                decoded = dict(zip(fields, decoded, strict=False))
            record = {key: self.value(item) for key, item in record.items() if key != "data"}
            record["data"] = decoded if isinstance(decoded, dict) else {}
            out.append(record)
        return out

    def first_evidence(self, record: Mapping[str, object]) -> tuple[int, str]:
        ids = _texts(record.get("evidence_ids"))
        return self.evidence.get(ids[0], (0, "")) if ids else (0, "")


def _data(record: Mapping[str, object]) -> Mapping[str, object]:
    data = record.get("data")
    return data if isinstance(data, dict) else {}


def _with_data(
    rows: Sequence[Mapping[str, object]],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    return [(row, _data(row)) for row in rows]


def _component(record: Mapping[str, object]) -> Component:
    data = _data(record)
    requires = data.get("requires")
    entries = tuple(
        Requires(str(item.get("component")), _opt(item, "rationale"))
        for item in (requires if isinstance(requires, list) else ())
        if isinstance(item, dict) and isinstance(item.get("component"), str)
    )
    public_api = data.get("public_api_ids")
    return Component(
        id=str(record.get("id")),
        title=str(record.get("title")),
        parent_id=_opt(data, "parent_id"),
        exact_modules=_texts(data.get("exact_modules")),
        packages=_texts(record.get("subjects")),
        responsibilities=_texts(data.get("responsibilities")),
        forbidden=_texts(data.get("forbidden_responsibilities")),
        decided_by=_opt(data, "decided_by"),
        provenance=_texts(record.get("provenance")),
        role=_opt(data, "role"),
        public_api=_texts(public_api) if isinstance(public_api, list) else None,
        requires=entries,
    )


def _symbol(record: Mapping[str, object], decoder: _Decoder) -> Symbol:
    data = _data(record)
    visibility = data.get("visibility_detail")
    line, excerpt = decoder.first_evidence(record)
    return Symbol(
        id=str(record.get("id")),
        qualified_name=str(data.get("qualified_name")),
        module=str(data.get("module")),
        name=str(data.get("name")),
        kind=str(record.get("kind")),
        class_kind=_opt(data, "class_kind"),
        parent=_opt(data, "parent"),
        visibility=_opt(visibility, "kind") if isinstance(visibility, dict) else None,
        static=data.get("method_kind") in ("static", "staticmethod"),
        variants=_texts(data.get("enum_members")),
        line=line,
        decl=excerpt,
    )


def _import(record: Mapping[str, object], decoder: _Decoder) -> Import:
    data = _data(record)
    return Import(
        id=str(record.get("id")),
        symbol=_opt(data, "symbol") or None,
        origin=_opt(data, "origin_definition"),
        reexport=record.get("kind") == "reexport" or data.get("reexport") is True,
        line=decoder.first_evidence(record)[0],
    )


def read_records(document: Mapping[str, object]) -> Records:
    """Decode the needed sections of one parsed architecture.json document."""
    decoder = _Decoder(document)
    sections = {name: decoder.section(name) for name in SECTIONS}
    source = document.get("source")
    source = source if isinstance(source, dict) else {}
    contract = document.get("contract")
    coverage = document.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    runtime = document.get("runtime")
    declarations = sections["declarations"]
    return Records(
        language=str(runtime.get("name")) if isinstance(runtime, dict) else "",
        git_head=_opt(source, "git_head"),
        dirty=source.get("dirty") is True,
        scope=_texts(source.get("scope")),
        contract=(
            str(contract.get("path")),
            str(contract.get("digest")),
            str(contract.get("schema_version")),
        )
        if isinstance(contract, dict)
        else None,
        coverage=(
            _int(coverage.get("files_discovered")),
            _int(coverage.get("files_read")),
            _int(coverage.get("files_parsed")),
        ),
        modules=tuple(
            Module(str(d.get("qualified_name")), str(d.get("file")), _opt(d, "package"))
            for d in map(_data, sections["modules"])
        ),
        packages=tuple(str(d.get("qualified_name")) for d in map(_data, sections["packages"])),
        symbols=tuple(_symbol(r, decoder) for r in sections["symbols"]),
        imports={str(r.get("id")): _import(r, decoder) for r in sections["imports"]},
        module_edges=tuple(
            DependencyEdge(str(d.get("source")), str(d.get("target")), _texts(r.get("fact_ids")))
            for r, d in _with_data(sections["dependency_edges"])
            if d.get("level") == "module"
        ),
        components=tuple(_component(r) for r in declarations if r.get("kind") in COMPONENT_KINDS),
        rule_declarations=tuple(
            RuleDeclaration(
                str(r.get("id")), str(r.get("kind")), str(r.get("title")), _opt(d, "parent_id")
            )
            for r, d in _with_data(declarations)
            if r.get("evidence_class") == "DECLARED_RULE" and r.get("kind") not in COMPONENT_KINDS
        ),
        scopes={
            str(d.get("component_id")): _texts(d.get("modules"))
            for r, d in _with_data(sections["scope_observations"])
            if r.get("kind") == "declared_component_scope_observation"
        },
        cycles=tuple(
            (str(d.get("level")), _texts(r.get("subjects")))
            for r, d in _with_data(sections["cycles"])
        ),
        metrics={
            str(r.get("kind")): _int(d.get("value")) for r, d in _with_data(sections["metrics"])
        },
    )
