# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Symbol import crossings across package boundaries."""

from archkeel.ir.facts import SourceNameVisibility
from archkeel.ir.model import Record
from archkeel.ir.source_records import source_name_visibility as _source_name_visibility


def is_crossing_import(
    symbol: str | None,
    source_package: str,
    target_package: str,
    *,
    private: bool,
) -> bool:
    """Identify project symbol crossings."""
    if not symbol:
        return False
    return source_package != target_package and (
        not private or _source_name_visibility(symbol) is SourceNameVisibility.PRIVATE
    )


def crossing_imports(imports: tuple[Record, ...], *, private: bool) -> tuple[Record, ...]:
    """Return cross-package symbol imports, optionally limited to private symbols."""
    result: list[Record] = []
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        if symbol is not None and not isinstance(symbol, str):
            continue
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if is_crossing_import(symbol, source, target, private=private):
            result.append(item)
    return tuple(result)
