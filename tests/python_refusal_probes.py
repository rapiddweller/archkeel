# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The compiler of the running interpreter, as the judge of the native Python refusals."""

from __future__ import annotations


def compiler_refuses(source: str | bytes) -> bool:
    try:
        compile(source, "probe.py", "exec", dont_inherit=True)
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return True
    return False
