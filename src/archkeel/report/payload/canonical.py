# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical bytes and the string table of the payload (AD-361).

Canonical bytes: keys in schema order; no whitespace; UTF-8; a string escapes only `"`, `\\` and
the control characters U+0000 to U+001F, as `\\b \\f \\n \\r \\t` or `\\u00xx` with lowercase hex;
no other escape and no Unicode normalisation; integers only in the tables; one trailing newline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from archkeel.report.payload.codes import ABSENT

STRING_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "nodes": ("key", "name", "path"),
    "measures": ("budget_source", "baseline_source"),
    "units": ("name", "decl"),
    "variants": ("name",),
    "edges": ("rationale",),
    "crossings": ("name",),
    "permissions": ("rule",),
    "violations": ("kind", "source_module", "target_module", "symbol", "path"),
    "unknowns": ("kind", "rule", "detail"),
    "carriers": ("name",),
}
STRING_LISTS = ("violation_rules", "violation_subjects", "violation_evidence")

Table = dict[str, list[object]]


def intern_strings(tables: Mapping[str, Table], lists: dict[str, list[object]]) -> list[str]:
    """Replace the string cells of the tables and lists with ids into one sorted string table."""
    found: set[str] = set()
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            found.update(v for v in tables[name][column] if isinstance(v, str))
    for name in STRING_LISTS:
        found.update(v for v in lists[name] if isinstance(v, str))
    strings = sorted(found)
    index = {value: position for position, value in enumerate(strings)}
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            tables[name][column] = [
                index[v] if isinstance(v, str) else ABSENT for v in tables[name][column]
            ]
    for name in STRING_LISTS:
        lists[name] = [index[v] for v in lists[name] if isinstance(v, str)]
    return strings


def encode(payload: Mapping[str, object]) -> bytes:
    """Return the canonical bytes of one payload."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8") + b"\n"
