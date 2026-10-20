# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small, source-only path facts for guarded-effect rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuardedCallPath:
    call_name: str
    line: int
    column: int
    condition_value: bool | None
    path_nodes: tuple[ast.AST, ...] = ()
    unknown_reason: str | None = None
    raised_exception_constructor: bool = False


def _is_condition(expression: ast.expr, name: str, receiver: str | None) -> bool:
    return (isinstance(expression, ast.Name) and expression.id == name) or (
        receiver is not None
        and isinstance(expression, ast.Attribute)
        and expression.attr == name
        and isinstance(expression.value, ast.Name)
        and expression.value.id == receiver
    )


def _guard_value(expression: ast.expr, name: str, receiver: str | None) -> bool | None:
    if _is_condition(expression, name, receiver):
        return True
    if (
        isinstance(expression, ast.UnaryOp)
        and isinstance(expression.op, ast.Not)
        and _is_condition(expression.operand, name, receiver)
    ):
        return False
    return None


def guarded_call_paths(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    condition_name: str,
    *,
    receiver_name: str | None = None,
) -> tuple[GuardedCallPath, ...]:
    """Record call occurrences with a Boolean parameter path when the syntax proves one.

    This deliberately handles only structured ``if`` and conditional expressions. Unsupported
    control flow and writes to the selected name erase its value proof.
    """
    calls: list[GuardedCallPath] = []

    def expression(
        node: ast.AST,
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None = None,
        *,
        raised_exception_constructor: bool = False,
    ) -> None:
        if isinstance(node, ast.IfExp):
            test_reason = (
                "condition_mutation"
                if writes_name(node.test)
                else "unsupported_condition"
                if reads_name(node.test)
                and _guard_value(node.test, condition_name, receiver_name) is None
                else unknown_reason
            )
            expression(node.test, value, path_nodes, test_reason)
            guard = _guard_value(node.test, condition_name, receiver_name)
            branch_nodes = (*path_nodes, node.test)
            expression(
                node.body,
                guard if guard is not None else value,
                branch_nodes,
                test_reason,
            )
            expression(
                node.orelse,
                not guard if guard is not None else value,
                branch_nodes,
                test_reason,
            )
            return
        for child in ast.iter_child_nodes(node):
            expression(child, value, path_nodes, unknown_reason)
        if isinstance(node, ast.Call):
            calls.append(
                GuardedCallPath(
                    ast.unparse(node.func),
                    node.lineno,
                    node.col_offset,
                    None if unknown_reason is not None else value,
                    path_nodes,
                    unknown_reason,
                    raised_exception_constructor,
                )
            )

    def writes_name(node: ast.AST) -> bool:
        direct = any(
            isinstance(child, ast.Name)
            and child.id == condition_name
            and isinstance(child.ctx, ast.Store)
            or receiver_name is not None
            and isinstance(child, ast.Attribute)
            and child.attr == condition_name
            and isinstance(child.ctx, ast.Store)
            and isinstance(child.value, ast.Name)
            and child.value.id == receiver_name
            for child in ast.walk(node)
        )
        if direct:
            return True
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            function_name = (
                child.func.id
                if isinstance(child.func, ast.Name)
                else child.func.attr
                if isinstance(child.func, ast.Attribute)
                else None
            )
            if function_name in {"exec", "eval", "globals", "locals", "vars"}:
                return True
            if function_name not in {"setattr", "delattr", "__setattr__", "__delattr__"}:
                continue
            args = child.args
            if isinstance(child.func, ast.Attribute):
                receiver = child.func.value
                if (
                    isinstance(receiver, ast.Name)
                    and receiver.id == "object"
                    and args
                    and isinstance(args[0], ast.Name)
                    and args[0].id == receiver_name
                ):
                    args = args[1:]
                elif not (isinstance(receiver, ast.Name) and receiver.id == receiver_name):
                    continue
            elif not (args and isinstance(args[0], ast.Name) and args[0].id == receiver_name):
                continue
            if len(args) < 2 or not isinstance(args[1], ast.Constant):
                return True
            if args[1].value == condition_name:
                return True
        if receiver_name is None:
            return False
        return any(
            isinstance(child, ast.Attribute)
            and child.attr == "__dict__"
            and isinstance(child.value, ast.Name)
            and child.value.id == receiver_name
            for child in ast.walk(node)
        )

    def reads_name(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Name)
            and child.id == condition_name
            and isinstance(child.ctx, ast.Load)
            or receiver_name is not None
            and isinstance(child, ast.Attribute)
            and child.attr == condition_name
            and isinstance(child.ctx, ast.Load)
            and isinstance(child.value, ast.Name)
            and child.value.id == receiver_name
            for child in ast.walk(node)
        )

    def has_calls(node: ast.AST) -> bool:
        return any(isinstance(child, ast.Call) for child in ast.walk(node))

    def block(
        statements: list[ast.stmt],
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None = None,
    ) -> list[tuple[bool | None, str | None]]:
        active: list[tuple[bool | None, str | None]] = [(value, unknown_reason)]
        for statement in statements:
            next_active: list[tuple[bool | None, str | None]] = []
            for current, current_reason in active:
                if isinstance(statement, ast.If):
                    guard = _guard_value(statement.test, condition_name, receiver_name)
                    test_reason = (
                        "condition_mutation"
                        if writes_name(statement.test)
                        else "opaque_call_mutation"
                        if receiver_name is not None and has_calls(statement.test)
                        else "unsupported_condition"
                        if guard is None and reads_name(statement.test)
                        else current_reason
                    )
                    expression(statement.test, current, path_nodes, test_reason)
                    branch_nodes = (
                        (*path_nodes, statement.test)
                        if guard is not None or test_reason is not current_reason
                        else path_nodes
                    )
                    if guard is None:
                        next_active.extend(
                            block(statement.body, current, branch_nodes, test_reason)
                        )
                        next_active.extend(
                            block(statement.orelse, current, branch_nodes, test_reason)
                        )
                    else:
                        next_active.extend(block(statement.body, guard, branch_nodes, test_reason))
                        next_active.extend(
                            block(statement.orelse, not guard, branch_nodes, test_reason)
                        )
                    continue
                if isinstance(statement, (ast.While, ast.For, ast.AsyncFor, ast.Try, ast.TryStar)):
                    for child in ast.iter_child_nodes(statement):
                        if isinstance(child, ast.expr):
                            expression(
                                child,
                                None,
                                (*path_nodes, statement),
                                "unsupported_control_flow",
                            )
                        elif isinstance(child, ast.stmt):
                            block(
                                [child],
                                None,
                                (*path_nodes, statement),
                                "unsupported_control_flow",
                            )
                    next_active.append((None, "unsupported_control_flow"))
                    continue
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                statement_reason = (
                    "condition_mutation"
                    if writes_name(statement)
                    else "opaque_call_mutation"
                    if receiver_name is not None
                    and sum(isinstance(child, ast.Call) for child in ast.walk(statement)) > 1
                    else current_reason
                )
                expression(
                    statement.exc
                    if isinstance(statement, ast.Raise) and statement.exc
                    else statement,
                    None
                    if statement_reason in {"condition_mutation", "opaque_call_mutation"}
                    else current,
                    path_nodes,
                    statement_reason,
                    raised_exception_constructor=isinstance(statement, ast.Raise)
                    and isinstance(statement.exc, ast.Call),
                )
                if isinstance(statement, ast.Return | ast.Raise):
                    continue
                invalidated = receiver_name is not None and has_calls(statement)
                if invalidated:
                    statement_reason = "opaque_call_mutation"
                next_active.append(
                    (
                        None
                        if statement_reason in {"condition_mutation", "opaque_call_mutation"}
                        else current,
                        statement_reason,
                    )
                )
            active = next_active
            if not active:
                break
        return active

    block(function.body, None, ())
    calls.sort(key=lambda item: (item.line, item.column))
    return tuple(calls)
