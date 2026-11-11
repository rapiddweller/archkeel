# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical bytes and the table invariants of the payload (AD-361).

Canonical bytes: keys in schema order, no whitespace, UTF-8, JSON escapes only where JSON
requires them, integers only in the tables, one trailing newline. The schema cannot say that
columns have equal length or that ids are in range, so `check_tables` asserts both.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from archkeel.report.payload.codes import ABSENT, LEVEL, code

STRING_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "nodes": ("key", "name", "path"),
    "measures": ("budget_source", "baseline_source"),
    "units": ("name", "decl"),
    "variants": ("name",),
    "edges": ("rationale",),
    "crossings": ("name",),
    "carriers": ("name",),
}
# (table, column) -> the table that the id points into, and whether -1 (absent) is allowed.
_REFERENCES: Mapping[tuple[str, str], tuple[str, bool]] = {
    ("nodes", "parent"): ("nodes", True),
    ("nodes", "package"): ("nodes", True),
    ("measures", "node"): ("nodes", False),
    ("units", "module"): ("nodes", False),
    ("units", "parent"): ("units", True),
    ("variants", "unit"): ("units", False),
    ("edges", "from"): ("nodes", False),
    ("edges", "to"): ("nodes", False),
    ("crossings", "edge"): ("module_edges", False),
    ("crossings", "unit"): ("units", True),
    ("findings", "subject"): ("nodes", False),
    ("carriers", "finding"): ("findings", False),
    ("carriers", "unit"): ("units", True),
}

Table = dict[str, list[object]]


def intern_strings(tables: Mapping[str, Table]) -> list[str]:
    """Replace the string cells of the tables with ids into one sorted string table."""
    found: set[str] = set()
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            found.update(v for v in tables[name][column] if isinstance(v, str))
    strings = sorted(found)
    index = {value: position for position, value in enumerate(strings)}
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            tables[name][column] = [
                index[v] if isinstance(v, str) else ABSENT for v in tables[name][column]
            ]
    return strings


def _length(table: Mapping[str, Sequence[object]], name: str) -> int:
    lengths = {len(column) for column in table.values()}
    if len(lengths) > 1:
        raise ValueError(f"the columns of table {name} have different lengths")
    return lengths.pop() if lengths else 0


def check_tables(payload: Mapping[str, object]) -> None:
    """Raise ValueError when a column length differs or an id is out of range."""
    sizes: dict[str, int] = {}
    tables: dict[str, Mapping[str, Sequence[object]]] = {}
    for name in (
        "nodes",
        "measures",
        "units",
        "variants",
        "edges",
        "crossings",
        "findings",
        "carriers",
    ):
        table = payload[name]
        if not isinstance(table, dict):
            raise ValueError(f"table {name} is missing")
        tables[name] = table
        sizes[name] = _length(table, name)
    strings = payload["strings"]
    sizes["strings"] = len(strings) if isinstance(strings, list) else 0
    sizes["module_edges"] = sum(
        1 for level in tables["edges"]["level"] if level == code(LEVEL, "module")
    )
    for (name, column), (target, optional) in _REFERENCES.items():
        _check_ids(tables[name][column], sizes[target], optional, f"{name}.{column}")
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            _check_ids(tables[name][column], sizes["strings"], True, f"{name}.{column}")
    via = payload["via"]
    via_end = [v for v in tables["edges"]["via_end"] if isinstance(v, int)]
    if (
        not isinstance(via, list)
        or via_end != sorted(via_end)
        or (via_end and via_end[-1] != len(via))
    ):
        raise ValueError("edges.via_end does not end at the length of via")
    _check_ids(via, sizes["module_edges"], False, "via")


def _check_ids(values: Sequence[object], size: int, optional: bool, where: str) -> None:
    low = ABSENT if optional else 0
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value < low or value >= size:
            raise ValueError(f"{where} holds {value!r}, outside 0..{size - 1}")


def encode(payload: Mapping[str, object]) -> bytes:
    """Return the canonical bytes of one payload."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode("utf-8")
