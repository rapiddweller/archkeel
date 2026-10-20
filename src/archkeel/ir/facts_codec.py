# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Pure strict validation of the language-process wire contract."""

from __future__ import annotations

import builtins as _builtins
import hashlib
import json
import re
from enum import StrEnum
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath

from .codec_strings import expand_strings, intern_strings, profitable_string
from .facts import (
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    AnalyzerInfo,
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    ConstructCapability,
    ConstructSupport,
    ContextManagerSignature,
    Evidence,
    EvidenceClass,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    ForbiddenConstructKind,
    ImportTarget,
    JsonValue,
    Language,
    LocalTarget,
    MethodDescriptor,
    PropertyBinding,
    ProviderBinding,
    ProviderBindingKind,
    Record,
    RecordData,
    ResolutionInput,
    ResolutionRole,
    RuntimeInfo,
    RuntimeRequirementState,
    SourceFacts,
    SourceInfo,
    SourceProfile,
    SourceSectionName,
    UnresolvedTarget,
    parse_runtime_requirement_state,
    source_dirty,
)
from .facts import (
    RawJson as RawJson,
)
from .facts_validation import _call_excerpt_matches, validate_source_facts
from .facts_validation import (
    selector_receiver_site_matches as selector_receiver_site_matches,
)
from .protocol import (
    PYTHON_IMPORT_SURVEY_SECTIONS,
    CollectionRequest,
    CollectionResponse,
    DartSettings,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonProviderSource,
    PythonSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)
from .source_records import (
    RawData as RawData,
)
from .source_records import (
    RawEvidence as RawEvidence,
)
from .source_records import (
    RawRecord as RawRecord,
)
from .source_records import (
    classified as classified,
)
from .source_records import (
    file_evidence as file_evidence,
)
from .source_records import (
    member_inventory_data as member_inventory_data,
)
from .source_records import (
    record_evidence as record_evidence,
)
from .state_codec import parse_state_data, state_data
from .type_shapes import (
    LiteralKind,
    TypeApplication,
    TypeList,
    TypeLiteral,
    TypeMember,
    TypeName,
    TypeShape,
    TypeUnion,
    TypeUnpack,
    UnresolvedType,
)


def call_excerpt_matches(
    expression: str, excerpt: str, line: int, column: int, end_line: int
) -> bool:
    """Check a call expression against its bounded evidence excerpt."""
    return _call_excerpt_matches(expression, excerpt, line, column, end_line)


def contextmanager_signature_data(signature: ContextManagerSignature) -> RawData:
    """Retain both source evidence and the distinct effective return on the wire."""
    return {
        "kind": signature.kind,
        "factory": signature.factory,
        "effective_return": {
            "wrapper": signature.effective_return.wrapper,
            "payload": signature.effective_return.payload,
        },
        "support_evidence_ids": list(signature.support_evidence_ids),
        "abc": {
            "kind": signature.abc.kind,
            "module": signature.abc.module,
            "origin": signature.abc.origin,
            "members": list(signature.abc.members),
        },
        "partial": {
            "kind": signature.partial.kind,
            "implementation": signature.partial.implementation,
            "version": signature.partial.version,
            "cache_tag": signature.partial.cache_tag,
            "origin": signature.partial.origin,
        },
    }


def property_binding_data(binding: PropertyBinding) -> RawData:
    """Write the unchanged JSON shape; the facts owner validates its meaning."""
    return {
        "operation": binding.operation.value,
        "source": binding.source.value,
        "line": binding.line,
        "source_line": binding.source_line,
    }


def method_descriptor_data(descriptor: MethodDescriptor) -> RawData:
    """Write the existing method payload without changing its proof or optional fields."""
    return {
        "method_kind": descriptor.method_kind.value,
        "signature_decorators_proven": descriptor.signature_decorators_proven,
        "source_final_method_binding": descriptor.source_final_method_binding,
        **(
            {"property_binding": property_binding_data(descriptor.property_binding)}
            if descriptor.property_binding is not None
            else {}
        ),
    }


class _TargetKind(StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"
    BUILTIN = "builtin"
    UNRESOLVED = "unresolved"


class _ShapeKind(StrEnum):
    NAME = "name"
    MEMBER = "member"
    APPLICATION = "application"
    UNION = "union"
    LIST = "list"
    LITERAL = "literal"
    UNPACK = "unpack"
    UNRESOLVED = "unresolved"


class _PathToken(StrEnum):
    NUL = "\x00"
    PARENT = ".."
    BACKSLASH = "\\"
    COLON = ":"
    SLASH = "/"


class ProtocolError(ValueError):
    """The collection message cannot substantiate the claims it carries."""


def _unique_fields(pairs: list[tuple[str, RawJson]]) -> dict[str, RawJson]:
    result: dict[str, RawJson] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate field {key}")
        result[key] = value
    return {key: result[key] for key in sorted(result)}


def _json_value(value: object) -> RawJson:
    if isinstance(value, float) and not isfinite(value):
        raise ProtocolError("JSON numbers must be finite")
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, RawJson] = {}
        for key, item in sorted(value.items()):
            if not isinstance(key, str):
                raise ProtocolError("JSON fields must be strings")
            result[key] = _json_value(item)
        return result
    raise ProtocolError("message is not JSON")


def _check_json_value(value: RawJson) -> None:
    if isinstance(value, float) and not isfinite(value):
        raise ProtocolError("JSON numbers must be finite")
    if value is None or isinstance(value, str | bool | int | float):
        return
    if isinstance(value, list):
        for item in value:
            _check_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            if not isinstance(key, str):
                raise ProtocolError("JSON fields must be strings")
            _check_json_value(item)
        return
    raise ProtocolError("message is not JSON")


def _decode(payload: bytes) -> RawJson:
    nonfinite = False

    def number(token: str) -> float:
        nonlocal nonfinite
        value = float(token)
        nonfinite |= not isfinite(value)
        return value

    try:
        value: RawJson = json.loads(
            payload, object_pairs_hook=_unique_fields, parse_float=number, parse_constant=number
        )
        if nonfinite:
            raise ProtocolError("JSON numbers must be finite")
        return value
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ProtocolError(f"invalid collection JSON: {error}") from error


def _object(value: RawJson, fields: set[str], label: str) -> dict[str, RawJson]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ProtocolError(f"{label} fields mismatch")
    return value


def _string(value: RawJson, label: str) -> str:
    if not isinstance(value, str) or not value or _PathToken.NUL in value:
        raise ProtocolError(f"{label} must be a nonempty string")
    return value


def _runtime_requirement_state(value: RawJson) -> RuntimeRequirementState:
    if not isinstance(value, str):
        raise ProtocolError("runtime.requirement_state is invalid")
    try:
        return parse_runtime_requirement_state(value)
    except ValueError as error:
        raise ProtocolError(str(error)) from error


def _relative(value: RawJson, label: str) -> str:
    path = _string(value, label)
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or _PathToken.PARENT in parsed.parts
        or _PathToken.BACKSLASH in path
        or _PathToken.COLON in path
    ):
        raise ProtocolError(f"{label} must stay inside the snapshot")
    return path


def _version(value: RawJson) -> ProtocolVersion:
    if not isinstance(value, str):
        raise ProtocolError("unsupported collection protocol version")
    try:
        return ProtocolVersion(value)
    except ValueError as error:
        raise ProtocolError("unsupported collection protocol version") from error


def decode_request(payload: bytes) -> CollectionRequest:
    raw = _object(
        _decode(payload), {"protocol_version", "snapshot", "scope", "resolver"}, "request"
    )
    version = _version(raw["protocol_version"])
    snapshot = _object(raw["snapshot"], {"root", "git_head", "dirty"}, "snapshot")
    source_root = _string(snapshot["root"], "snapshot.root")
    if not (
        (PurePosixPath(source_root).is_absolute() and _PathToken.BACKSLASH not in source_root)
        or (
            PureWindowsPath(source_root).is_absolute()
            and not (_PathToken.SLASH in source_root and _PathToken.BACKSLASH in source_root)
        )
    ):
        raise ProtocolError("snapshot.root must be an absolute path")
    dirty_raw = snapshot["dirty"]
    if not isinstance(dirty_raw, (bool, str)):
        raise ProtocolError("snapshot.dirty must be a boolean or unknown")
    try:
        dirty_value = source_dirty(dirty_raw)
    except ValueError as error:
        raise ProtocolError("snapshot.dirty must be a boolean or unknown") from error
    scope = _object(raw["scope"], {"roots", "namespace"}, "scope")
    roots_raw = scope["roots"]
    if not isinstance(roots_raw, list) or not roots_raw:
        raise ProtocolError("scope.roots must be a nonempty array")
    roots = tuple(_relative(root, "scope.roots") for root in roots_raw)
    if len(set(roots)) != len(roots):
        raise ProtocolError("scope.roots must not repeat")
    for index, root in enumerate(roots):
        for other in roots[index + 1 :]:
            if (
                PurePosixPath(root) in PurePosixPath(other).parents
                or PurePosixPath(other) in PurePosixPath(root).parents
            ):
                raise ProtocolError("scope.roots must not overlap")
    namespace = _string(scope["namespace"], "scope.namespace")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", namespace) is None:
        raise ProtocolError("scope.namespace must be a dotted namespace")
    resolver_raw = raw["resolver"]
    if not isinstance(resolver_raw, dict):
        raise ProtocolError("resolver fields mismatch")
    try:
        language = Language(_string(resolver_raw.get("language"), "resolver.language"))
    except ValueError as error:
        raise ProtocolError("unsupported collection language") from error
    if language is Language.PYTHON:
        resolver: PythonSettings | DartSettings | TypeScriptSettings = _python_settings(
            resolver_raw, version
        )
    elif language is Language.DART:
        _object(resolver_raw, {"language"}, "resolver")
        resolver = DartSettings()
    elif language is Language.TYPESCRIPT:
        _object(resolver_raw, {"language", "tsconfig"}, "resolver")
        resolver = TypeScriptSettings(_relative(resolver_raw["tsconfig"], "resolver.tsconfig"))
    else:
        raise ProtocolError("unsupported collection language")
    return CollectionRequest(
        SnapshotInput(source_root, _string(snapshot["git_head"], "snapshot.git_head"), dirty_value),
        SourceScope(roots, namespace),
        resolver,
        version,
    )


def _python_settings(raw: dict[str, RawJson], version: ProtocolVersion) -> PythonSettings:
    fields = (
        {"language", "provider_sources", "phase"}
        if version in {ProtocolVersion.V4, ProtocolVersion.V5}
        else {"language"}
    )
    _object(raw, fields, "resolver")
    try:
        phase = PythonCollectionPhase(
            _string(raw.get("phase", PythonCollectionPhase.COLLECT), "resolver.phase")
        )
    except ValueError as error:
        raise ProtocolError("unsupported Python collection phase") from error
    providers = _python_providers(raw.get("provider_sources", []))
    if phase is not PythonCollectionPhase.COLLECT and providers:
        raise ProtocolError("Python import survey cannot include provider sources")
    return PythonSettings(provider_sources=providers, phase=phase)


def encode_request(request: CollectionRequest) -> bytes:
    version = _version(request.protocol_version)
    resolver: dict[str, RawJson] = {"language": request.resolver.language}
    if isinstance(request.resolver, PythonSettings):
        if version in {ProtocolVersion.V4, ProtocolVersion.V5}:
            resolver["phase"] = request.resolver.phase
            resolver["provider_sources"] = [
                _python_provider_payload(entry) for entry in request.resolver.provider_sources
            ]
        elif request.resolver.provider_sources:
            raise ProtocolError("Python provider sources require collection protocol 4.0.0")
        elif request.resolver.phase is not PythonCollectionPhase.COLLECT:
            raise ProtocolError("Python collection phase requires collection protocol 4.0.0")
    if isinstance(request.resolver, TypeScriptSettings):
        resolver["tsconfig"] = request.resolver.tsconfig
    raw = {
        "protocol_version": request.protocol_version,
        "snapshot": {
            "root": request.snapshot.root,
            "git_head": request.snapshot.git_head,
            "dirty": request.snapshot.dirty,
        },
        "scope": {"roots": list(request.scope.roots), "namespace": request.scope.namespace},
        "resolver": resolver,
    }
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    decode_request(payload)
    return payload


def _python_providers(value: RawJson) -> tuple[PythonProviderSource, ...]:
    providers = tuple(_python_provider(entry) for entry in _array(value, "provider sources"))
    if len({item.module for item in providers}) != len(providers) or len(
        {item.path for item in providers}
    ) != len(providers):
        raise ProtocolError("duplicate Python provider source")
    return providers


def _python_provider_payload(entry: PythonProviderSource) -> dict[str, RawJson]:
    return {
        "module": entry.module,
        "path": entry.path,
        "source": entry.source,
        "digest": entry.digest,
    }


def _python_provider(value: RawJson) -> PythonProviderSource:
    item = _object(value, {"module", "path", "source", "digest"}, "Python provider source")
    module: str = _string(item["module"], "Python provider module")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module) is None:
        raise ProtocolError("Python provider module must be a dotted namespace")
    path = _relative(item["path"], "Python provider path")
    stem = ".archkeel-providers/" + module.replace(".", "/")
    if path not in {stem + ".py", stem + "/__init__.py"}:
        raise ProtocolError("Python provider path disagrees with module identity")
    source: str = _record_string(item["source"], "Python provider source")
    digest = _digest(item["digest"], "Python provider digest")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != digest:
        raise ProtocolError("Python provider source digest disagrees")
    return PythonProviderSource(module, path, source, digest)


def _record_object(raw: object, label: str) -> dict[str, RawJson]:
    value = _json_value(raw)
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _record_string(raw: RawJson, label: str) -> str:
    if not isinstance(raw, str):
        raise ProtocolError(f"{label} must be a string")
    return _builtins.str.__str__(raw)


def _record_strings(raw: RawJson, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ProtocolError(f"{label} must be a string array")
    return tuple(_record_string(item, label) for item in raw)


_RECORD_KEYS = set(RECORD_FIELDS)
_EVIDENCE_KEYS = set(EVIDENCE_FIELDS)


def freeze_data(raw: object, label: str = "data") -> RecordData:
    return _freeze_object(_record_object(raw, label))


def _freeze_object(raw: RawJson, label: str = "data") -> RecordData:
    if not isinstance(raw, dict):
        raise ProtocolError(f"{label} must be an object")
    return RecordData(tuple((key, _freeze_validated(item)) for key, item in sorted(raw.items())))


def _freeze_validated(raw: RawJson) -> JsonValue:
    # _record_object already validates the whole tree, including nested keys and numbers.
    if isinstance(raw, str):
        return _builtins.str.__str__(raw)
    if raw is None or isinstance(raw, (bool, int, float)):
        return raw
    if isinstance(raw, list):
        return tuple(_freeze_validated(item) for item in raw)
    return _freeze_object(raw)


def freeze_value(raw: RawJson, label: str) -> JsonValue:
    if isinstance(raw, str):
        return _builtins.str.__str__(raw)
    if raw is None or isinstance(raw, (bool, int, float)):
        return raw
    if isinstance(raw, list):
        return tuple(freeze_value(item, f"{label}[]") for item in raw)
    if isinstance(raw, dict):
        return freeze_data(raw, label)
    raise ValueError(f"{label} is not a JSON value")


def parse_record(raw: object, label: str = "record") -> Record:
    return _parsed_record(_record_object(raw, label), label)


def _parsed_record(item: RawJson, label: str = "record") -> Record:
    if not isinstance(item, dict):
        raise ProtocolError(f"{label} must be an object")
    if set(item) != _RECORD_KEYS:
        raise ValueError(f"{label} fields mismatch")
    try:
        evidence_class = EvidenceClass(
            _record_string(item["evidence_class"], f"{label}.evidence_class")
        )
    except ValueError as exc:
        raise ValueError(f"{label}.evidence_class is invalid") from exc
    rule_ids = _record_strings(item["rule_ids"], f"{label}.rule_ids")
    # schema/architecture-ir-common.schema.json promises minItems: 1 here for VIOLATION but
    # does not enforce it at runtime; a downstream count keyed on `rule_ids[0]` (AD-51, AD-54)
    # would otherwise fail on a malformed file with an IndexError, not a named diagnosis.
    if evidence_class == EvidenceClass.VIOLATION and not rule_ids:
        raise ValueError(f"{label}.rule_ids must not be empty for a VIOLATION record")
    return Record(
        id=_record_string(item["id"], f"{label}.id"),
        evidence_class=evidence_class,
        area=_record_string(item["area"], f"{label}.area"),
        kind=_record_string(item["kind"], f"{label}.kind"),
        title=_record_string(item["title"], f"{label}.title"),
        subjects=_record_strings(item["subjects"], f"{label}.subjects"),
        evidence_ids=_record_strings(item["evidence_ids"], f"{label}.evidence_ids"),
        rule_ids=rule_ids,
        fact_ids=_record_strings(item["fact_ids"], f"{label}.fact_ids"),
        provenance=_record_strings(item["provenance"], f"{label}.provenance"),
        data=_freeze_object(item["data"], f"{label}.data"),
    )


def _position(raw: RawJson, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{label} positions must be integers")
    return raw


def parse_evidence(raw: object, label: str = "evidence") -> Evidence:
    return _parsed_evidence(_record_object(raw, label), label)


def _parsed_evidence(item: RawJson, label: str = "evidence") -> Evidence:
    if not isinstance(item, dict):
        raise ProtocolError(f"{label} must be an object")
    if set(item) != _EVIDENCE_KEYS:
        raise ValueError(f"{label} fields mismatch")
    line, end_line, column = (_position(item[key], label) for key in ("line", "end_line", "column"))
    return Evidence(
        id=_record_string(item["id"], f"{label}.id"),
        file=_record_string(item["file"], f"{label}.file"),
        line=line,
        end_line=end_line,
        column=column,
        excerpt=_record_string(item["excerpt"], f"{label}.excerpt"),
    )


def raw_value(value: JsonValue) -> RawJson:
    if isinstance(value, RecordData):
        return {key: raw_value(item) for key, item in value.entries}
    if isinstance(value, tuple):
        return [raw_value(item) for item in value]
    return value


def thaw_data(value: RecordData) -> dict[str, RawJson]:
    return {key: raw_value(item) for key, item in value.entries}


def record_payload(record: Record) -> dict[str, RawJson]:
    return {
        "id": record.id,
        "evidence_class": record.evidence_class.value,
        "area": record.area,
        "kind": record.kind,
        "title": record.title,
        "subjects": list(record.subjects),
        "evidence_ids": list(record.evidence_ids),
        "rule_ids": list(record.rule_ids),
        "fact_ids": list(record.fact_ids),
        "provenance": list(record.provenance),
        "data": thaw_data(record.data),
    }


def evidence_payload(evidence: Evidence) -> dict[str, RawJson]:
    return {
        "id": evidence.id,
        "file": evidence.file,
        "line": evidence.line,
        "end_line": evidence.end_line,
        "column": evidence.column,
        "excerpt": evidence.excerpt,
    }


def _array(value: RawJson, label: str) -> list[RawJson]:
    if not isinstance(value, list):
        raise ProtocolError(f"{label} must be an array")
    return value


def _boolean(value: RawJson, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolError(f"{label} must be a boolean")
    return value


def _count(value: RawJson, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProtocolError(f"{label} must be a nonnegative integer")
    return value


def _digest(value: RawJson, label: str) -> str:
    text = _string(value, label)
    if re.fullmatch("[a-f0-9]{64}", text) is None:
        raise ProtocolError(f"{label} must be a SHA-256 digest")
    return text


def _profile(value: RawJson) -> SourceProfile:
    try:
        return SourceProfile(_string(value, "source profile"))
    except ValueError as error:
        raise ProtocolError("unregistered source profile") from error


def _section_name(value: RawJson) -> SourceSectionName:
    try:
        return SourceSectionName(_string(value, "source section"))
    except ValueError as error:
        raise ProtocolError("unsupported source section") from error


def _file(value: RawJson) -> FileFact:
    item = _object(
        value,
        {
            "id",
            "rel_path",
            "module",
            "package",
            "all_exports",
            "all_literal",
            "compatibility_logic_free",
            "stable_bindings",
            "blank",
            "evidence_id",
        },
        "file",
    )
    return FileFact(
        _string(item["id"], "file.id"),
        _relative(item["rel_path"], "file.rel_path"),
        _string(item["module"], "file.module"),
        _string(item["package"], "file.package"),
        frozenset(_record_strings(item["all_exports"], "file.all_exports")),
        _boolean(item["all_literal"], "file.all_literal"),
        _boolean(item["compatibility_logic_free"], "file.compatibility_logic_free"),
        frozenset(_record_strings(item["stable_bindings"], "file.stable_bindings")),
        _boolean(item["blank"], "file.blank"),
        _string(item["evidence_id"], "file.evidence_id"),
    )


def _input(value: RawJson) -> ResolutionInput:
    item = _object(value, {"path", "digest", "role"}, "input")
    try:
        role = ResolutionRole(_string(item["role"], "input.role"))
    except ValueError as error:
        raise ProtocolError("input.role is invalid") from error
    return ResolutionInput(
        _relative(item["path"], "input.path"),
        _digest(item["digest"], "input.digest"),
        role,
    )


def _target(value: RawJson) -> ImportTarget:
    if not isinstance(value, dict):
        raise ProtocolError("import target must be an object")
    try:
        kind = _TargetKind(_string(value.get("kind"), "target.kind"))
    except ValueError as error:
        raise ProtocolError("invalid import target kind") from error
    if kind is _TargetKind.LOCAL:
        item = _object(
            value,
            {"kind", "import_id", "module", "file", "runtime_file", "declaration_file"},
            "local target",
        )
        return LocalTarget(
            _string(item["import_id"], "target.import_id"),
            _string(item["module"], "target.module"),
            _relative(item["file"], "target.file"),
            _relative(item["runtime_file"], "target.runtime_file")
            if item["runtime_file"] is not None
            else None,
            _relative(item["declaration_file"], "target.declaration_file")
            if item["declaration_file"] is not None
            else None,
        )
    if kind is _TargetKind.EXTERNAL:
        item = _object(value, {"kind", "import_id", "package"}, "external target")
        return ExternalPackageTarget(
            _string(item["import_id"], "target.import_id"),
            _string(item["package"], "target.package"),
        )
    if kind is _TargetKind.BUILTIN:
        item = _object(value, {"kind", "import_id", "name"}, "builtin target")
        return BuiltinTarget(
            _string(item["import_id"], "target.import_id"), _string(item["name"], "target.name")
        )
    if kind is _TargetKind.UNRESOLVED:
        item = _object(value, {"kind", "import_id", "specifier", "reason"}, "unresolved target")
        return UnresolvedTarget(
            _string(item["import_id"], "target.import_id"),
            _string(item["specifier"], "target.specifier"),
            _string(item["reason"], "target.reason"),
        )
    raise ProtocolError("invalid import target kind")


def _target_payload(target: ImportTarget) -> dict[str, RawJson]:
    if isinstance(target, LocalTarget):
        return {
            "kind": _TargetKind.LOCAL.value,
            "import_id": target.import_id,
            "module": target.module,
            "file": target.file,
            "runtime_file": target.runtime_file,
            "declaration_file": target.declaration_file,
        }
    if isinstance(target, ExternalPackageTarget):
        return {
            "kind": _TargetKind.EXTERNAL.value,
            "import_id": target.import_id,
            "package": target.package,
        }
    if isinstance(target, BuiltinTarget):
        return {
            "kind": _TargetKind.BUILTIN.value,
            "import_id": target.import_id,
            "name": target.name,
        }
    return {
        "kind": _TargetKind.UNRESOLVED.value,
        "import_id": target.import_id,
        "specifier": target.specifier,
        "reason": target.reason,
    }


def _shape(value: RawJson, protocol_version: ProtocolVersion) -> TypeShape:
    if not isinstance(value, dict):
        raise ProtocolError("type shape must be an object")
    try:
        kind = _ShapeKind(_string(value.get("kind"), "type shape.kind"))
    except ValueError as error:
        raise ProtocolError("invalid type shape kind") from error
    text = _record_string(value.get("text"), "type shape.text")
    if kind is _ShapeKind.NAME:
        _object(value, {"kind", "text", "name"}, "type name")
        return TypeName(text, _string(value["name"], "type name.name"))
    if kind is _ShapeKind.MEMBER:
        _object(value, {"kind", "text", "owner", "member"}, "type member")
        return TypeMember(
            text,
            _shape(value["owner"], protocol_version),
            _string(value["member"], "type member.member"),
        )
    if kind is _ShapeKind.APPLICATION:
        _object(value, {"kind", "text", "head", "arguments", "tuple_arguments"}, "type application")
        return TypeApplication(
            text,
            _shape(value["head"], protocol_version),
            tuple(
                _shape(item, protocol_version)
                for item in _array(value["arguments"], "type arguments")
            ),
            _boolean(value["tuple_arguments"], "type tuple arguments"),
        )
    if kind is _ShapeKind.UNION:
        _object(value, {"kind", "text", "left", "right"}, "type union")
        return TypeUnion(
            text, _shape(value["left"], protocol_version), _shape(value["right"], protocol_version)
        )
    if kind is _ShapeKind.LIST and protocol_version in {
        ProtocolVersion.V3,
        ProtocolVersion.V4,
        ProtocolVersion.V5,
    }:
        _object(value, {"kind", "text", "elements"}, "type list")
        return TypeList(
            text,
            tuple(
                _shape(item, protocol_version)
                for item in _array(value["elements"], "type list elements")
            ),
        )
    if kind is _ShapeKind.LITERAL:
        _object(value, {"kind", "text", "literal_kind"}, "type literal")
        try:
            literal = LiteralKind(_string(value["literal_kind"], "literal kind"))
        except ValueError as error:
            raise ProtocolError("invalid literal kind") from error
        return TypeLiteral(text, literal)
    if kind is _ShapeKind.UNPACK:
        _object(value, {"kind", "text", "argument"}, "type unpack")
        return TypeUnpack(text, _shape(value["argument"], protocol_version))
    if kind is _ShapeKind.UNRESOLVED:
        _object(value, {"kind", "text", "valid_syntax"}, "unresolved type")
        return UnresolvedType(text, _boolean(value["valid_syntax"], "type valid syntax"))
    raise ProtocolError("invalid type shape kind")


def _shape_payload(shape: TypeShape) -> dict[str, RawJson]:
    base: dict[str, RawJson] = {"text": shape.text}
    if isinstance(shape, TypeName):
        return {**base, "kind": _ShapeKind.NAME.value, "name": shape.name}
    if isinstance(shape, TypeMember):
        return {
            **base,
            "kind": _ShapeKind.MEMBER.value,
            "owner": _shape_payload(shape.owner),
            "member": shape.member,
        }
    if isinstance(shape, TypeApplication):
        return {
            **base,
            "kind": _ShapeKind.APPLICATION.value,
            "head": _shape_payload(shape.head),
            "arguments": [_shape_payload(item) for item in shape.arguments],
            "tuple_arguments": shape.tuple_arguments,
        }
    if isinstance(shape, TypeUnion):
        return {
            **base,
            "kind": _ShapeKind.UNION.value,
            "left": _shape_payload(shape.left),
            "right": _shape_payload(shape.right),
        }
    if isinstance(shape, TypeList):
        return {
            **base,
            "kind": _ShapeKind.LIST.value,
            "elements": [_shape_payload(element) for element in shape.elements],
        }
    if isinstance(shape, TypeLiteral):
        return {**base, "kind": _ShapeKind.LITERAL.value, "literal_kind": shape.kind.value}
    if isinstance(shape, TypeUnpack):
        return {**base, "kind": _ShapeKind.UNPACK.value, "argument": _shape_payload(shape.argument)}
    return {**base, "kind": _ShapeKind.UNRESOLVED.value, "valid_syntax": shape.valid_syntax}


def _source(value: RawJson) -> SourceInfo:
    item = _object(value, {"git_head", "dirty", "source_digest", "scope"}, "source")
    dirty_raw = item["dirty"]
    if not isinstance(dirty_raw, (bool, str)):
        raise ProtocolError("source.dirty is invalid")
    try:
        dirty = source_dirty(dirty_raw)
    except ValueError as error:
        raise ProtocolError("source.dirty is invalid") from error
    return SourceInfo(
        _string(item["git_head"], "source.git_head"),
        dirty,
        _digest(item["source_digest"], "source.source_digest"),
        _record_strings(item["scope"], "source.scope"),
    )


def _section(value: RawJson) -> FactSection:
    item = _object(value, {"name", "records"}, "section")
    return FactSection(
        _section_name(item["name"]),
        tuple(_parsed_record(record) for record in _array(item["records"], "section.records")),
    )


def _coverage(value: RawJson) -> CollectionCoverage:
    item = _object(
        value, {"selected_files", "files_read", "files_parsed", "full_scope", "gaps"}, "coverage"
    )
    return CollectionCoverage(
        tuple(
            _relative(path, "coverage.selected_files")
            for path in _array(item["selected_files"], "selected files")
        ),
        _count(item["files_read"], "coverage.files_read"),
        _count(item["files_parsed"], "coverage.files_parsed"),
        _boolean(item["full_scope"], "coverage.full_scope"),
        tuple(_parsed_record(record) for record in _array(item["gaps"], "coverage.gaps")),
    )


def _construct_capability(raw: RawJson) -> ConstructCapability:
    item = _object(raw, {"name", "status"}, "construct capability")
    return ConstructCapability(
        ForbiddenConstructKind(_string(item["name"], "construct capability.name")),
        ConstructSupport(_string(item["status"], "construct capability.status")),
    )


def _capabilities(value: RawJson) -> Capabilities:
    item = _object(value, {"sections", "resolution_features", "constructs"}, "capabilities")
    return Capabilities(
        tuple(
            _section_name(section) for section in _array(item["sections"], "capabilities.sections")
        ),
        _record_strings(item["resolution_features"], "resolution_features"),
        tuple(
            _construct_capability(entry)
            for entry in _array(item["constructs"], "capabilities.constructs")
        ),
    )


def _file_payload(entry: FileFact) -> dict[str, RawJson]:
    return {
        "id": entry.id,
        "rel_path": entry.rel_path,
        "module": entry.module,
        "package": entry.package,
        "all_exports": [value for value in sorted(entry.all_exports)],
        "all_literal": entry.all_literal,
        "compatibility_logic_free": entry.compatibility_logic_free,
        "stable_bindings": [value for value in sorted(entry.stable_bindings)],
        "blank": entry.blank,
        "evidence_id": entry.evidence_id,
    }


def _runtime_info(value: RawJson, protocol_version: ProtocolVersion) -> RuntimeInfo:
    expected = (
        {"name", "version", "required", "requirement_state"}
        if protocol_version
        in {ProtocolVersion.V2, ProtocolVersion.V3, ProtocolVersion.V4, ProtocolVersion.V5}
        else {"name", "version", "required"}
    )
    if not isinstance(value, dict) or set(value) != expected:
        raise ProtocolError("runtime fields mismatch for collection protocol version")
    return RuntimeInfo(
        _string(value["name"], "runtime.name"),
        _string(value["version"], "runtime.version"),
        _string(value["required"], "runtime.required") if value["required"] is not None else None,
        _runtime_requirement_state(value.get("requirement_state", "declared")),
    )


def _source_facts(value: RawJson, version: ProtocolVersion) -> SourceFacts:
    item = _object(
        value,
        {
            "profile",
            "adapter",
            "runtime",
            "source",
            "capabilities",
            "inputs",
            "files",
            "imports",
            "sections",
            "coverage",
            "evidence",
            "uncertain_reexports",
            "type_shapes",
            "state",
            "candidate_evidence",
        }
        | ({"provider_bindings"} if version in {ProtocolVersion.V4, ProtocolVersion.V5} else set()),
        "facts",
    )
    adapter = _object(item["adapter"], {"name", "version", "code_digest"}, "adapter")
    uncertain: list[tuple[str, tuple[str, ...]]] = []
    for entry in _array(item["uncertain_reexports"], "uncertain reexports"):
        pair = _object(entry, {"binding", "origins"}, "uncertain reexport")
        uncertain.append(
            (
                _string(pair["binding"], "reexport binding"),
                _record_strings(pair["origins"], "reexport origins"),
            )
        )
    shapes: list[tuple[str, TypeShape]] = []
    for entry in _array(item["type_shapes"], "type shapes"):
        pair = _object(entry, {"expression", "shape"}, "type shape entry")
        shapes.append(
            (_string(pair["expression"], "type expression"), _shape(pair["shape"], version))
        )
    facts = SourceFacts(
        _profile(item["profile"]),
        AnalyzerInfo(
            _string(adapter["name"], "adapter.name"),
            _string(adapter["version"], "adapter.version"),
            _digest(adapter["code_digest"], "adapter.code_digest"),
        ),
        _runtime_info(item["runtime"], version),
        _source(item["source"]),
        _capabilities(item["capabilities"]),
        tuple(_input(entry) for entry in _array(item["inputs"], "inputs")),
        tuple(_file(entry) for entry in _array(item["files"], "files")),
        tuple(_target(entry) for entry in _array(item["imports"], "imports")),
        tuple(_section(entry) for entry in _array(item["sections"], "sections")),
        _coverage(item["coverage"]),
        tuple(_parsed_evidence(entry) for entry in _array(item["evidence"], "evidence")),
        tuple(uncertain),
        tuple(shapes),
        parse_state_data(_freeze_object(item["state"])),
        tuple(
            _parsed_evidence(entry)
            for entry in _array(item["candidate_evidence"], "candidate evidence")
        ),
        tuple(
            _provider_binding(entry)
            for entry in _array(item.get("provider_bindings", []), "provider bindings")
        ),
    )
    _contextmanager_protocol(facts, version)
    validate_source_facts(facts)
    return facts


def _compact_source_facts(value: RawJson) -> dict[str, RawJson]:
    """Encode source records and evidence as positional rows with a lossless string table."""
    facts = _compact_object(value, "facts")
    sections = _array(facts["sections"], "sections")
    packed_sections, data_fields = _pack_source_sections(sections)
    compact_rows, table = intern_strings(
        {
            "records": [
                row
                for packed_section in packed_sections
                for row in _array(packed_section["records"], "records")
            ],
            "evidence": _source_evidence_rows(facts["evidence"], "evidence"),
            "candidate_evidence": _source_evidence_rows(
                facts["candidate_evidence"], "candidate evidence"
            ),
        },
        profitable=profitable_string,
    )
    rows = _compact_object(compact_rows, "compact source rows")
    encoded_records = _array(rows["records"], "compact records")
    cursor = 0
    compact_sections: list[RawJson] = []
    for packed_section in packed_sections:
        record_count = len(_array(packed_section["records"], "records"))
        compact_sections.append(
            {
                "name": packed_section["name"],
                "records": encoded_records[cursor : cursor + record_count],
            }
        )
        cursor += record_count
    compact: dict[str, RawJson] = {
        **{
            key: item
            for key, item in facts.items()
            if key not in {"sections", "evidence", "candidate_evidence"}
        },
        "sections": compact_sections,
        "evidence": rows["evidence"],
        "candidate_evidence": rows["candidate_evidence"],
    }
    wire_data_fields: list[RawJson] = []
    for field in data_fields:
        wire_data_fields.append(field)
    wire_string_table: list[RawJson] = []
    for entry in table:
        wire_string_table.append(entry)
    compact["encoding"] = {
        "kind": "source-facts-columnar-v1",
        "record_fields": list(RECORD_FIELDS),
        "evidence_fields": list(EVIDENCE_FIELDS),
        "data_fields": wire_data_fields,
        "string_reference": "$<index>",
    }
    compact["string_table"] = wire_string_table
    return compact


def _pack_source_sections(
    sections: list[RawJson],
) -> tuple[list[dict[str, RawJson]], list[str]]:
    """Pack record dictionaries as rows and return their sorted data keys."""
    data_fields = sorted(
        {
            key
            for raw_section in sections
            for raw_record in _array(_compact_object(raw_section, "section")["records"], "records")
            for key in _compact_object(_compact_object(raw_record, "record")["data"], "record.data")
        }
    )
    data_indexes = {field: index for index, field in enumerate(data_fields)}
    packed_sections: list[dict[str, RawJson]] = []
    for raw_section in sections:
        section = _compact_object(raw_section, "section")
        packed_records: list[RawJson] = []
        for raw_record in _array(section["records"], "records"):
            record = _compact_object(raw_record, "record")
            data = _compact_object(record["data"], "record.data")
            packed_records.append(
                [
                    *(record[field] for field in RECORD_FIELDS[:-1]),
                    [[data_indexes[key], data[key]] for key in sorted(data)],
                ]
            )
        packed_sections.append({"name": section["name"], "records": packed_records})
    return packed_sections, data_fields


def _source_evidence_rows(raw: RawJson, label: str) -> list[RawJson]:
    """Encode evidence objects in the exact positional wire field order."""
    rows: list[RawJson] = []
    for entry in _array(raw, label):
        evidence = _compact_object(entry, "evidence")
        rows.append([evidence[field] for field in EVIDENCE_FIELDS])
    return rows


def _compact_object(raw: RawJson, label: str) -> dict[str, RawJson]:
    """Shallow-check encoder-owned objects; nested values are validated at the JSON boundary."""
    if not isinstance(raw, dict):
        raise ProtocolError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in raw):
        raise ProtocolError("JSON fields must be strings")
    return raw


def _expand_source_facts(value: RawJson) -> dict[str, RawJson]:
    """Validate and expand V5 rows before ordinary source-fact validation."""
    item = _record_object(value, "compact source facts")
    encoding = _object(
        item.get("encoding"),
        {"kind", "record_fields", "evidence_fields", "data_fields", "string_reference"},
        "source encoding",
    )
    if encoding != {
        "kind": "source-facts-columnar-v1",
        "record_fields": list(RECORD_FIELDS),
        "evidence_fields": list(EVIDENCE_FIELDS),
        "data_fields": encoding.get("data_fields"),
        "string_reference": "$<index>",
    }:
        raise ProtocolError("unsupported source facts columnar encoding")
    data_fields = tuple(
        _record_string(field, "encoding.data_fields[]")
        for field in _array(encoding["data_fields"], "encoding.data_fields")
    )
    if tuple(sorted(set(data_fields))) != data_fields:
        raise ProtocolError("source encoding data fields must be sorted and unique")
    table = tuple(
        _record_string(entry, "string_table[]")
        for entry in _array(item.get("string_table"), "string_table")
    )
    if tuple(sorted(set(table))) != table:
        raise ProtocolError("source string table must be sorted and unique")
    raw_sections = _array(item.get("sections"), "sections")
    section_names: set[str] = set()
    record_rows: list[RawJson] = []
    section_shapes: list[tuple[str, int]] = []
    for raw_section in raw_sections:
        section = _object(raw_section, {"name", "records"}, "compact section")
        name = _string(section["name"], "section.name")
        if name in section_names:
            raise ProtocolError("duplicate compact source section")
        section_names.add(name)
        records = _array(section["records"], "compact records")
        record_rows.extend(records)
        section_shapes.append((name, len(records)))
    expanded_rows = expand_strings(
        {
            "records": record_rows,
            "evidence": _array(item.get("evidence"), "evidence"),
            "candidate_evidence": _array(item.get("candidate_evidence"), "candidate evidence"),
        },
        list(table),
    )
    expanded_row_object = _compact_object(expanded_rows, "expanded source rows")
    expanded_records = _array(expanded_row_object["records"], "expanded records")
    expanded_sections: list[RawJson] = []
    cursor = 0
    for name, record_count in section_shapes:
        section_records: list[RawJson] = [
            _expand_source_record(row, data_fields)
            for row in expanded_records[cursor : cursor + record_count]
        ]
        expanded_sections.append({"name": name, "records": section_records})
        cursor += record_count
    expanded: dict[str, RawJson] = {
        key: entry for key, entry in item.items() if key not in {"encoding", "string_table"}
    }
    expanded["sections"] = expanded_sections
    expanded["evidence"] = _expand_evidence_rows(expanded_row_object["evidence"], "evidence")
    expanded["candidate_evidence"] = _expand_evidence_rows(
        expanded_row_object["candidate_evidence"], "candidate evidence"
    )
    if _compact_source_facts(expanded) != item:
        raise ProtocolError("source facts columnar encoding is not canonical")
    return expanded


def _expand_source_record(value: RawJson, data_fields: tuple[str, ...]) -> dict[str, RawJson]:
    row = _array(value, "compact record")
    if len(row) != len(RECORD_FIELDS):
        raise ProtocolError("compact source record width mismatch")
    data: dict[str, RawJson] = {}
    previous = -1
    for pair_raw in _array(row[-1], "compact record data"):
        pair = _array(pair_raw, "compact data pair")
        if len(pair) != 2 or not isinstance(pair[0], int) or isinstance(pair[0], bool):
            raise ProtocolError("compact data pair is invalid")
        index = pair[0]
        if index <= previous or index >= len(data_fields):
            raise ProtocolError("compact data field index is invalid")
        previous = index
        data[data_fields[index]] = pair[1]
    record = dict(zip(RECORD_FIELDS[:-1], row[:-1], strict=True))
    record["data"] = data
    return record


def _expand_evidence_rows(value: RawJson, label: str) -> list[RawJson]:
    output: list[RawJson] = []
    for raw_row in _array(value, label):
        row = _array(raw_row, f"{label} row")
        if len(row) != len(EVIDENCE_FIELDS):
            raise ProtocolError(f"{label} row width mismatch")
        output.append(dict(zip(EVIDENCE_FIELDS, row, strict=True)))
    return output


def _response(decoded: RawJson) -> CollectionResponse:
    try:
        if not isinstance(decoded, dict):
            raise ProtocolError("response must be an object")
        version = _version(decoded.get("protocol_version"))
        raw = _object(
            decoded,
            {"protocol_version", "facts"}
            | (
                {"provider_sources"}
                if version in {ProtocolVersion.V4, ProtocolVersion.V5}
                else set()
            ),
            "response",
        )
        raw_facts = raw["facts"]
        if version is ProtocolVersion.V5:
            raw_facts = _expand_source_facts(raw_facts)
        facts = _source_facts(raw_facts, version)
        providers = _python_providers(raw.get("provider_sources", []))
        if providers and (
            facts.profile is not SourceProfile.PYTHON
            or frozenset(facts.capabilities.sections) != frozenset(PYTHON_IMPORT_SURVEY_SECTIONS)
        ):
            raise ProtocolError("captured provider sources require a Python import survey")
        return CollectionResponse(facts, version, providers)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ProtocolError(str(error)) from error


def decode_response(payload: bytes) -> CollectionResponse:
    # The decoder owns a JSON-only tree; internal parsers retain structure and semantic checks.
    return _response(_decode(payload))


def _provider_binding(value: RawJson) -> ProviderBinding:
    if not isinstance(value, dict):
        raise ProtocolError("provider binding must be an object")
    kind = ProviderBindingKind(_string(value.get("kind"), "provider binding.kind"))
    alias = kind is ProviderBindingKind.ALIAS
    item = _object(
        value,
        {"qualified_name", "kind", "evidence_id"}
        | ({"target", "supporting_evidence_ids"} if alias else set()),
        "provider binding",
    )
    return ProviderBinding(
        _string(item["qualified_name"], "provider binding.qualified_name"),
        kind,
        _string(item["evidence_id"], "provider binding.evidence_id"),
        _string(item["target"], "provider binding.target") if alias else None,
        _record_strings(item["supporting_evidence_ids"], "provider binding support")
        if alias
        else (),
    )


def _provider_binding_payload(binding: ProviderBinding) -> dict[str, RawJson]:
    if binding.kind is not ProviderBindingKind.ALIAS and (
        binding.target is not None or binding.supporting_evidence_ids
    ):
        raise ProtocolError("direct provider binding cannot carry alias proof fields")
    return {
        "qualified_name": binding.qualified_name,
        "kind": binding.kind.value,
        "evidence_id": binding.evidence_id,
        **(
            {
                "target": binding.target,
                "supporting_evidence_ids": list(binding.supporting_evidence_ids),
            }
            if binding.kind is ProviderBindingKind.ALIAS
            else {}
        ),
    }


def _runtime_payload(runtime: RuntimeInfo, version: ProtocolVersion) -> dict[str, RawJson]:
    if (
        version is ProtocolVersion.V1
        and runtime.requirement_state != RuntimeRequirementState.DECLARED
    ):
        raise ProtocolError("protocol 1.0.0 cannot carry runtime.requirement_state")
    return {
        "name": runtime.name,
        "version": runtime.version,
        "required": runtime.required,
        **(
            {"requirement_state": runtime.requirement_state}
            if version
            in {ProtocolVersion.V2, ProtocolVersion.V3, ProtocolVersion.V4, ProtocolVersion.V5}
            else {}
        ),
    }


def _contextmanager_protocol(facts: SourceFacts, version: ProtocolVersion) -> None:
    if version not in {ProtocolVersion.V4, ProtocolVersion.V5} and any(
        record.data.get("contextmanager_signature") is not None
        for section in facts.sections
        for record in section.records
    ):
        raise ProtocolError("contextmanager signatures require collection protocol 4.0.0")


def _facts_payload(
    facts: SourceFacts, version: ProtocolVersion, runtime: dict[str, RawJson]
) -> dict[str, RawJson]:
    return {
        **(
            {
                "provider_bindings": [
                    _provider_binding_payload(entry) for entry in facts.provider_bindings
                ]
            }
            if version in {ProtocolVersion.V4, ProtocolVersion.V5}
            else {}
        ),
        "state": thaw_data(state_data(facts.state)),
        "candidate_evidence": [evidence_payload(entry) for entry in facts.candidate_evidence],
        "profile": facts.profile,
        "adapter": {
            "name": facts.adapter.name,
            "version": facts.adapter.version,
            "code_digest": facts.adapter.code_digest,
        },
        "runtime": runtime,
        "source": {
            "git_head": facts.source.git_head,
            "dirty": facts.source.dirty,
            "source_digest": facts.source.source_digest,
            "scope": list(facts.source.scope),
        },
        "capabilities": {
            "sections": list(facts.capabilities.sections),
            "resolution_features": list(facts.capabilities.resolution_features),
            "constructs": [
                {"name": entry.name.value, "status": entry.status.value}
                for entry in facts.capabilities.constructs
            ],
        },
        "inputs": [
            {"path": entry.path, "digest": entry.digest, "role": entry.role}
            for entry in facts.inputs
        ],
        "files": [_file_payload(entry) for entry in facts.files],
        "imports": [_target_payload(target) for target in facts.imports],
        "sections": [
            {
                "name": section.name,
                "records": [record_payload(record) for record in section.records],
            }
            for section in facts.sections
        ],
        "coverage": {
            "selected_files": list(facts.coverage.selected_files),
            "files_read": facts.coverage.files_read,
            "files_parsed": facts.coverage.files_parsed,
            "full_scope": facts.coverage.full_scope,
            "gaps": [record_payload(record) for record in facts.coverage.gaps],
        },
        "evidence": [evidence_payload(entry) for entry in facts.evidence],
        "uncertain_reexports": [
            {"binding": binding, "origins": list(origins)}
            for binding, origins in facts.uncertain_reexports
        ],
        "type_shapes": [
            {"expression": expression, "shape": _shape_payload(shape)}
            for expression, shape in facts.type_shapes
        ],
    }


def encode_response(response: CollectionResponse) -> bytes:
    facts = response.facts
    version = _version(response.protocol_version)
    _contextmanager_protocol(facts, version)
    if facts.provider_bindings and version not in {ProtocolVersion.V4, ProtocolVersion.V5}:
        raise ProtocolError("provider bindings require collection protocol 4.0.0")
    if response.provider_sources and version not in {ProtocolVersion.V4, ProtocolVersion.V5}:
        raise ProtocolError("captured provider sources require collection protocol 4.0.0")
    runtime = _runtime_payload(facts.runtime, version)
    raw: dict[str, RawJson] = {
        "protocol_version": response.protocol_version,
        **(
            {
                "provider_sources": [
                    _python_provider_payload(entry) for entry in response.provider_sources
                ]
            }
            if version in {ProtocolVersion.V4, ProtocolVersion.V5}
            else {}
        ),
        "facts": _facts_payload(facts, version, runtime),
    }
    if version is ProtocolVersion.V5:
        raw["facts"] = _compact_source_facts(raw["facts"])
    payload = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    _check_json_value(raw)
    _response(raw)
    return payload


def raw_record(record: Record) -> RawRecord:
    return RawRecord(
        id=record.id,
        evidence_class=record.evidence_class.value,
        area=record.area,
        kind=record.kind,
        title=record.title,
        subjects=list(record.subjects),
        evidence_ids=list(record.evidence_ids),
        rule_ids=list(record.rule_ids),
        fact_ids=list(record.fact_ids),
        provenance=list(record.provenance),
        data=thaw_data(record.data),
    )


def raw_evidence(evidence: Evidence) -> RawEvidence:
    return RawEvidence(
        id=evidence.id,
        file=evidence.file,
        line=evidence.line,
        end_line=evidence.end_line,
        column=evidence.column,
        excerpt=evidence.excerpt,
    )
