# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Declared repository paths of a contract: checked without filesystem access."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


def contract_relative_path(value: str) -> PurePosixPath | None:
    """Check a declared repository path without filesystem access."""
    relative = PurePosixPath(value)
    if relative.is_absolute() or re.search(r"(?:^|/)\.\.(?:/|$)|\\", value):
        return None
    return relative


def validate_module_target_path(path: str) -> None:
    relative = contract_relative_path(path)
    if (
        not path
        or relative is None
        or str(relative) != path
        or re.match(r"^[A-Za-z]:", path) is not None
        or re.search(r"\x00", path) is not None
        or re.fullmatch(r"\.(?:py|dart|tsx?|mts|cts|jsx?|mjs|cjs)", relative.suffix) is None
    ):
        raise ValueError("path must be a repository-relative source path")
