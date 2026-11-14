# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command-line shell of Archkeel. The Rust core decides each run (AD-432)."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    from .core_only import run

    return run(list(sys.argv[1:] if argv is None else argv))
