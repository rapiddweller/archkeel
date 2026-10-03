# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Pure strict validation of the language-process wire contract."""

from __future__ import annotations

import json
import re
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, TypeAlias, TypeGuard, get_args

from .facts import (
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    AnalyzerInfo,
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    Evidence,
    EvidenceClass,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    ImportTarget,
    JsonValue,
    LocalTarget,
    Record,
    RecordData,
    ResolutionInput,
    RuntimeInfo,
    SourceFacts,
    SourceInfo,
    SourceProfile,
    SourceSectionName,
    UnresolvedTarget,
)
from .facts_validation import validate_source_facts
from .protocol import (
    PROTOCOL_VERSION,
    CollectionRequest,
    CollectionResponse,
    DartSettings,
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
    record_evidence as record_evidence,
)
from .state_codec import parse_state_data, state_data
from .type_shapes import (
    LiteralKind,
    TypeApplication,
    TypeLiteral,
    TypeMember,
    TypeName,
    TypeShape,
    TypeUnion,
    TypeUnpack,
    UnresolvedType,
)

RawJson: TypeAlias = str | int | float | bool | None | list["RawJson"] | dict[str, "RawJson"]


class ProtocolError(ValueError):
    """The collection message cannot substantiate the claims it carries."""


def _unique_fields(pairs: list[tuple[str, RawJson]]) -> dict[str, RawJson]:
    result: dict[str, RawJson] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate field {key}")
        result[key] = value
    return result


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


def _decode(payload: bytes) -> RawJson:
    try:
        return _json_value(json.loads(payload, object_pairs_hook=_unique_fields))
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ProtocolError(f"invalid collection JSON: {error}") from error


def _object(value: RawJson, fields: set[str], label: str) -> dict[str, RawJson]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ProtocolError(f"{label} fields mismatch")
    return value


def _string(value: RawJson, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProtocolError(f"{label} must be a nonempty string")
    return value


def _relative(value: RawJson, label: str) -> str:
    path = _string(value, label)
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path or ":" in path:
        raise ProtocolError(f"{label} must stay inside the snapshot")
    return path


def _version(value: RawJson) -> None:
    if value != PROTOCOL_VERSION:
        raise ProtocolError("unsupported collection protocol version")


def decode_request(payload: bytes) -> CollectionRequest:
    raw = _object(
        _decode(payload), {"protocol_version", "snapshot", "scope", "resolver"}, "request"
    )
    _version(raw["protocol_version"])
    snapshot = _object(raw["snapshot"], {"root", "git_head", "dirty"}, "snapshot")
    source_root = _string(snapshot["root"], "snapshot.root")
    if not (
        (PurePosixPath(source_root).is_absolute() and "\\" not in source_root)
        or (
            PureWindowsPath(source_root).is_absolute()
            and not ("/" in source_root and "\\" in source_root)
        )
    ):
        raise ProtocolError("snapshot.root must be an absolute path")
    dirty = snapshot["dirty"]
    if not isinstance(dirty, bool) and dirty != "unknown":
        raise ProtocolError("snapshot.dirty must be a boolean or unknown")
    dirty_value: bool | Literal["unknown"] = dirty if isinstance(dirty, bool) else "unknown"
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
    language = resolver_raw.get("language")
    if language == "python":
        _object(resolver_raw, {"language"}, "resolver")
        resolver: PythonSettings | DartSettings | TypeScriptSettings = PythonSettings()
    elif language == "dart":
        _object(resolver_raw, {"language"}, "resolver")
        resolver = DartSettings()
    elif language == "typescript":
        _object(resolver_raw, {"language", "tsconfig"}, "resolver")
        resolver = TypeScriptSettings(_relative(resolver_raw["tsconfig"], "resolver.tsconfig"))
    else:
        raise ProtocolError("unsupported collection language")
    return CollectionRequest(
        SnapshotInput(source_root, _string(snapshot["git_head"], "snapshot.git_head"), dirty_value),
        SourceScope(roots, namespace),
        resolver,
    )


def encode_request(request: CollectionRequest) -> bytes:
    resolver: dict[str, RawJson] = {"language": request.resolver.language}
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


def _record_object(raw: object, label: str) -> dict[str, RawJson]:
    value = _json_value(raw)
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _record_string(raw: object, label: str) -> str:
    if not isinstance(raw, str):
        raise ProtocolError(f"{label} must be a string")
    return raw


def _record_strings(raw: object, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ProtocolError(f"{label} must be a string array")
    return tuple(_record_string(item, label) for item in raw)


_RECORD_KEYS = set(RECORD_FIELDS)
_EVIDENCE_KEYS = set(EVIDENCE_FIELDS)


def freeze_data(raw: object, label: str = "data") -> RecordData:
    value = _record_object(raw, label)
    return RecordData(
        tuple((key, freeze_value(item, f"{label}.{key}")) for key, item in sorted(value.items()))
    )


def freeze_value(raw: object, label: str) -> JsonValue:
    if raw is None or isinstance(raw, (str, bool, int, float)):
        return raw
    if isinstance(raw, list):
        return tuple(freeze_value(item, f"{label}[]") for item in raw)
    if isinstance(raw, dict):
        return freeze_data(raw, label)
    raise ValueError(f"{label} is not a JSON value")


def parse_record(raw: object, label: str = "record") -> Record:
    item = _record_object(raw, label)
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
        data=freeze_data(item["data"], f"{label}.data"),
    )


def _position(raw: RawJson, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{label} positions must be integers")
    return raw


def parse_evidence(raw: object, label: str = "evidence") -> Evidence:
    item = _record_object(raw, label)
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
    if isinstance(value, str) and _is_profile(value):
        return value
    raise ProtocolError("unregistered source profile")


def _is_profile(value: str) -> TypeGuard[SourceProfile]:
    return value in get_args(SourceProfile)


def _section_name(value: RawJson) -> SourceSectionName:
    if isinstance(value, str) and _is_section_name(value):
        return value
    raise ProtocolError("unsupported source section")


def _is_section_name(value: str) -> TypeGuard[SourceSectionName]:
    return value in get_args(SourceSectionName)


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
    role = item["role"]
    if role not in ("selected", "resolution"):
        raise ProtocolError("input.role is invalid")
    return ResolutionInput(
        _relative(item["path"], "input.path"),
        _digest(item["digest"], "input.digest"),
        "selected" if role == "selected" else "resolution",
    )


def _target(value: RawJson) -> ImportTarget:
    if not isinstance(value, dict):
        raise ProtocolError("import target must be an object")
    kind = value.get("kind")
    if kind == "local":
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
    if kind == "external":
        item = _object(value, {"kind", "import_id", "package"}, "external target")
        return ExternalPackageTarget(
            _string(item["import_id"], "target.import_id"),
            _string(item["package"], "target.package"),
        )
    if kind == "builtin":
        item = _object(value, {"kind", "import_id", "name"}, "builtin target")
        return BuiltinTarget(
            _string(item["import_id"], "target.import_id"), _string(item["name"], "target.name")
        )
    if kind == "unresolved":
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
            "kind": "local",
            "import_id": target.import_id,
            "module": target.module,
            "file": target.file,
            "runtime_file": target.runtime_file,
            "declaration_file": target.declaration_file,
        }
    if isinstance(target, ExternalPackageTarget):
        return {"kind": "external", "import_id": target.import_id, "package": target.package}
    if isinstance(target, BuiltinTarget):
        return {"kind": "builtin", "import_id": target.import_id, "name": target.name}
    return {
        "kind": "unresolved",
        "import_id": target.import_id,
        "specifier": target.specifier,
        "reason": target.reason,
    }


def _shape(value: RawJson) -> TypeShape:
    if not isinstance(value, dict):
        raise ProtocolError("type shape must be an object")
    kind = value.get("kind")
    text = _record_string(value.get("text"), "type shape.text")
    if kind == "name":
        _object(value, {"kind", "text", "name"}, "type name")
        return TypeName(text, _string(value["name"], "type name.name"))
    if kind == "member":
        _object(value, {"kind", "text", "owner", "member"}, "type member")
        return TypeMember(
            text, _shape(value["owner"]), _string(value["member"], "type member.member")
        )
    if kind == "application":
        _object(value, {"kind", "text", "head", "arguments", "tuple_arguments"}, "type application")
        return TypeApplication(
            text,
            _shape(value["head"]),
            tuple(_shape(item) for item in _array(value["arguments"], "type arguments")),
            _boolean(value["tuple_arguments"], "type tuple arguments"),
        )
    if kind == "union":
        _object(value, {"kind", "text", "left", "right"}, "type union")
        return TypeUnion(text, _shape(value["left"]), _shape(value["right"]))
    if kind == "literal":
        _object(value, {"kind", "text", "literal_kind"}, "type literal")
        try:
            literal = LiteralKind(_string(value["literal_kind"], "literal kind"))
        except ValueError as error:
            raise ProtocolError("invalid literal kind") from error
        return TypeLiteral(text, literal)
    if kind == "unpack":
        _object(value, {"kind", "text", "argument"}, "type unpack")
        return TypeUnpack(text, _shape(value["argument"]))
    if kind == "unresolved":
        _object(value, {"kind", "text", "valid_syntax"}, "unresolved type")
        return UnresolvedType(text, _boolean(value["valid_syntax"], "type valid syntax"))
    raise ProtocolError("invalid type shape kind")


def _shape_payload(shape: TypeShape) -> dict[str, RawJson]:
    base: dict[str, RawJson] = {"text": shape.text}
    if isinstance(shape, TypeName):
        return {**base, "kind": "name", "name": shape.name}
    if isinstance(shape, TypeMember):
        return {
            **base,
            "kind": "member",
            "owner": _shape_payload(shape.owner),
            "member": shape.member,
        }
    if isinstance(shape, TypeApplication):
        return {
            **base,
            "kind": "application",
            "head": _shape_payload(shape.head),
            "arguments": [_shape_payload(item) for item in shape.arguments],
            "tuple_arguments": shape.tuple_arguments,
        }
    if isinstance(shape, TypeUnion):
        return {
            **base,
            "kind": "union",
            "left": _shape_payload(shape.left),
            "right": _shape_payload(shape.right),
        }
    if isinstance(shape, TypeLiteral):
        return {**base, "kind": "literal", "literal_kind": shape.kind.value}
    if isinstance(shape, TypeUnpack):
        return {**base, "kind": "unpack", "argument": _shape_payload(shape.argument)}
    return {**base, "kind": "unresolved", "valid_syntax": shape.valid_syntax}


def _source(value: RawJson) -> SourceInfo:
    item = _object(value, {"git_head", "dirty", "source_digest", "scope"}, "source")
    dirty = item["dirty"]
    if not isinstance(dirty, bool) and dirty != "unknown":
        raise ProtocolError("source.dirty is invalid")
    return SourceInfo(
        _string(item["git_head"], "source.git_head"),
        dirty if isinstance(dirty, bool) else "unknown",
        _digest(item["source_digest"], "source.source_digest"),
        _record_strings(item["scope"], "source.scope"),
    )


def _section(value: RawJson) -> FactSection:
    item = _object(value, {"name", "records"}, "section")
    return FactSection(
        _section_name(item["name"]),
        tuple(parse_record(record) for record in _array(item["records"], "section.records")),
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
        tuple(parse_record(record) for record in _array(item["gaps"], "coverage.gaps")),
    )


def decode_response(payload: bytes) -> CollectionResponse:
    try:
        raw = _object(_decode(payload), {"protocol_version", "facts"}, "response")
        _version(raw["protocol_version"])
        item = _object(
            raw["facts"],
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
            },
            "facts",
        )
        adapter = _object(item["adapter"], {"name", "version", "code_digest"}, "adapter")
        runtime = _object(item["runtime"], {"name", "version"}, "runtime")
        capabilities = _object(
            item["capabilities"], {"sections", "resolution_features"}, "capabilities"
        )
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
            shapes.append((_string(pair["expression"], "type expression"), _shape(pair["shape"])))
        facts = SourceFacts(
            _profile(item["profile"]),
            AnalyzerInfo(
                _string(adapter["name"], "adapter.name"),
                _string(adapter["version"], "adapter.version"),
                _digest(adapter["code_digest"], "adapter.code_digest"),
            ),
            RuntimeInfo(
                _string(runtime["name"], "runtime.name"),
                _string(runtime["version"], "runtime.version"),
            ),
            _source(item["source"]),
            Capabilities(
                tuple(
                    _section_name(section)
                    for section in _array(capabilities["sections"], "capabilities.sections")
                ),
                _record_strings(capabilities["resolution_features"], "resolution_features"),
            ),
            tuple(_input(entry) for entry in _array(item["inputs"], "inputs")),
            tuple(_file(entry) for entry in _array(item["files"], "files")),
            tuple(_target(entry) for entry in _array(item["imports"], "imports")),
            tuple(_section(entry) for entry in _array(item["sections"], "sections")),
            _coverage(item["coverage"]),
            tuple(parse_evidence(entry) for entry in _array(item["evidence"], "evidence")),
            tuple(uncertain),
            tuple(shapes),
            parse_state_data(freeze_data(item["state"])),
            tuple(
                parse_evidence(entry)
                for entry in _array(item["candidate_evidence"], "candidate evidence")
            ),
        )
        validate_source_facts(facts)
        return CollectionResponse(facts)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ProtocolError(str(error)) from error


def encode_response(response: CollectionResponse) -> bytes:
    facts = response.facts
    raw: dict[str, RawJson] = {
        "protocol_version": response.protocol_version,
        "facts": {
            "state": thaw_data(state_data(facts.state)),
            "candidate_evidence": [evidence_payload(entry) for entry in facts.candidate_evidence],
            "profile": facts.profile,
            "adapter": {
                "name": facts.adapter.name,
                "version": facts.adapter.version,
                "code_digest": facts.adapter.code_digest,
            },
            "runtime": {"name": facts.runtime.name, "version": facts.runtime.version},
            "source": {
                "git_head": facts.source.git_head,
                "dirty": facts.source.dirty,
                "source_digest": facts.source.source_digest,
                "scope": list(facts.source.scope),
            },
            "capabilities": {
                "sections": list(facts.capabilities.sections),
                "resolution_features": list(facts.capabilities.resolution_features),
            },
            "inputs": [
                {"path": entry.path, "digest": entry.digest, "role": entry.role}
                for entry in facts.inputs
            ],
            "files": [
                {
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
                for entry in facts.files
            ],
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
        },
    }
    payload = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    decode_response(payload)
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
