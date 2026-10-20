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

MAX_STATIC_INTEGER = (1 << 4096) - 1
MAX_NUMERIC_EVIDENCE_CHARS = 16_384


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
SOURCE_SCRIPT_GLOBAL_KIND = "script_global"

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
        for name, value in self.entries:
            if name == key:
                return value
        return default


JsonValue: TypeAlias = str | int | float | bool | None | tuple["JsonValue", ...] | RecordData
RawJson: TypeAlias = str | int | float | bool | None | list["RawJson"] | dict[str, "RawJson"]


class CallBindingOrigin(StrEnum):
    DIRECT = "direct"
    DECLARED_RECEIVER = "declared_receiver"
    STORED_RECEIVER = "stored_receiver"
    CONSTRUCTED_RECEIVER = "constructed_receiver"
    CONSTRUCTOR = "constructor"
    NATIVE = "native"
    NATIVE_RECEIVER = "native_receiver"


class _CallBindingProofKind(StrEnum):
    STORED_FIELD = "stored_field"
    CONSTRUCTION = "construction"
    CONSTRUCTOR = "constructor"
    PROVIDER_MEMBER = "provider_member"
    NATIVE_DESCRIPTOR = "native_descriptor"


_DATETIME_DESCRIPTOR_IDENTITY = {
    "target": "datetime.datetime.now",
    "runtime_name": "python",
    "runtime_implementation": "cpython",
    "descriptor_owner_module": "datetime",
    "descriptor_owner_qualname": "datetime",
    "descriptor_member": "now",
    "descriptor_kind": "classmethod_descriptor",
}
_CALL_BINDING_PROOF_FIELDS = {
    _CallBindingProofKind.STORED_FIELD: {
        "kind",
        "owner",
        "field",
        "parameter",
        "target",
        "witness_evidence_ids",
    },
    _CallBindingProofKind.CONSTRUCTION: {
        "kind",
        "target",
        "constructor_evidence_id",
        "assignment_evidence_id",
        "assignment_name",
    },
    _CallBindingProofKind.CONSTRUCTOR: {
        "kind",
        "target",
        "constructor_evidence_id",
        "provider_evidence_id",
        "runtime_name",
        "runtime_version",
    },
    _CallBindingProofKind.PROVIDER_MEMBER: {
        "kind",
        "target",
        "provider_evidence_id",
        "runtime_name",
        "runtime_version",
    },
    _CallBindingProofKind.NATIVE_DESCRIPTOR: {
        "kind",
        "target",
        "runtime_name",
        "runtime_version",
        "runtime_implementation",
        "descriptor_owner_module",
        "descriptor_owner_qualname",
        "descriptor_member",
        "descriptor_kind",
        "stdlib_source_digest",
        "witness_evidence_ids",
    },
}


CALL_BINDINGS_FEATURE = "canonical_call_bindings"
EXTENDED_CALL_BINDINGS_FEATURE = "extended_call_bindings"
NATIVE_CALL_TARGETS = frozenset(
    {
        "random.Random",
        "random.random",
        "random.Random.random",
        "random.Random.randrange",
        "random.Random.randint",
        "random.Random.choice",
        "random.Random.choices",
        "random.Random.sample",
        "random.Random.shuffle",
        "random.Random.uniform",
        "random.Random.getrandbits",
        "random.Random.seed",
        "random.Random.getstate",
        "random.Random.setstate",
        "datetime.datetime.now",
        "secrets.token_hex",
    }
)


@dataclass(frozen=True, slots=True)
class CallBinding:
    origin: CallBindingOrigin
    target: str
    evidence_ids: tuple[str, ...]
    proof: RecordData | None = None


class CallArgumentKind(StrEnum):
    POSITIONAL = "positional"
    KEYWORD = "keyword"
    STARRED_POSITIONAL = "starred_positional"
    STARRED_KEYWORD = "starred_keyword"


class CallArgumentValueKind(StrEnum):
    STRING_LITERAL = "string_literal"
    OTHER = "other"


CALL_ARGUMENTS_FEATURE = "call_arguments"


@dataclass(frozen=True, slots=True)
class CallArgument:
    kind: CallArgumentKind
    keyword: str | None
    value_kind: CallArgumentValueKind
    value: str | None
    evidence_ids: tuple[str, ...]


def call_arguments(value: JsonValue) -> tuple[CallArgument, ...] | None:
    if value is None:
        return None
    if not isinstance(value, tuple):
        raise ValueError("invalid call arguments")
    result: list[CallArgument] = []
    for item in value:
        if not isinstance(item, RecordData) or {key for key, _ in item.entries} != {
            "kind",
            "keyword",
            "value_kind",
            "value",
            "evidence_ids",
        }:
            raise ValueError("invalid call argument fields")
        kind, keyword = item.get("kind"), item.get("keyword")
        value_kind, actual_value, evidence = (
            item.get("value_kind"),
            item.get("value"),
            item.get("evidence_ids"),
        )
        if (
            not isinstance(kind, str)
            or not isinstance(value_kind, str)
            or value_kind == CallArgumentValueKind.STRING_LITERAL
            and not isinstance(actual_value, str)
            or value_kind == CallArgumentValueKind.OTHER
            and actual_value is not None
            or not isinstance(evidence, tuple)
            or not evidence
            or any(not isinstance(identifier, str) or not identifier for identifier in evidence)
            or (kind == CallArgumentKind.KEYWORD and (not isinstance(keyword, str) or not keyword))
            or (kind != CallArgumentKind.KEYWORD and keyword is not None)
        ):
            raise ValueError("invalid call argument values")
        result.append(
            CallArgument(
                CallArgumentKind(kind),
                keyword if isinstance(keyword, str) else None,
                CallArgumentValueKind(value_kind),
                actual_value if isinstance(actual_value, str) else None,
                tuple(identifier for identifier in evidence if isinstance(identifier, str)),
            )
        )
    return tuple(result)


def call_binding(value: JsonValue) -> CallBinding | None:
    if value is None:
        return None
    if not isinstance(value, RecordData):
        raise ValueError("invalid call binding fields")
    fields = {key for key, _ in value.entries}
    if fields not in (
        {"origin", "target", "evidence_ids"},
        {"origin", "target", "evidence_ids", "proof"},
    ):
        raise ValueError("invalid call binding fields")
    origin, target, evidence = value.get("origin"), value.get("target"), value.get("evidence_ids")
    if (
        not isinstance(origin, str)
        or not isinstance(target, str)
        or not target
        or not isinstance(evidence, tuple)
        or not evidence
        or any(not isinstance(item, str) or not item for item in evidence)
    ):
        raise ValueError("invalid call binding values")
    proof = value.get("proof")
    if proof is not None and not isinstance(proof, RecordData):
        raise ValueError("invalid call binding proof")
    parsed_origin = CallBindingOrigin(origin)
    if (
        parsed_origin
        in {
            CallBindingOrigin.STORED_RECEIVER,
            CallBindingOrigin.CONSTRUCTED_RECEIVER,
            CallBindingOrigin.CONSTRUCTOR,
            CallBindingOrigin.NATIVE,
            CallBindingOrigin.NATIVE_RECEIVER,
        }
        and proof is None
    ):
        raise ValueError("extended call binding needs a typed origin proof")
    if proof is not None:
        _validate_call_binding_proof(proof, parsed_origin, target, evidence)
    return CallBinding(
        parsed_origin,
        target,
        tuple(item for item in evidence if isinstance(item, str)),
        proof,
    )


def _validate_call_binding_proof(
    proof: RecordData, origin: CallBindingOrigin, target: str, evidence: tuple[JsonValue, ...]
) -> None:
    _call_binding_proof_kind(proof, origin, target)
    _validate_call_binding_proof_values(proof)
    witness_ids = proof.get("witness_evidence_ids")
    references = {
        proof.get(key)
        for key in ("constructor_evidence_id", "provider_evidence_id", "assignment_evidence_id")
        if isinstance(proof.get(key), str)
    }
    if isinstance(witness_ids, tuple):
        references.update(item for item in witness_ids if isinstance(item, str))
    if not references <= set(evidence):
        raise ValueError("call binding proof references evidence outside its binding")


def _call_binding_proof_kind(
    proof: RecordData, origin: CallBindingOrigin, target: str
) -> _CallBindingProofKind:
    proof_kind_raw = proof.get("kind")
    if not isinstance(proof_kind_raw, str):
        raise ValueError("invalid call binding proof kind")
    try:
        proof_kind = _CallBindingProofKind(proof_kind_raw)
    except ValueError as error:
        raise ValueError("invalid call binding proof kind") from error
    if {key for key, _ in proof.entries} != _CALL_BINDING_PROOF_FIELDS.get(proof_kind):
        raise ValueError("invalid call binding proof fields")
    if (
        proof_kind
        in {
            _CallBindingProofKind.CONSTRUCTOR,
            _CallBindingProofKind.PROVIDER_MEMBER,
            _CallBindingProofKind.NATIVE_DESCRIPTOR,
        }
        and proof.get("target") != target
    ):
        raise ValueError("call binding proof disagrees with its canonical target")
    expected_origins = {
        _CallBindingProofKind.STORED_FIELD: CallBindingOrigin.STORED_RECEIVER,
        _CallBindingProofKind.CONSTRUCTION: CallBindingOrigin.CONSTRUCTED_RECEIVER,
        _CallBindingProofKind.CONSTRUCTOR: CallBindingOrigin.CONSTRUCTOR,
        _CallBindingProofKind.NATIVE_DESCRIPTOR: CallBindingOrigin.NATIVE,
    }
    if proof_kind in expected_origins and origin is not expected_origins[proof_kind]:
        raise ValueError("call binding proof kind disagrees with its origin")
    if proof_kind is _CallBindingProofKind.NATIVE_DESCRIPTOR and not (
        _valid_datetime_descriptor_proof(proof)
    ):
        raise ValueError("native descriptor proof disagrees with the admitted runtime identity")
    if proof_kind is _CallBindingProofKind.PROVIDER_MEMBER and origin not in {
        CallBindingOrigin.NATIVE,
        CallBindingOrigin.NATIVE_RECEIVER,
        CallBindingOrigin.CONSTRUCTOR,
    }:
        raise ValueError("provider member proof needs a native call origin")
    return proof_kind


def _valid_datetime_descriptor_proof(proof: RecordData) -> bool:
    source_digest = proof.get("stdlib_source_digest")
    return (
        not any(proof.get(key) != value for key, value in _DATETIME_DESCRIPTOR_IDENTITY.items())
        and isinstance(source_digest, str)
        and len(source_digest) == 64
        and not any(character not in "0123456789abcdef" for character in source_digest)
    )


def _validate_call_binding_proof_values(proof: RecordData) -> None:
    for key in ("constructor_evidence_id", "provider_evidence_id", "assignment_evidence_id"):
        item = proof.get(key)
        if item is not None and (not isinstance(item, str) or not item):
            raise ValueError("invalid call binding proof evidence reference")
    for key in (
        "runtime_name",
        "runtime_version",
        "runtime_implementation",
        "descriptor_owner_module",
        "descriptor_owner_qualname",
        "descriptor_member",
        "descriptor_kind",
        "stdlib_source_digest",
        "owner",
        "field",
        "parameter",
    ):
        item = proof.get(key)
        if item is not None and (not isinstance(item, str) or not item):
            raise ValueError("invalid call binding proof identity")
    witness_ids = proof.get("witness_evidence_ids")
    if witness_ids is not None and (
        not isinstance(witness_ids, tuple)
        or not witness_ids
        or any(not isinstance(item, str) or not item for item in witness_ids)
    ):
        raise ValueError("invalid call binding proof witness references")


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


class SourceNameVisibility(StrEnum):
    """Source underscore spelling, separate from a language's API visibility detail."""

    PRIVATE = "private"
    PUBLIC_NAME = "public_name"


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


def parse_source_name_visibility(
    value: JsonValue | RawJson | SourceNameVisibility,
) -> SourceNameVisibility | None:
    """Recognize spelling tags without interpreting foreign language visibility values."""
    if not isinstance(value, str):
        return None
    try:
        return SourceNameVisibility(value)
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


class NativeSignatureKind(StrEnum):
    PARTIAL = "cpython-partial-v1"
    ABC = "cpython-abc-import-v1"
    CONTEXTMANAGER = "sync-generator-contextmanager-v1"


class NativeImplementation(StrEnum):
    CPYTHON = "cpython"


class NativeOrigin(StrEnum):
    BUILTIN = "built-in"


class NativeABCModule(StrEnum):
    ABC = "_abc"


@dataclass(frozen=True, slots=True)
class CPythonPartialIntrinsic:
    kind: NativeSignatureKind
    implementation: NativeImplementation
    version: str
    cache_tag: str
    origin: NativeOrigin


@dataclass(frozen=True, slots=True)
class ContextManagerReturn:
    wrapper: str
    payload: str


@dataclass(frozen=True, slots=True)
class CPythonABCBranch:
    kind: NativeSignatureKind
    module: NativeABCModule
    origin: NativeOrigin
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextManagerSignature:
    kind: NativeSignatureKind
    factory: str
    effective_return: ContextManagerReturn
    support_evidence_ids: tuple[str, ...]
    partial: CPythonPartialIntrinsic
    abc: CPythonABCBranch


def _signature_object(value: JsonValue, fields: set[str]) -> dict[str, JsonValue]:
    if not isinstance(value, RecordData) or {name for name, _ in value.entries} != fields:
        raise ValueError("invalid contextmanager signature fields")
    return dict(value.entries)


def _partial_intrinsic(value: JsonValue) -> CPythonPartialIntrinsic:
    data = _signature_object(value, {"kind", "implementation", "version", "cache_tag", "origin"})
    version, cache_tag = data["version"], data["cache_tag"]
    kind, implementation, origin = data["kind"], data["implementation"], data["origin"]
    if (
        not isinstance(kind, str)
        or NativeSignatureKind(kind) is not NativeSignatureKind.PARTIAL
        or not isinstance(implementation, str)
        or NativeImplementation(implementation) is not NativeImplementation.CPYTHON
        or not isinstance(origin, str)
        or NativeOrigin(origin) is not NativeOrigin.BUILTIN
        or not isinstance(version, str)
        or not isinstance(cache_tag, str)
        or re.fullmatch(r"3\.(11|12)\.[0-9]+", version) is None
        or cache_tag != "cpython-" + "".join(version.split(".")[:2])
    ):
        raise ValueError("invalid CPython partial intrinsic")
    return CPythonPartialIntrinsic(
        NativeSignatureKind.PARTIAL,
        NativeImplementation.CPYTHON,
        version,
        cache_tag,
        NativeOrigin.BUILTIN,
    )


def contextmanager_signature(value: JsonValue) -> ContextManagerSignature:
    """Decode a source-bound signature transform without interpreting Python source."""
    data = _signature_object(
        value, {"kind", "factory", "effective_return", "support_evidence_ids", "partial", "abc"}
    )
    effective = _signature_object(data["effective_return"], {"wrapper", "payload"})
    factory, wrapper, payload = data["factory"], effective["wrapper"], effective["payload"]
    support = data["support_evidence_ids"]
    abc = _signature_object(data["abc"], {"kind", "module", "origin", "members"})
    members = abc["members"]
    kind, abc_kind, module, origin = data["kind"], abc["kind"], abc["module"], abc["origin"]
    if (
        not isinstance(kind, str)
        or NativeSignatureKind(kind) is not NativeSignatureKind.CONTEXTMANAGER
        or not isinstance(abc_kind, str)
        or NativeSignatureKind(abc_kind) is not NativeSignatureKind.ABC
        or not isinstance(module, str)
        or NativeABCModule(module) is not NativeABCModule.ABC
        or not isinstance(origin, str)
        or NativeOrigin(origin) is not NativeOrigin.BUILTIN
        or not isinstance(members, tuple)
        or members
        != (
            "get_cache_token",
            "_abc_init",
            "_abc_register",
            "_abc_instancecheck",
            "_abc_subclasscheck",
            "_get_dump",
            "_reset_registry",
            "_reset_caches",
        )
        or not isinstance(factory, str)
        or not isinstance(wrapper, str)
        or any(
            len(parts := name.split(".")) < 2 or not all(part.isidentifier() for part in parts)
            for name in (factory, wrapper)
        )
        or not isinstance(payload, str)
        or not payload.strip()
        or payload != payload.strip()
        or not isinstance(support, tuple)
        or not support
        or any(not isinstance(item, str) or not item for item in support)
        or len(set(support)) != len(support)
    ):
        raise ValueError("invalid contextmanager signature")
    support_ids = tuple(item for item in support if isinstance(item, str))
    member_names = tuple(item for item in members if isinstance(item, str))
    return ContextManagerSignature(
        NativeSignatureKind.CONTEXTMANAGER,
        factory,
        ContextManagerReturn(wrapper, payload),
        support_ids,
        _partial_intrinsic(data["partial"]),
        CPythonABCBranch(
            NativeSignatureKind.ABC, NativeABCModule.ABC, NativeOrigin.BUILTIN, member_names
        ),
    )


class ProviderBindingKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    DECLARATION = "declaration"
    MODULE = "module"
    ALIAS = "alias"


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    qualified_name: str
    kind: ProviderBindingKind
    evidence_id: str
    target: str | None = None
    supporting_evidence_ids: tuple[str, ...] = ()


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
    provider_bindings: tuple[ProviderBinding, ...] = ()


def in_scope(name: str, scope: str) -> bool:
    """Match a qualified name against a dotted prefix without partial segments."""
    return name == scope or name.startswith(f"{scope}.")
