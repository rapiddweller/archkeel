# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate JSON field values and encode immutable IR values."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from archkeel.ir.model import JsonValue, Record, RecordData
from archkeel.ir.model import RawJson as RawJson


def _object(raw: object, label: str) -> dict[str, RawJson]:
    if not isinstance(raw, dict) or not all(isinstance(k, str) for k in raw):
        raise ValueError(f"{label} must be an object")
    return raw


def _has_field(item: Mapping[str, RawJson], name: str) -> bool:
    """Apply open field grammar while distinguishing absence from explicit null."""
    return name in item


def _string(raw: object, label: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be a string")
    return raw


def _strings(raw: object, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise ValueError(f"{label} must be a string array")
    return tuple(raw)


def _raw_object(value: dict[str, Any]) -> dict[str, RawJson]:
    return {key: _raw_value(item) for key, item in value.items()}


def _raw_value(value: JsonValue | dict[str, Any] | tuple[Any, ...]) -> RawJson:
    if isinstance(value, RecordData):
        return {key: _raw_value(item) for key, item in value.entries}
    if isinstance(value, tuple):
        return [_raw_value(item) for item in value]
    if isinstance(value, dict):
        return _raw_object(value)
    return value


def value_bytes(value: JsonValue) -> bytes:
    """Canonical JSON bytes for one immutable IR value."""
    return (
        json.dumps(_raw_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def canonical_json_bytes(model: Mapping[str, object]) -> bytes:
    """Serialize the canonical model without time, locale, or filesystem noise."""
    return (
        json.dumps(dict(model), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def decode_json(payload: bytes | str) -> RawJson:
    try:
        value: RawJson = json.loads(
            payload.decode("utf-8") if isinstance(payload, bytes) else payload
        )
        return value
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc


def _exact(value: object, keys: set[str], label: str) -> dict[str, RawJson]:
    result = _object(value, label)
    if set(result) != keys:
        raise ValueError(f"{label} fields mismatch")
    return result


def _nonempty(raw: RawJson, label: str) -> str:
    value = _string(raw, label)
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _count(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _record_payload(value: Record) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result
