# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the compiler options of a tsconfig that the resolver and the parser take as typed input.

`config.py` calls these on the compiler options of one layer: the `lib` list as standard libraries
(AD-261) and the `typeRoots` list as a flag for a project type root (AD-354).
"""

from __future__ import annotations

from typing import Final

from .standard_libs import StandardLibrary

_INSTALLED: Final = "node_modules"


def read_libraries(raw: dict[str, object]) -> tuple[tuple[StandardLibrary, ...] | None, bool]:
    value = raw.get("lib")
    if value is None:
        return None, False
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        return (), True
    libraries: list[StandardLibrary] = []
    unsupported = False
    for name in value:
        try:
            libraries.append(StandardLibrary(name.lower()))
        except ValueError:
            unsupported = True
    return tuple(dict.fromkeys(libraries)), unsupported


def project_type_roots(raw: dict[str, object]) -> bool:
    """A `typeRoots` entry without `node_modules` in it may name a project directory (AD-354).
    The check is lexical, so it errs on the side of a concern."""
    roots = raw.get("typeRoots")
    return isinstance(roots, list) and any(
        isinstance(root, str) and _INSTALLED not in root for root in roots
    )
