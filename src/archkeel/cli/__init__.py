# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command-line shell of Archkeel. The Rust core decides each run (AD-432)."""

from __future__ import annotations

import io
import os
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """The entry point of the `archkeel` command: run the arguments and return the exit code."""

    if (
        sys.platform == "win32"
        and isinstance(sys.stdout, io.TextIOWrapper)
        and not sys.stdout.isatty()
        and "PYTHONIOENCODING" not in os.environ
    ):
        sys.stdout.reconfigure(encoding="utf-8")

    from .core_only import run

    return run(list(sys.argv[1:] if argv is None else argv))
