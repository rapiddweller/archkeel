# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python decoded-IR profile: underscore-private imports across package boundaries."""

from typing import Final

from archkeel.ir.model import Record

# AD-43: language boilerplate every module in a namespace carries names no project symbol
# on either side, so a new file's copy of it is not a crossing worth declaring.
_LANGUAGE_BOILERPLATE_IMPORTS: Final = frozenset({("__future__", "annotations")})


def crossing_imports(imports: tuple[Record, ...], *, private: bool) -> tuple[Record, ...]:
    """Return cross-package symbol imports, optionally limited to private symbols."""
    result: list[Record] = []
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        target_module = item.data.get("target_module")
        if not isinstance(symbol, str) or not symbol:
            continue
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            continue
        if private and not symbol.startswith("_"):
            continue
        if (target_module, symbol) in _LANGUAGE_BOILERPLATE_IMPORTS:
            continue
        result.append(item)
    return tuple(result)
