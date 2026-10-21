# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small syntax-only proof helpers shared by source collection and saved readers."""

from __future__ import annotations

import ast


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
