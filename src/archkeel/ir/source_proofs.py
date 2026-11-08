# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small syntax-only proof helpers shared by source collection and saved readers."""

from __future__ import annotations

import ast
from functools import lru_cache

from .facts import MAX_NUMERIC_EVIDENCE_CHARS


def _instance_member_write_nodes(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    """Find bounded writes or escapes of a method receiver."""
    parameters = [*node.args.posonlyargs, *node.args.args]
    if not parameters:
        return ()
    aliases = {parameters[0].arg}
    writes: set[str] = set()
    pending: list[ast.AST] = [*reversed(node.body)]
    while pending:
        child = pending.pop()
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            if _contains_alias(child, aliases):
                writes = writes | {"*"}
            continue
        pending.extend(reversed(tuple(ast.iter_child_nodes(child))))
        if isinstance(child, ast.Assign):
            targets = tuple(
                target
                for expression in child.targets
                for target in ast.walk(expression)
                if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store)
            )
            if isinstance(child.value, ast.Name) and child.value.id in aliases:
                aliases = aliases | {target.id for target in targets}
            elif targets and _receiver_escapes_in_value(child.value, aliases):
                writes = writes | {"*"}
        elif isinstance(child, ast.AnnAssign):
            if isinstance(child.value, ast.Name) and child.value.id in aliases:
                if isinstance(child.target, ast.Name):
                    aliases = aliases | {child.target.id}
            elif child.value is not None and _receiver_escapes_in_value(child.value, aliases):
                writes = writes | {"*"}
        if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store | ast.Del):
            if isinstance(child.value, ast.Name) and child.value.id in aliases:
                writes = writes | {child.attr}
            elif _contains_alias(child.value, aliases):
                writes = writes | {"*"}
        elif isinstance(child, ast.Subscript) and isinstance(child.ctx, ast.Store | ast.Del):
            if _contains_alias(child.value, aliases):
                writes = writes | {"*"}
        elif isinstance(child, ast.Return | ast.Yield | ast.YieldFrom):
            value = child.value
            if value is not None and _receiver_escapes_in_value(value, aliases):
                writes = writes | {"*"}
        elif isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id in {"setattr", "delattr"}:
                if (
                    child.args
                    and isinstance(child.args[0], ast.Name)
                    and child.args[0].id in aliases
                ):
                    member = child.args[1] if len(child.args) > 1 else None
                    name = (
                        member.value
                        if isinstance(member, ast.Constant) and isinstance(member.value, str)
                        else "*"
                    )
                    writes = writes | {name}
            elif any(_contains_alias(argument, aliases) for argument in child.args) or any(
                _contains_alias(keyword.value, aliases) for keyword in child.keywords
            ):
                writes = writes | {"*"}
    return tuple(sorted(writes))


def class_instance_member_write_names(node: ast.ClassDef) -> tuple[str, ...]:
    names = {
        member
        for child in node.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        for member in _instance_member_write_nodes(child)
    }
    return tuple(sorted(names))


def _contains_alias(node: ast.AST, aliases: set[str]) -> bool:
    return any(isinstance(child, ast.Name) and child.id in aliases for child in ast.walk(node))


def _receiver_escapes_in_value(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(_receiver_escapes_in_value(item, aliases) for item in node.elts)
    if isinstance(node, ast.Subscript):
        return _contains_alias(node.value, aliases)
    if isinstance(node, ast.Dict):
        return any(
            item is not None and _receiver_escapes_in_value(item, aliases)
            for item in (*node.keys, *node.values)
        )
    if isinstance(node, ast.IfExp):
        return _receiver_escapes_in_value(node.body, aliases) or _receiver_escapes_in_value(
            node.orelse, aliases
        )
    if isinstance(node, ast.Lambda):
        return _contains_alias(node.body, aliases)
    if isinstance(node, ast.Call):
        return any(_contains_alias(argument, aliases) for argument in node.args) or any(
            _contains_alias(keyword.value, aliases) for keyword in node.keywords
        )
    return False


@lru_cache(maxsize=256)
def parse_numeric_evidence_excerpt(
    excerpt: str,
) -> tuple[tuple[ast.stmt, ...], int] | None:
    """Parse the one-line excerpt of a source evidence as the statements that it starts.

    The second value is the number of wrapper lines that the parse added before the excerpt. A
    header, a decorator and an `elif` have no body or no `if` in one line: the parser adds a
    synthetic one and returns it. It returns None when no such parse is possible.
    """
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS or "\n" in excerpt:
        return None
    stripped: str = excerpt.lstrip(" \t")
    if stripped.startswith("@"):
        return _parse_numeric_decorator_excerpt(excerpt)
    if _numeric_elif_start(excerpt) is not None:
        return _parse_numeric_elif_excerpt(excerpt)
    try:
        return tuple(ast.parse(excerpt).body), 0
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
        parsed = _parse_indented_numeric_excerpt(excerpt, indentation, synthetic_body=False)
        if parsed is not None:
            return parsed
        parsed = _parse_indented_numeric_excerpt(excerpt, indentation, synthetic_body=True)
        if parsed is None or len(parsed[0]) != 1:
            return None
        return parsed if _numeric_header_has_synthetic_body(parsed[0][0]) else None


def _parse_numeric_decorator_excerpt(
    excerpt: str,
) -> tuple[tuple[ast.stmt, ...], int] | None:
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    unit = "\t" if "\t" in indentation else "    "
    prefix = "if True:\n" if indentation else ""
    source = (
        f"{prefix}{excerpt}\n"
        f"{indentation}def __archkeel_numeric_witness__():\n"
        f"{indentation}{unit}pass"
    )
    try:
        parsed = ast.parse(source)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots = tuple(parsed.body)
    if indentation and (len(roots) != 1 or not isinstance(roots[0], ast.If)):
        return None
    body = tuple(roots[0].body) if indentation and isinstance(roots[0], ast.If) else roots
    if (
        len(body) != 1
        or not isinstance(body[0], ast.FunctionDef)
        or len(body[0].decorator_list) != 1
    ):
        return None
    return roots, 1 if indentation else 0


def _numeric_elif_start(excerpt: str) -> int | None:
    for index, character in enumerate(excerpt):
        if character not in " \t":
            if excerpt[index : index + 4] != "elif":
                return None
            if index + 4 < len(excerpt) and excerpt[index + 4] not in " \t(":
                return None
            return index
    return None


def _parse_indented_numeric_excerpt(
    excerpt: str, indentation: str, *, synthetic_body: bool
) -> tuple[tuple[ast.stmt, ...], int] | None:
    unit = "\t" if "\t" in indentation else "    "
    depth = 1 if indentation else 0
    wrappers = "if True:\n" if indentation else ""
    suffix = f"\n{indentation}{unit}pass" if synthetic_body else ""
    try:
        parsed = ast.parse(wrappers + excerpt + suffix)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots = tuple(parsed.body)
    for _ in range(depth):
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return None
        roots = tuple(roots[0].body)
    return roots, depth


def _numeric_header_has_synthetic_body(node: ast.stmt) -> bool:
    header_types = (
        ast.If,
        ast.While,
        ast.For,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    return (
        isinstance(node, header_types)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def _parse_numeric_elif_excerpt(excerpt: str) -> tuple[tuple[ast.stmt, ...], int] | None:
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    unit = "\t" if "\t" in indentation else "    "
    source = f"{indentation}if True:\n{indentation}{unit}pass\n{excerpt}"
    for synthetic_body in (False, True):
        parsed = _parse_indented_numeric_excerpt(source, indentation, synthetic_body=synthetic_body)
        if parsed is None:
            continue
        roots, depth = parsed
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return None
        preceding = roots[0]
        if len(preceding.body) != 1 or not isinstance(preceding.body[0], ast.Pass):
            return None
        if len(preceding.orelse) != 1 or not isinstance(preceding.orelse[0], ast.If):
            return None
        alternate = preceding.orelse[0]
        if not synthetic_body or _numeric_header_has_synthetic_body(alternate):
            return roots, depth + 2
    return None
