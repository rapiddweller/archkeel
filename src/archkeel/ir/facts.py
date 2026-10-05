# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable source values shared with replaceable language collectors."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from .state_facts import StateFacts
from .type_shapes import TypeShape

Language: TypeAlias = Literal["python", "dart", "typescript"]

RECORD_FIELDS = (
    "id",
    "evidence_class",
    "area",
    "kind",
    "title",
    "subjects",
    "evidence_ids",
    "rule_ids",
    "fact_ids",
    "provenance",
    "data",
)
EVIDENCE_FIELDS = ("id", "file", "line", "end_line", "column", "excerpt")


class ForbiddenConstructKind(StrEnum):
    GETATTR = "getattr"
    HASATTR = "hasattr"
    CAST = "cast"
    EVAL = "eval"
    EXEC = "exec"
    DYNAMIC_IMPORT = "dynamic_import"
    TYPE_IGNORE = "type_ignore"
    ANY_ANNOTATION = "any_annotation"
    PLACEHOLDER_BODY = "placeholder_body"
    ASSERT = "assert"
    BROAD_EXCEPT = "broad_except"
    SETATTR = "setattr"
    DELATTR = "delattr"
    VARS = "vars"
    DUNDER_DICT = "dunder_dict"
    STRING_LITERAL_COMPARE = "string_literal_compare"


class EvidenceClass(StrEnum):
    FACT = "FACT"
    DECLARED_RULE = "DECLARED_RULE"
    VIOLATION = "VIOLATION"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


def dart_module_name(path: str) -> str | None:
    """Retain the directive profile's legacy module spelling, including collisions."""
    segments = path.split("/")
    names = [
        re.sub(
            r"[.-]", "_", segment.removesuffix(".dart") if index == len(segments) - 1 else segment
        )
        for index, segment in enumerate(segments)
    ]
    return (
        ".".join(names)
        if all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names)
        else None
    )


def stable_id(prefix: str, *parts: object) -> str:
    """Return a compact content-derived ID independent of traversal order."""
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


@dataclass(frozen=True, slots=True)
class RecordData:
    """Immutable, profile-owned JSON payload; the common schema leaves its keys open."""

    entries: tuple[tuple[str, JsonValue], ...] = ()

    def __post_init__(self) -> None:
        if len({key for key, _ in self.entries}) != len(self.entries):
            raise ValueError("duplicate record data key")

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return next((value for name, value in self.entries if name == key), default)


JsonValue: TypeAlias = str | int | float | bool | None | tuple["JsonValue", ...] | RecordData


@dataclass(frozen=True, slots=True)
class MemberInventory:
    """Direct static declarations; inherited and generated members stay outside proof."""

    kind: Literal["attribute", "method"]
    status: Literal["complete", "partial"]
    definition_ids: tuple[str, ...]
    reason: str | None = None
    schema_version: Literal["1.0.0"] = "1.0.0"

    def __post_init__(self) -> None:
        if (
            self.schema_version != "1.0.0"
            or self.kind not in ("attribute", "method")
            or self.status not in ("complete", "partial")
        ):
            raise ValueError("invalid member inventory vocabulary")
        if (
            not isinstance(self.definition_ids, tuple)
            or any(not isinstance(item, str) or not item for item in self.definition_ids)
            or len(set(self.definition_ids)) != len(self.definition_ids)
        ):
            raise ValueError("invalid member inventory identities")
        if (self.status == "complete" and self.reason is not None) or (
            self.status == "partial"
            and (not isinstance(self.reason, str) or not self.reason.strip())
        ):
            raise ValueError("member inventory reason contradicts status")


def member_inventories(value: JsonValue) -> tuple[MemberInventory, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple):
        raise ValueError("member inventory needs an array")
    result: list[MemberInventory] = []
    for item in value:
        required = {"kind", "status", "definition_ids", "schema_version"}
        if (
            not isinstance(item, RecordData)
            or not required <= {key for key, _ in item.entries}
            or {key for key, _ in item.entries} - (required | {"reason"})
        ):
            raise ValueError("member inventory fields mismatch")
        if item.get("schema_version") != "1.0.0":
            raise ValueError("unsupported member inventory version")
        kind, status = item.get("kind"), item.get("status")
        ids, reason = item.get("definition_ids"), item.get("reason")
        if (
            not isinstance(ids, tuple)
            or any(not isinstance(identifier, str) for identifier in ids)
            or (reason is not None and not isinstance(reason, str))
        ):
            raise ValueError("invalid member inventory values")
        if kind not in ("attribute", "method") or status not in ("complete", "partial"):
            raise ValueError("invalid member inventory vocabulary")
        result.append(
            MemberInventory(
                "attribute" if kind == "attribute" else "method",
                "complete" if status == "complete" else "partial",
                tuple(identifier for identifier in ids if isinstance(identifier, str)),
                reason,
            )
        )
    if len(result) != 2 or {item.kind for item in result} != {"attribute", "method"}:
        raise ValueError("member inventory needs one receipt per member kind")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class Record:
    id: str
    evidence_class: EvidenceClass
    area: str
    kind: str
    title: str
    subjects: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    provenance: tuple[str, ...]
    data: RecordData


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    file: str
    line: int
    end_line: int
    column: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class AnalyzerInfo:
    name: str
    version: str
    code_digest: str


@dataclass(frozen=True, slots=True)
class SourceInfo:
    git_head: str
    dirty: bool | Literal["unknown"]
    source_digest: str
    scope: tuple[str, ...]


SourceSectionName: TypeAlias = Literal[
    "symbols",
    "imports",
    "calls",
    "references",
    "bindings",
    "typing_signals",
    "constructs",
    "unknowns",
]
SourceProfile: TypeAlias = Literal[
    "archkeel-python-analyzer", "archkeel-dart-directives", "archkeel-typescript-imports"
]


class ConstructSupport(StrEnum):
    DECIDED = "decided"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ConstructCapability:
    name: ForbiddenConstructKind
    status: ConstructSupport


@dataclass(frozen=True, slots=True)
class Capabilities:
    sections: tuple[SourceSectionName, ...]
    resolution_features: tuple[str, ...] = ()
    constructs: tuple[ConstructCapability, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    name: str
    version: str
    required: str | None = None


@dataclass(frozen=True, slots=True)
class ResolutionInput:
    path: str
    digest: str
    role: Literal["selected", "resolution"]


@dataclass(frozen=True, slots=True)
class FileFact:
    id: str
    rel_path: str
    module: str
    package: str
    all_exports: frozenset[str]
    all_literal: bool
    compatibility_logic_free: bool
    stable_bindings: frozenset[str]
    blank: bool
    evidence_id: str


@dataclass(frozen=True, slots=True)
class FactSection:
    name: SourceSectionName
    records: tuple[Record, ...]


@dataclass(frozen=True, slots=True)
class CollectionCoverage:
    selected_files: tuple[str, ...]
    files_read: int
    files_parsed: int
    full_scope: bool
    gaps: tuple[Record, ...]


@dataclass(frozen=True, slots=True)
class LocalTarget:
    import_id: str
    module: str
    file: str
    runtime_file: str | None = None
    declaration_file: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalPackageTarget:
    import_id: str
    package: str


@dataclass(frozen=True, slots=True)
class BuiltinTarget:
    import_id: str
    name: str


@dataclass(frozen=True, slots=True)
class UnresolvedTarget:
    import_id: str
    specifier: str
    reason: str


ImportTarget: TypeAlias = LocalTarget | ExternalPackageTarget | BuiltinTarget | UnresolvedTarget


@dataclass(frozen=True, slots=True)
class SourceFacts:
    profile: SourceProfile
    adapter: AnalyzerInfo
    runtime: RuntimeInfo
    source: SourceInfo
    capabilities: Capabilities
    inputs: tuple[ResolutionInput, ...]
    files: tuple[FileFact, ...]
    imports: tuple[ImportTarget, ...]
    sections: tuple[FactSection, ...]
    coverage: CollectionCoverage
    evidence: tuple[Evidence, ...]
    uncertain_reexports: tuple[tuple[str, tuple[str, ...]], ...] = ()
    type_shapes: tuple[tuple[str, TypeShape], ...] = ()
    state: StateFacts = StateFacts((), ())
    candidate_evidence: tuple[Evidence, ...] = ()


def in_scope(name: str, scope: str) -> bool:
    """Match a qualified name against a dotted prefix without partial segments."""
    return name == scope or name.startswith(f"{scope}.")
