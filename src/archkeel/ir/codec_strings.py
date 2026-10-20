# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Lossless JSON string interning shared by the IR wire encodings."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable

from archkeel.ir.model import RawJson

_REFERENCE = re.compile(r"^\$\d+$")
_ESCAPED_REFERENCE = re.compile(r"^\$\$+\d+$")
_MISSING = "$m"


def intern_strings(
    value: RawJson,
    *,
    profitable: Callable[[str, int], bool],
    missing_value: RawJson | None = None,
    escape_reserved: Callable[[str], bool] | None = None,
) -> tuple[RawJson, list[str]]:
    """Return a lossless JSON tree and its sorted string table."""
    counts: Counter[str] = Counter()

    def count(item: RawJson) -> None:
        if item is missing_value and missing_value is not None:
            return
        if isinstance(item, str):
            counts[item] += 1
        elif isinstance(item, list):
            for child in item:
                count(child)
        elif isinstance(item, dict):
            for child in item.values():
                count(child)

    count(value)
    table = sorted(text for text, occurrences in counts.items() if profitable(text, occurrences))
    indexes = {text: index for index, text in enumerate(table)}

    def encode(item: RawJson) -> RawJson:
        if item is missing_value and missing_value is not None:
            return _MISSING
        if isinstance(item, str):
            if item in indexes:
                return f"${indexes[item]}"
            if escape_reserved(item) if escape_reserved is not None else item.startswith("$"):
                return f"${item}"
        if isinstance(item, list):
            return [encode(child) for child in item]
        if isinstance(item, dict):
            return {key: encode(child) for key, child in item.items()}
        return item

    return encode(value), table


def expand_strings(
    value: RawJson, table: list[str], *, missing_value: RawJson | None = None
) -> RawJson:
    """Expand interned strings, rejecting malformed or out-of-range references."""

    def decode(item: RawJson) -> RawJson:
        if isinstance(item, str):
            if item == _MISSING:
                return _MISSING if missing_value is None else missing_value
            if _REFERENCE.fullmatch(item):
                index = int(item[1:])
                if index >= len(table):
                    raise ValueError("string table reference is out of range")
                return table[index]
            if item.startswith("$$"):
                return item[1:]
        if isinstance(item, list):
            return [decode(child) for child in item]
        if isinstance(item, dict):
            return {key: decode(child) for key, child in item.items()}
        return item

    return decode(value)


def profitable_string(text: str, occurrences: int) -> bool:
    """Intern when the JSON byte savings exceed table and reference overhead."""
    quoted = len(json.dumps(text, ensure_ascii=False).encode("utf-8"))
    reference_bytes = len(str(occurrences - 1)) + 3
    table_bytes = quoted + 2
    return occurrences >= 2 and occurrences * (quoted - reference_bytes) > table_bytes


def observation_profitable(text: str, occurrences: int) -> bool:
    """Keep the historical report encoding policy byte-for-byte stable."""
    return (
        text == "$$m"
        or occurrences >= 2
        and len(text) >= 8
        and ((occurrences - 1) * len(text) - occurrences * 8 > 100)
    )


def observation_escaped(text: str) -> bool:
    """Match the historical observation sentinel and reference escaping."""
    return (
        text in {"$m", "$$m"}
        or bool(_REFERENCE.fullmatch(text))
        or bool(_ESCAPED_REFERENCE.fullmatch(text))
    )
