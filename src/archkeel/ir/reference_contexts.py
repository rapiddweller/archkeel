# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check that a saved reference record agrees with the bounded source text of its evidence.

`validate_reference_contexts` parses each excerpt for a reference record. One run of it keeps a
memo of the verdicts, so an excerpt, column and expression that repeat parse once. The memo lives
in that call and holds only `SourceReferenceContext` values, which are immutable.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Mapping

from .facts import Evidence, Record, SourceProfile, SourceReferenceContext
from .source_proofs import parse_numeric_evidence_excerpt

ContextMemo = dict[tuple[str, int, str], SourceReferenceContext | None]


def _reference_annotation_excerpt(
    reference: Record, evidence: Evidence, memo: ContextMemo | None = None
) -> bool | None:
    """Classify an anchored occurrence; return None when its bounded excerpt is incomplete."""
    expression = reference.data.get("expression")
    if not isinstance(expression, str):
        return None
    key = (evidence.excerpt, evidence.column, expression)
    if memo is not None and key in memo:
        context = memo[key]
    else:
        context = source_reference_context(*key)
        if memo is not None:
            memo[key] = context
    if context is SourceReferenceContext.ANNOTATION:
        return True
    if context is SourceReferenceContext.VALUE:
        return False
    return None


def source_reference_context(
    excerpt: str, column: int, expression: str
) -> SourceReferenceContext | None:
    """Return a source context only when the bounded syntax anchors the expression."""
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


def _validate_reference_contexts(
    records: Iterable[Record], evidence: Mapping[str, Evidence], profile: SourceProfile
) -> None:
    if profile is not SourceProfile.PYTHON:
        return
    memo: ContextMemo = {}
    for record in records:
        if record.kind not in {"value_reference", "attribute_reference"}:
            continue
        if record.data.get("reference_context") == SourceReferenceContext.UNKNOWN:
            continue
        contexts = [
            _reference_annotation_excerpt(record, evidence[item], memo)
            for item in record.evidence_ids
            if item in evidence
        ]
        if record.data.get("reference_context") == SourceReferenceContext.ANNOTATION:
            if False in contexts:
                raise ValueError("annotation reference contradicts its source occurrence")
            if True not in contexts:
                raise ValueError("annotation reference lacks a complete bounded source occurrence")
            continue
        if record.data.get("reference_context") != SourceReferenceContext.VALUE:
            continue
        if True in contexts:
            raise ValueError("value reference contradicts its annotated source occurrence")
        if False not in contexts:
            raise ValueError("value reference lacks a complete bounded source occurrence")
