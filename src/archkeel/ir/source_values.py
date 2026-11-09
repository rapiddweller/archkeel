# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read typed text and record arrays from recorded source facts; fail on any other shape."""

from __future__ import annotations

from archkeel.ir.model import JsonValue, RecordData


def optional_text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("source graph expected text")


def vocabulary_text(value: JsonValue, *, default: str = "") -> str:
    found = optional_text(value)
    return default if found is None else found


def text_array(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise ValueError("source graph expected text array")
    return tuple(item for item in value if isinstance(item, str))


def record_array(value: JsonValue) -> tuple[RecordData, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, RecordData) for item in value):
        raise ValueError("source graph expected record array")
    return tuple(item for item in value if isinstance(item, RecordData))
