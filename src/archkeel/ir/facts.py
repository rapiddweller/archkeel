# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable source values shared with replaceable language collectors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from .state_facts import StateFacts
from .type_shapes import TypeShape

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


class EvidenceClass(StrEnum):
    FACT = "FACT"
    DECLARED_RULE = "DECLARED_RULE"
    VIOLATION = "VIOLATION"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


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


@dataclass(frozen=True, slots=True)
class Capabilities:
    sections: tuple[SourceSectionName, ...]
    resolution_features: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    name: str
    version: str


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
