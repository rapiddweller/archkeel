# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect type syntax without resolving bindings or consulting architecture policy."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from types import MappingProxyType

from archkeel.ir.facts_codec import RawRecord
from archkeel.ir.type_shapes import (
    LiteralKind,
    TypeApplication,
    TypeLiteral,
    TypeMember,
    TypeName,
    TypeShape,
    TypeShapeIndex,
    TypeUnion,
    TypeUnpack,
    UnresolvedType,
)


def collect_type_shapes(annotations: Iterable[str]) -> TypeShapeIndex:
    shapes: dict[str, TypeShape] = {}
    for annotation in annotations:
        if annotation in shapes:
            continue
        try:
            expression = ast.parse(annotation, mode="eval").body
        except SyntaxError:
            shapes[annotation] = UnresolvedType(annotation, valid_syntax=False)
            continue
        shapes[annotation] = _shape(expression, annotation, shapes)
    return MappingProxyType(shapes)


def _shape(node: ast.expr, source: str, shapes: dict[str, TypeShape]) -> TypeShape:
    text = ast.unparse(node)
    shape: TypeShape
    if isinstance(node, ast.Name):
        shape = TypeName(text, node.id)
    elif isinstance(node, ast.Attribute):
        shape = TypeMember(text, _shape(node.value, source, shapes), node.attr)
    elif isinstance(node, ast.Subscript):
        arguments = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        shape = TypeApplication(
            text,
            _shape(node.value, source, shapes),
            tuple(_shape(argument, source, shapes) for argument in arguments),
            tuple_arguments=isinstance(node.slice, ast.Tuple),
        )
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        shape = TypeUnion(
            text, _shape(node.left, source, shapes), _shape(node.right, source, shapes)
        )
    elif isinstance(node, ast.Constant):
        kind = (
            LiteralKind.NONE
            if node.value is None
            else LiteralKind.ELLIPSIS
            if node.value is Ellipsis
            else LiteralKind.BOOLEAN
            if isinstance(node.value, bool)
            else LiteralKind.INTEGER
            if isinstance(node.value, int)
            else LiteralKind.STRING
            if isinstance(node.value, str)
            else LiteralKind.OTHER
        )
        shape = TypeLiteral(text, kind)
    elif isinstance(node, ast.Starred):
        shape = TypeUnpack(text, _shape(node.value, source, shapes))
    else:
        shape = UnresolvedType(text, valid_syntax=True)
    shapes[text] = shape
    for spelling in _source_spellings(node, source):
        shapes[spelling] = shape
    return shape


def _source_spellings(node: ast.expr, source: str) -> Iterator[str]:
    # AST spans omit grouping parentheses; collection descent retains those source spellings.
    if node.end_lineno is None or node.end_col_offset is None:
        return
    raw = source.encode()
    lines = raw.splitlines(keepends=True)
    start = sum(map(len, lines[: node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[: node.end_lineno - 1])) + node.end_col_offset
    yield raw[start:end].decode()
    while raw[:start].rstrip().endswith(b"(") and raw[end:].lstrip().startswith(b")"):
        start = len(raw[:start].rstrip()) - 1
        end = len(raw) - len(raw[end:].lstrip()) + 1
        yield raw[start:end].decode()


def symbol_type_expressions(symbols: Iterable[RawRecord]) -> Iterator[str]:
    """Enumerate the source text positions emitted by Python symbol collection."""
    for symbol in symbols:
        data = symbol["data"]
        for key in ("name", "alias", "returns"):
            value = data.get(key)
            if isinstance(value, str):
                yield value
        yield from data.get("bases", ())
        for position in (*data.get("parameters", ()), *data.get("fields", ())):
            annotation = position.get("annotation")
            if isinstance(annotation, str):
                yield annotation
