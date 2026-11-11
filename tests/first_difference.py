# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare two large texts and fail with the first different slice only.

A plain `assert` of two replies makes pytest build a diff of several MB, and that takes minutes.
"""

from __future__ import annotations

import os

import pytest


def same(found: str, expected: str, label: object) -> None:
    """Fail with 80 characters on each side of the first difference."""
    if found != expected:
        at = len(os.path.commonprefix([found, expected]))
        start = max(at - 80, 0)
        pytest.fail(
            f"{label}: at {at} native {found[start : at + 80]!r} "
            f"python {expected[start : at + 80]!r}"
        )
