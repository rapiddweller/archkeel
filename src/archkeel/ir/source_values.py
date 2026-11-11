# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read typed text and record arrays from recorded source facts; fail on any other shape."""

from __future__ import annotations

from archkeel.ir.architecture_graph import Visibility, VisibilityBasis, VisibilityKind
from archkeel.ir.model import JsonValue, RecordData


def optional_text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("source graph expected text")


def required_text(value: JsonValue, label: str) -> str:
    """A field that every record of its kind has; a copy without it fails (#949 item 3)."""
    if isinstance(value, str):
        return value
    raise ValueError(f"source graph needs {label}")


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


def visibility_detail(value: JsonValue, spelling: str | None = None) -> Visibility:
    if value is None:
        return Visibility(spelling=spelling)
    if not isinstance(value, RecordData):
        raise ValueError("source graph expected visibility record")
    return Visibility(
        VisibilityKind(vocabulary_text(value.get("kind"), default=VisibilityKind.UNKNOWN)),
        VisibilityBasis(vocabulary_text(value.get("basis"), default=VisibilityBasis.UNKNOWN)),
        optional_text(value.get("spelling")),
    )
