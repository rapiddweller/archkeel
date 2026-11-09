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
# on pydantic: 2 817 entries, 0.98 MB).
REFERENCE_CONTEXT_CACHE_SIZE = 32768
# An excerpt is a source line without a length limit, so the cache keeps only short inputs.
# Measured distinct excerpt lengths: fastapi 99.9th percentile 91, maximum 111; pydantic 147 and
# 165. A longer excerpt or expression is computed again at each call and is never pinned.
# The bound of the cache is 32 768 entries of at most 2 x 256 characters: about 23 MiB.
REFERENCE_CONTEXT_CACHE_MAX_CHARS = 256


class _Uncacheable(Exception):
    """Carry a verdict that depends on the call depth, so that the cache never keeps it.

    The verdict is the one argument: an exception is never stored by `lru_cache`.
    """


def source_reference_context(
    excerpt: str, column: int, expression: str
) -> SourceReferenceContext | None:
    """Return a source context only when the bounded syntax anchors the expression.

    The result is a pure function of the three arguments and is immutable: an enum or None.
    The parse tree stays inside the call, so the cache never shares a mutable object.
    A short input has its verdict remembered. A long input, and a verdict that came from a
    RecursionError (it depends on the depth of the caller), are computed at each call.
    """
    if (
        len(excerpt) > REFERENCE_CONTEXT_CACHE_MAX_CHARS
        or len(expression) > REFERENCE_CONTEXT_CACHE_MAX_CHARS
    ):
        return _context(excerpt, column, expression)[0]
    try:
        return _remembered_context(excerpt, column, expression)
    except _Uncacheable as uncacheable:
        verdict: SourceReferenceContext | None = uncacheable.args[0]
        return verdict


@lru_cache(maxsize=REFERENCE_CONTEXT_CACHE_SIZE)
def _remembered_context(
    excerpt: str, column: int, expression: str
) -> SourceReferenceContext | None:
    verdict, cacheable = _context(excerpt, column, expression)
    if not cacheable:
        raise _Uncacheable(verdict)
    return verdict


def _context(
    excerpt: str, column: int, expression: str
) -> tuple[SourceReferenceContext | None, bool]:
    """Return the verdict and whether it is the same at any call depth."""
    tree, cacheable = _reference_excerpt_tree(excerpt)
    if tree is None:
        return None, cacheable
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name | ast.Attribute)
        and node.col_offset == column
        and ast.unparse(node) == expression
    ]
    if not matches:
        return None, cacheable
    annotations = {
        id(node) for annotation in _annotation_roots(tree) for node in ast.walk(annotation)
    }
    return (
        SourceReferenceContext.ANNOTATION
        if any(id(node) in annotations for node in matches)
        else SourceReferenceContext.VALUE
    ), cacheable


def _reference_excerpt_tree(excerpt: str) -> tuple[ast.Module | None, bool]:
    """Parse the excerpt; the flag is False when a RecursionError changed the path."""
    cacheable = True
    try:
        return ast.parse(excerpt), cacheable
    except RecursionError:
        cacheable = False
    except (IndentationError, SyntaxError, ValueError):
        pass
    parsed = parse_numeric_evidence_excerpt(excerpt)
    if parsed is not None:
        return ast.Module(body=list(parsed[0]), type_ignores=[]), cacheable
    stripped: str = excerpt.rstrip()
    if not stripped.endswith(("(", "[", "{")):
        return None, cacheable
    closing = {"(": ")", "[": "]", "{": "}"}[stripped[-1]]
    for count in range(1, 9):
        candidate = f"{excerpt}None{closing * count}"
        try:
            return ast.parse(candidate), cacheable
        except RecursionError:
            cacheable = False
        except (IndentationError, SyntaxError, ValueError):
            pass
        parsed = parse_numeric_evidence_excerpt(candidate)
        if parsed is not None:
            return ast.Module(body=list(parsed[0]), type_ignores=[]), cacheable
    return None, cacheable


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
