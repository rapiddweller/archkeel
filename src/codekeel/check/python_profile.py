# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python decoded-IR profile: underscore-private imports across package boundaries."""

from codekeel.ir.model import Record


def crossing_imports(imports: tuple[Record, ...], *, private: bool) -> tuple[Record, ...]:
    """Return cross-package symbol imports, optionally limited to private symbols."""
    result: list[Record] = []
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        if not isinstance(symbol, str) or not symbol:
            continue
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            continue
        if private and not symbol.startswith("_"):
            continue
        result.append(item)
    return tuple(result)
