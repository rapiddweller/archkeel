# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable source values shared with replaceable language collectors."""

from __future__ import annotations

import builtins
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Literal, TypeAlias

from .state_facts import StateFacts
from .type_shapes import TypeShape


class Language(StrEnum):
    PYTHON = "python"
    DART = "dart"
    TYPESCRIPT = "typescript"


class DefinitionContextKind(StrEnum):
    IF = "if"
    FOR = "for"
    ASYNC_FOR = "async_for"
    WHILE = "while"
    TRY = "try"
    TRY_STAR = "try_star"
    WITH = "with"
    ASYNC_WITH = "async_with"
    MATCH = "match"


class DefinitionBranchKind(StrEnum):
    BODY = "body"
    ELSE = "else"
    HANDLER = "handler"
    FINALLY = "finally"
    CASE = "case"


class RuntimeRequirementState(StrEnum):
    DECLARED = "declared"
    METADATA_MISSING = "metadata_missing"
    METADATA_INVALID = "metadata_invalid"
    REQUIREMENT_MISSING = "requirement_missing"
    REQUIREMENT_INVALID = "requirement_invalid"


def parse_runtime_requirement_state(value: str) -> RuntimeRequirementState:
    """Validate the shared runtime vocabulary once, at a wire or metadata boundary."""
    try:
        return RuntimeRequirementState(value)
    except ValueError as error:
        raise ValueError("runtime.requirement_state is invalid") from error


class SourceDirty(StrEnum):
    UNKNOWN = "unknown"


class MemberKind(StrEnum):
    ATTRIBUTE = "attribute"
    METHOD = "method"


class InventoryStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class InventoryVersion(StrEnum):
    V1 = "1.0.0"


class ResolutionRole(StrEnum):
    SELECTED = "selected"
    RESOLUTION = "resolution"


class SourceResolution(StrEnum):
    """Resolution claims published by source collectors, separate from graph resolution."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"


def parse_source_resolution(value: JsonValue | RawJson) -> SourceResolution | None:
    """Recognize source resolution at an owned port; future record data remains opaque."""
    if isinstance(value, SourceResolution):
        return value
    if not isinstance(value, str):
        return None
    try:
        return SourceResolution(value)
    except ValueError:
        return None


def source_dirty(value: bool | str) -> bool | Literal["unknown"]:
    """Validate the dirty sentinel without changing its legacy wire spelling."""
    if isinstance(value, bool):
        return value
    try:
        SourceDirty(value)
    except ValueError as error:
        raise ValueError("source.dirty is invalid") from error
    return "unknown"


SOURCE_RESOLUTION_GAP_KIND = "source_resolution_gap"

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
RawJson: TypeAlias = str | int | float | bool | None | list["RawJson"] | dict[str, "RawJson"]


class PropertyOperation(Enum):
    CREATE = "create"
    GETTER = "getter"
    SETTER = "setter"


class PropertyOrigin(Enum):
    NEW = "new"
    LOCAL = "local"
    BASE = "base"


@dataclass(frozen=True, slots=True)
class PropertyBinding:
    """An ordered standard-property operation, not proof of descriptor ownership."""

    operation: PropertyOperation
    source: PropertyOrigin
    line: int
    source_line: int

    def __post_init__(self) -> None:
        try:
            builtins.object.__setattr__(self, "operation", PropertyOperation(self.operation))
            builtins.object.__setattr__(self, "source", PropertyOrigin(self.source))
        except ValueError as error:
            raise ValueError("invalid property binding operation or order") from error
        if (
            type(self.line) is not int
            or type(self.source_line) is not int
            or self.line < 1
            or self.source_line < 0
            or self.source_line >= self.line
            or (self.operation is PropertyOperation.CREATE) != (self.source is PropertyOrigin.NEW)
            or (self.source is PropertyOrigin.LOCAL) != (self.source_line > 0)
        ):
            raise ValueError("invalid property binding operation or order")


def property_binding(value: RecordData | Mapping[str, object]) -> PropertyBinding:
    """Decode the existing property wire record at the source-facts boundary."""
    raw = dict(value.entries) if isinstance(value, RecordData) else value
    if set(raw) != {"operation", "source", "line", "source_line"}:
        raise ValueError("invalid property binding fields")
    operation, source = raw["operation"], raw["source"]
    line, source_line = raw["line"], raw["source_line"]
    if (
        not isinstance(operation, str)
        or not isinstance(source, str)
        or not isinstance(line, int)
        or not isinstance(source_line, int)
    ):
        raise ValueError("invalid property binding operation or order")
    try:
        return PropertyBinding(
            PropertyOperation(operation), PropertyOrigin(source), line, source_line
        )
    except ValueError as error:
        raise ValueError("invalid property binding operation or order") from error


class ParameterKind(StrEnum):
    POSITIONAL_ONLY = "positional_only"
    POSITIONAL = "positional"
    KEYWORD_ONLY = "keyword_only"
    VARARGS = "varargs"
    KWARGS = "kwargs"
    UNKNOWN = "unknown"


class SymbolClassKind(StrEnum):
    """The five values `class_kind` resolves to (`analyzer.python.symbols`'s fixpoint)."""

    PROTOCOL = "protocol"
    ENUM = "enum"
    PYDANTIC_MODEL = "pydantic_model"
    DATACLASS = "dataclass"
    CLASS = "class"


class MethodKind(Enum):
    INSTANCE = "instance"
    STATIC = "static"
    CLASS = "class"
    CONSTRUCTOR = "constructor"
    FACTORY = "factory"


def parse_method_kind(value: JsonValue | RawJson | MethodKind) -> MethodKind | None:
    """Recognize shared method tags without assigning meaning to opaque wire data."""
    if isinstance(value, MethodKind):
        return value
    if not isinstance(value, str):
        return None
    try:
        return MethodKind(value)
    except ValueError:
        return None


def parse_symbol_class_kind(value: JsonValue | RawJson | SymbolClassKind) -> SymbolClassKind | None:
    """Recognize source classifier tags without assigning meaning to foreign wire data."""
    if not isinstance(value, str):
        return None
    try:
        return SymbolClassKind(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class MethodDescriptor:
    """Nominal method kind with independent source descriptor and binding proof."""

    method_kind: MethodKind
    signature_decorators_proven: bool
    source_final_method_binding: bool
    property_binding: PropertyBinding | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.method_kind, MethodKind)
            or type(self.signature_decorators_proven) is not bool
            or type(self.source_final_method_binding) is not bool
            or self.property_binding is not None
            and not isinstance(self.property_binding, PropertyBinding)
        ):
            raise ValueError("invalid method descriptor")


@dataclass(frozen=True, slots=True)
class MemberInventory:
    """Direct static declarations; inherited and generated members stay outside proof."""

    kind: MemberKind
    status: InventoryStatus
    definition_ids: tuple[str, ...]
    reason: str | None = None
    schema_version: InventoryVersion = InventoryVersion.V1

    def __post_init__(self) -> None:
        if (
            self.schema_version != InventoryVersion.V1
            or self.kind not in (MemberKind.ATTRIBUTE, MemberKind.METHOD)
            or self.status not in (InventoryStatus.COMPLETE, InventoryStatus.PARTIAL)
        ):
            raise ValueError("invalid member inventory vocabulary")
        if (
            not isinstance(self.definition_ids, tuple)
            or any(not isinstance(item, str) or not item for item in self.definition_ids)
            or len(set(self.definition_ids)) != len(self.definition_ids)
        ):
            raise ValueError("invalid member inventory identities")
        if (self.status == InventoryStatus.COMPLETE and self.reason is not None) or (
            self.status == InventoryStatus.PARTIAL
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
        raw_version = item.get("schema_version")
        if not isinstance(raw_version, str):
            raise ValueError("unsupported member inventory version")
        try:
            inventory_version = InventoryVersion(raw_version)
        except ValueError as error:
            raise ValueError("unsupported member inventory version") from error
        kind, status = item.get("kind"), item.get("status")
        ids, reason = item.get("definition_ids"), item.get("reason")
        if (
            not isinstance(ids, tuple)
            or any(not isinstance(identifier, str) for identifier in ids)
            or (reason is not None and not isinstance(reason, str))
        ):
            raise ValueError("invalid member inventory values")
        if not isinstance(kind, str) or not isinstance(status, str):
            raise ValueError("invalid member inventory vocabulary")
        try:
            member_kind = MemberKind(kind)
            inventory_status = InventoryStatus(status)
        except ValueError as error:
            raise ValueError("invalid member inventory vocabulary") from error
        result.append(
            MemberInventory(
                member_kind,
                inventory_status,
                tuple(identifier for identifier in ids if isinstance(identifier, str)),
                reason,
                inventory_version,
            )
        )
    if len(result) != 2 or {item.kind for item in result} != {
        MemberKind.ATTRIBUTE,
        MemberKind.METHOD,
    }:
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


class SourceSectionName(StrEnum):
    SYMBOLS = "symbols"
    IMPORTS = "imports"
    CALLS = "calls"
    REFERENCES = "references"
    BINDINGS = "bindings"
    TYPING_SIGNALS = "typing_signals"
    CONSTRUCTS = "constructs"
    UNKNOWNS = "unknowns"


class SourceProfile(StrEnum):
    PYTHON = "archkeel-python-analyzer"
    DART = "archkeel-dart-analyzer"
    TYPESCRIPT = "archkeel-typescript-imports"


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
    # Diagnostic context does not change runtime comparability for saved snapshots.
    requirement_state: RuntimeRequirementState = field(
        default=RuntimeRequirementState.DECLARED, compare=False
    )


@dataclass(frozen=True, slots=True)
class ResolutionInput:
    path: str
    digest: str
    role: ResolutionRole


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
