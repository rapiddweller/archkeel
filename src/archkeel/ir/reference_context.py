# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Classify a reference occurrence from its bounded source excerpt (AD-338).

The host checks the excerpt of every reference again in each validation and in each saved-model
read. The check is pure, so one verdict per (excerpt, column, expression) serves all of them.
The collector keeps its own check; the host never trusts it.
"""

from __future__ import annotations

import ast
import sys
from functools import lru_cache

from .facts import SourceReferenceContext
from .source_proofs import parse_numeric_evidence_excerpt

# Measured distinct inputs of one run: 309 (demo), 1 125 (fastapi), 2 817 (pydantic), 26 472
# (a private repository). The size covers the largest. One entry costs about 350 bytes (measured
# on pydantic: 2 817 entries, 0.98 MB), so a full cache holds about 11 MiB.
REFERENCE_CONTEXT_CACHE_SIZE = 32768


@lru_cache(maxsize=REFERENCE_CONTEXT_CACHE_SIZE)
def source_reference_context(
    excerpt: str, column: int, expression: str
) -> SourceReferenceContext | None:
    """Return a source context only when the bounded syntax anchors the expression.

    The result is a pure function of the three arguments and is immutable: an enum or None.
    The parse tree stays inside the call, so the cache never shares a mutable object.
    """
    tree = _reference_excerpt_tree(excerpt)
    if tree is None:
        return None
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name | ast.Attribute)
        and node.col_offset == column
        and ast.unparse(node) == expression
    ]
    if not matches:
        return None
    annotations = {
        id(node) for annotation in _annotation_roots(tree) for node in ast.walk(annotation)
    }
    return (
        SourceReferenceContext.ANNOTATION
        if any(id(node) in annotations for node in matches)
        else SourceReferenceContext.VALUE
    )


def _reference_excerpt_tree(excerpt: str) -> ast.Module | None:
    try:
        return ast.parse(excerpt)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        parsed = parse_numeric_evidence_excerpt(excerpt)
        if parsed is not None:
            return ast.Module(body=list(parsed[0]), type_ignores=[])
    stripped: str = excerpt.rstrip()
    if not stripped.endswith(("(", "[", "{")):
        return None
    closing = {"(": ")", "[": "]", "{": "}"}[stripped[-1]]
    for count in range(1, 9):
        candidate = f"{excerpt}None{closing * count}"
        try:
            return ast.parse(candidate)
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            parsed = parse_numeric_evidence_excerpt(candidate)
            if parsed is not None:
                return ast.Module(body=list(parsed[0]), type_ignores=[])
    return None


def _annotation_roots(tree: ast.Module) -> tuple[ast.expr, ...]:
    roots: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            roots.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns:
            roots.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            roots.append(node.annotation)
        elif sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias):
            roots.append(node.value)
    return tuple(roots)
