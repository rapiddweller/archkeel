# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python decoded-IR profile: underscore-private imports across package boundaries."""

from typing import Final

from archkeel.ir.model import JsonValue, Record

# AD-43: language boilerplate every module in a namespace carries names no project symbol
# on either side, so a new file's copy of it is not a crossing worth declaring.
_LANGUAGE_BOILERPLATE_IMPORTS: Final = frozenset({("__future__", "annotations")})


def is_crossing_import(
    symbol: str | None,
    source_package: str,
    target_package: str,
    target_module: JsonValue,
    *,
    private: bool,
) -> bool:
    """Identify project symbol crossings, excluding language boilerplate."""
    if not symbol:
        return False
    return (
        source_package != target_package
        and (not private or symbol.startswith("_"))
        and (target_module, symbol) not in _LANGUAGE_BOILERPLATE_IMPORTS
    )


def crossing_imports(imports: tuple[Record, ...], *, private: bool) -> tuple[Record, ...]:
    """Return cross-package symbol imports, optionally limited to private symbols."""
    result: list[Record] = []
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        target_module = item.data.get("target_module")
        if symbol is not None and not isinstance(symbol, str):
            continue
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if is_crossing_import(symbol, source, target, target_module, private=private):
            result.append(item)
    return tuple(result)
