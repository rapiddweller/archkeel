# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-condition classes of the AD-402 unproved inventory (AD-414)."""

from __future__ import annotations


def condition_class(site: dict) -> str:
    if site["call"] == "PyErr_NoMemory":
        return "resource-allocation"
    if site["file"] == "Python/ast.c":
        return "ast-validation"
    if site["file"] == "Grammar/python.gram":
        return "grammar"
    return site["file"]
