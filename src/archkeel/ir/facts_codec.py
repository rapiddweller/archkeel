# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Pure strict validation of the language-process wire contract."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Literal, TypeAlias

from .facts import (
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    Evidence,
    EvidenceClass,
    JsonValue,
    Record,
    RecordData,
)
from .protocol import (
    PROTOCOL_VERSION,
    CollectionRequest,
    DartSettings,
    PythonSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
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
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, RawJson] = {}
        for key, item in value.items():
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
    if not PurePosixPath(source_root).is_absolute() or "\\" in source_root:
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
        tuple((key, freeze_value(item, f"{label}.{key}")) for key, item in value.items())
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
