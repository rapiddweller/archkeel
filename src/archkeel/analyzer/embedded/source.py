# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Parsed-module primitives shared by the scanner and its context collector."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .records import RawEvidence, stable_id


def location(node: ast.AST) -> tuple[int, int, int]:
    if not isinstance(node, ast.stmt | ast.expr | ast.excepthandler | ast.arg | ast.keyword):
        return 1, 1, 0
    line = max(node.lineno, 1)
    return line, node.end_lineno or line, node.col_offset


@dataclass(frozen=True)
class AliasBinding:
    target: str
    kind: str
    imported_name: str | None = None


@dataclass
class ParsedModule:
    path: Path
    rel_path: str
    module: str
    package: str
    source: str
    source_bytes: bytes
    lines: list[str]
    tree: ast.Module
    aliases: dict[str, AliasBinding] = field(default_factory=dict)
    all_exports: set[str] = field(default_factory=set)


def _excerpt(module: ParsedModule, node: ast.AST) -> str:
    start, _, _ = location(node)
    return module.lines[start - 1].rstrip() if start <= len(module.lines) else ""


def add_evidence(evidence: dict[str, RawEvidence], module: ParsedModule, node: ast.AST) -> str:
    line, end_line, column = location(node)
    # One source location is one evidence owner even when several observations
    # (for example a call and a dynamic-typing signal) refer to it.
    evidence_id = stable_id("EVD", module.rel_path, line, end_line, column)
    evidence[evidence_id] = {
        "id": evidence_id,
        "file": module.rel_path,
        "line": line,
        "end_line": end_line,
        "column": column,
        "excerpt": _excerpt(module, node),
    }
    return evidence_id


def annotation_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        try:
            names.append(ast.unparse(target))
        except Exception:
            continue
    return sorted(names)
