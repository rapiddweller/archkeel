# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Lossless JSON string interning shared by the IR wire encodings."""

from __future__ import annotations

import json
import re
from collections import Counter

from archkeel.ir.facts import RawJson
from archkeel.ir.facts import StringTablePolicy as StringTablePolicy
from archkeel.ir.facts import _ReservedString as _ReservedString

_REFERENCE = r"^\$\d+$"
_ESCAPED_REFERENCE = r"^\$\$+\d+$"
_MISSING = "$m"


def intern_strings(
    value: object,
    *,
    policy: StringTablePolicy,
    missing_value: object | None = None,
) -> tuple[RawJson, list[str]]:
    """Return a JSON tree with profitable repeated strings represented by a sorted table."""
    counts: Counter[str] = Counter()

    def count(item: object) -> None:
        if missing_value is not None and item is missing_value:
            return
        if isinstance(item, str):
            counts[item] += 1
        elif isinstance(item, list):
            for child in item:
                count(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("JSON fields must be strings")
                count(child)
        elif not isinstance(item, (bool, int, float)) and item is not None:
            raise ValueError("value is not JSON")

    count(value)
    table = sorted(
        text for text, occurrences in counts.items() if _profitable(policy, text, occurrences)
    )
    indexes = {text: index for index, text in enumerate(table)}

    def encode(item: object) -> RawJson:
        if missing_value is not None and item is missing_value:
            return _MISSING
        if isinstance(item, str):
            if item in indexes:
                return f"${indexes[item]}"
            if _reserved_reference(item, policy):
                return f"${item}"
            return item
        if isinstance(item, list):
            return [encode(child) for child in item]
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON fields must be strings")
            return {key: encode(child) for key, child in item.items()}
        if item is None or isinstance(item, bool | int | float):
            return item
        raise ValueError("value is not JSON")

    return encode(value), table


def expand_strings(value: RawJson, table: list[str]) -> RawJson:
    """Expand references, rejecting malformed or out-of-range string-table indexes."""

    def decode(item: RawJson) -> RawJson:
        if isinstance(item, str):
            if item == _MISSING:
                return _MISSING
            if re.fullmatch(_REFERENCE, item) is not None:
                index = int(item[1:])
                if index >= len(table):
                    raise ValueError("string table reference is out of range")
                return table[index]
            if item[:2] == _ReservedString.DOUBLE_DOLLAR:
                return item[1:]
        if isinstance(item, list):
            return [decode(child) for child in item]
        if isinstance(item, dict):
            return {key: decode(child) for key, child in item.items()}
        return item

    return decode(value)


def profitable_string(text: str, occurrences: int) -> bool:
    """Measure repeated JSON string savings against table and reference overhead."""
    serialized: str = json.dumps(text, ensure_ascii=False)
    quoted: int = len(serialized.encode("utf-8"))
    reference_bytes = len(str(occurrences - 1)) + 3
    table_bytes = quoted + 2
    return occurrences >= 2 and occurrences * (quoted - reference_bytes) > table_bytes


def observation_profitable(text: str, occurrences: int) -> bool:
    """Retain the historical report string interning policy byte-for-byte."""
    return text == "$$m" or (
        occurrences >= 2
        and len(text) >= 8
        and (occurrences - 1) * len(text) - occurrences * 8 > 100
    )


def observation_escaped(text: str) -> bool:
    """Escape the historical missing marker and string-reference spellings."""
    return (
        text in {_ReservedString.MISSING, _ReservedString.DOUBLE_MISSING}
        or re.fullmatch(_REFERENCE, text) is not None
        or re.fullmatch(_ESCAPED_REFERENCE, text) is not None
    )


def _profitable(policy: StringTablePolicy, text: str, occurrences: int) -> bool:
    if policy is StringTablePolicy.OBSERVATION:
        return observation_profitable(text, occurrences)
    return profitable_string(text, occurrences)


def _reserved_reference(text: str, policy: StringTablePolicy) -> bool:
    if policy is StringTablePolicy.OBSERVATION:
        return observation_escaped(text)
    return text[:1] == _ReservedString.DOLLAR
