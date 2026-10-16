# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Own the direct-start protocol shared by language collector entry points."""

from enum import Enum


class _EntryMode(Enum):
    MAIN = "__main__"


def is_direct_entrypoint(module_name: str) -> bool:
    """Classify one incoming module name without invoking code or accessing streams."""
    try:
        mode = _EntryMode(module_name)
    except ValueError:
        return False
    return mode is _EntryMode.MAIN
