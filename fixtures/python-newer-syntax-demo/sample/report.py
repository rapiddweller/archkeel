# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from sample.maintenance import purge


def summarize(rows: list[list[object]]) -> list[bool]:
    # Python 3.12 inlines the list comprehension; the generator keeps its own scope.
    return [any(purge(cell) for cell in row) for row in rows]
