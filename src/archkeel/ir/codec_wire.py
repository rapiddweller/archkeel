# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate JSON field values and encode immutable IR values."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from io import BytesIO
from typing import Any, BinaryIO

from archkeel.ir.facts import EVIDENCE_FIELDS, RECORD_FIELDS
from archkeel.ir.model import JsonValue, RecordData
from archkeel.ir.model import RawJson as RawJson


def _object(raw: object, label: str) -> dict[str, RawJson]:
    if not isinstance(raw, dict) or not all(isinstance(k, str) for k in raw):
        raise ValueError(f"{label} must be an object")
    return raw


def _has_field(item: Iterable[str], name: str) -> bool:
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


_COMPACT: tuple[str, str] = (",", ":")
_LIST_PIECE = 4096
_NESTING = 4


def _dumps(value: object, separators: tuple[str, str]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=separators)


def _pieces(value: object, separators: tuple[str, str], depth: int = 0) -> Iterator[str]:
    """Yield texts that join to `json.dumps(value, sort_keys=True, ensure_ascii=False)`."""
    item_separator, key_separator = separators
    if (
        isinstance(value, dict)
        and value
        and depth < _NESTING
        and all(isinstance(key, str) for key in value)
    ):
        yield "{"
        for position, key in enumerate(sorted(value)):
            yield (item_separator if position else "") + _dumps(key, separators) + key_separator
            yield from _pieces(value[key], separators, depth + 1)
        yield "}"
    elif isinstance(value, list | tuple) and len(value) > _LIST_PIECE:
        yield "["
        for start in range(0, len(value), _LIST_PIECE):
            piece = _dumps(value[start : start + _LIST_PIECE], separators)
            yield (item_separator if start else "") + piece[1:-1]
        yield "]"
    else:
        yield _dumps(value, separators)


def write_json(
    out: BinaryIO,
    value: Mapping[str, object] | Sequence[object],
    *,
    separators: tuple[str, str] = _COMPACT,
    html_safe: bool = False,
) -> None:
    """Write `json.dumps(value, sort_keys=True, ensure_ascii=False)` to `out` as UTF-8 (AD-324).

    The text is made in pieces. A report of 50 MB as one text holds two bytes for each character,
    and the usual `+ "\\n"` and `.encode()` copy it twice. `html_safe` writes `<` as `\\u003c`.
    """
    for piece in _pieces(value, separators):
        out.write((piece.replace("<", "\\u003c") if html_safe else piece).encode("utf-8"))


def json_bytes(
    value: Mapping[str, object] | Sequence[object],
    *,
    separators: tuple[str, str] = _COMPACT,
    tail: bytes = b"",
) -> bytes:
    """Return the JSON of `value` with sorted keys as UTF-8, then `tail`."""
    out = BytesIO()
    write_json(out, value, separators=separators)
    out.write(tail)
    return out.getvalue()


def canonical_json_bytes(model: Mapping[str, object]) -> bytes:
    """Serialize the canonical model without time, locale, or filesystem noise."""
    return json_bytes(dict(model), tail=b"\n")


def json_arrays(model: dict[str, object]) -> dict[str, object]:
    """Turn each tuple of a built model into a list in place; a copy would double its memory."""
    pending: list[object] = [model]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, tuple):
                    item = node[key] = list(item)
                if isinstance(item, dict | list):
                    pending.append(item)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, tuple):
                    item = node[index] = list(item)
                if isinstance(item, dict | list):
                    pending.append(item)
    return model


def section_rows(
    section: str, raw_items: RawJson, missing: RawJson
) -> tuple[list[str], list[list[RawJson]]]:
    """Columnize one record section: its sorted data fields and one row for each record.

    A caller that passes the only reference to `raw_items` frees the raw records on return.
    """
    if not isinstance(raw_items, list):
        raise ValueError(f"{section} must be an array")
    items = [_object(entry, f"{section}[]") for entry in raw_items]
    data_fields = sorted({key for item in items for key in _object(item["data"], "data")})
    return data_fields, [
        [
            *(item[field] for field in RECORD_FIELDS[:-1]),
            [_object(item["data"], "data").get(field, missing) for field in data_fields],
        ]
        for item in items
    ]


def evidence_rows(raw_evidence: RawJson) -> list[list[RawJson]]:
    if not isinstance(raw_evidence, list):
        raise ValueError("evidence must be an array")
    items = [_object(entry, "evidence[]") for entry in raw_evidence]
    return [[item[field] for field in EVIDENCE_FIELDS] for item in items]


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
