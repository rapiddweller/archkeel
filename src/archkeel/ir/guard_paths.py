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


class _GuardPathWalker:
    def __init__(
        self,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        condition_name: str,
        receiver_name: str | None,
    ) -> None:
        self.function = function
        self.condition_name = condition_name
        self.receiver_name = receiver_name
        self.calls: list[GuardedCallPath] = []

    def writes_name(self, node: ast.AST) -> bool:
        direct = any(
            isinstance(child, ast.Name)
            and child.id == self.condition_name
            and isinstance(child.ctx, ast.Store)
            or self.receiver_name is not None
            and isinstance(child, ast.Attribute)
            and child.attr == self.condition_name
            and isinstance(child.ctx, ast.Store)
            and isinstance(child.value, ast.Name)
            and child.value.id == self.receiver_name
            for child in ast.walk(node)
        )
        if direct:
            return True
        return any(self._reflective_write(child) for child in ast.walk(node)) or (
            self.receiver_name is not None
            and any(
                isinstance(child, ast.Attribute)
                and child.attr == "__dict__"
                and isinstance(child.value, ast.Name)
                and child.value.id == self.receiver_name
                for child in ast.walk(node)
            )
        )

    def _reflective_write(self, child: ast.AST) -> bool:
        if not isinstance(child, ast.Call):
            return False
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
            return False
        args = child.args
        if isinstance(child.func, ast.Attribute):
            receiver = child.func.value
            if (
                isinstance(receiver, ast.Name)
                and receiver.id == "object"
                and args
                and isinstance(args[0], ast.Name)
                and args[0].id == self.receiver_name
            ):
                args = args[1:]
            elif not (isinstance(receiver, ast.Name) and receiver.id == self.receiver_name):
                return False
        elif not (args and isinstance(args[0], ast.Name) and args[0].id == self.receiver_name):
            return False
        return (
            len(args) < 2
            or not isinstance(args[1], ast.Constant)
            or (args[1].value == self.condition_name)
        )

    def reads_name(self, node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Name)
            and child.id == self.condition_name
            and isinstance(child.ctx, ast.Load)
            or self.receiver_name is not None
            and isinstance(child, ast.Attribute)
            and child.attr == self.condition_name
            and isinstance(child.ctx, ast.Load)
            and isinstance(child.value, ast.Name)
            and child.value.id == self.receiver_name
            for child in ast.walk(node)
        )

    @staticmethod
    def has_calls(node: ast.AST) -> bool:
        return any(isinstance(child, ast.Call) for child in ast.walk(node))

    @staticmethod
    def _branch_state(
        current: bool | None,
        reason: str | None,
        guard: bool | None,
        branch_value: bool | None,
    ) -> tuple[bool | None, str | None] | None:
        if guard is None:
            return current, reason
        if branch_value is None:
            return current, reason
        if reason is not None:
            return None, reason
        if current is not None and current is not branch_value:
            return None
        return branch_value, None

    def expression(
        self,
        node: ast.AST,
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None = None,
        *,
        raised_exception_constructor: bool = False,
    ) -> None:
        if isinstance(node, ast.IfExp):
            self._conditional_expression(node, value, path_nodes, unknown_reason)
            return
        for child in ast.iter_child_nodes(node):
            self.expression(child, value, path_nodes, unknown_reason)
        if isinstance(node, ast.Call):
            self.calls.append(
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

    def _conditional_expression(
        self,
        node: ast.IfExp,
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None,
    ) -> None:
        guard = _guard_value(node.test, self.condition_name, self.receiver_name)
        reason = (
            "condition_mutation"
            if self.writes_name(node.test)
            else "unsupported_condition"
            if self.reads_name(node.test) and guard is None
            else unknown_reason
        )
        self.expression(node.test, value, path_nodes, reason)
        branch_nodes = (*path_nodes, node.test)
        body_state = self._branch_state(value, reason, guard, guard)
        if body_state is not None:
            self.expression(node.body, body_state[0], branch_nodes, body_state[1])
        else_state = self._branch_state(
            value, reason, guard, not guard if guard is not None else None
        )
        if else_state is not None:
            self.expression(node.orelse, else_state[0], branch_nodes, else_state[1])

    def block(
        self,
        statements: list[ast.stmt],
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None = None,
    ) -> list[tuple[bool | None, str | None, tuple[ast.AST, ...]]]:
        active: list[tuple[bool | None, str | None, tuple[ast.AST, ...]]] = [
            (value, unknown_reason, path_nodes)
        ]
        for statement in statements:
            next_active: list[tuple[bool | None, str | None, tuple[ast.AST, ...]]] = []
            for current, current_reason, current_nodes in active:
                next_active.extend(
                    self._statement_paths(statement, current, current_reason, current_nodes)
                )
            active = next_active
            if not active:
                break
        return active

    def _statement_paths(
        self,
        statement: ast.stmt,
        current: bool | None,
        reason: str | None,
        path_nodes: tuple[ast.AST, ...],
    ) -> list[tuple[bool | None, str | None, tuple[ast.AST, ...]]]:
        if isinstance(statement, ast.If):
            return self._if_paths(statement, current, reason, path_nodes)
        if isinstance(
            statement,
            (
                ast.While,
                ast.For,
                ast.AsyncFor,
                ast.Try,
                ast.TryStar,
                ast.With,
                ast.AsyncWith,
                ast.Match,
            ),
        ):
            self._unsupported_flow(statement, path_nodes)
            return [(None, "unsupported_control_flow", path_nodes)]
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = statement.args
            for expression in (
                *statement.decorator_list,
                *arguments.defaults,
                *(item for item in arguments.kw_defaults if item is not None),
            ):
                self.expression(expression, current, path_nodes, reason)
            return [(current, reason, path_nodes)]
        if isinstance(statement, ast.ClassDef):
            for expression in (
                *statement.decorator_list,
                *statement.bases,
                *(keyword.value for keyword in statement.keywords),
            ):
                self.expression(expression, current, path_nodes, reason)
            self.block(statement.body, current, path_nodes, reason)
            return [(current, reason, path_nodes)]
        return self._ordinary_paths(statement, current, reason, path_nodes)

    def _if_paths(
        self,
        statement: ast.If,
        current: bool | None,
        current_reason: str | None,
        path_nodes: tuple[ast.AST, ...],
    ) -> list[tuple[bool | None, str | None, tuple[ast.AST, ...]]]:
        guard = _guard_value(statement.test, self.condition_name, self.receiver_name)
        test_reason = (
            "condition_mutation"
            if self.writes_name(statement.test)
            else "opaque_call_mutation"
            if self.receiver_name is not None and self.has_calls(statement.test)
            else "unsupported_condition"
            if guard is None and self.reads_name(statement.test)
            else current_reason
        )
        self.expression(statement.test, current, path_nodes, test_reason)
        branch_nodes = (
            (*path_nodes, statement.test)
            if guard is not None or test_reason is not current_reason
            else path_nodes
        )
        body_state = self._branch_state(current, test_reason, guard, guard)
        else_state = self._branch_state(
            current, test_reason, guard, not guard if guard is not None else None
        )
        branches = []
        if body_state is not None:
            branches.extend(self.block(statement.body, body_state[0], branch_nodes, body_state[1]))
        if else_state is not None:
            branches.extend(
                self.block(statement.orelse, else_state[0], branch_nodes, else_state[1])
            )
        return branches

    def _unsupported_flow(self, statement: ast.stmt, path_nodes: tuple[ast.AST, ...]) -> None:
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.expr):
                self.expression(child, None, (*path_nodes, statement), "unsupported_control_flow")
            elif isinstance(child, ast.stmt):
                self.block([child], None, (*path_nodes, statement), "unsupported_control_flow")

    def _ordinary_paths(
        self,
        statement: ast.stmt,
        current: bool | None,
        current_reason: str | None,
        path_nodes: tuple[ast.AST, ...],
    ) -> list[tuple[bool | None, str | None, tuple[ast.AST, ...]]]:
        reason = (
            "condition_mutation"
            if self.writes_name(statement)
            else "opaque_call_mutation"
            if self.receiver_name is not None
            and sum(isinstance(child, ast.Call) for child in ast.walk(statement)) > 1
            else current_reason
        )
        expression = (
            statement.exc if isinstance(statement, ast.Raise) and statement.exc else statement
        )
        self.expression(
            expression,
            None if reason in {"condition_mutation", "opaque_call_mutation"} else current,
            path_nodes,
            reason,
            raised_exception_constructor=isinstance(statement, ast.Raise)
            and isinstance(statement.exc, ast.Call),
        )
        if isinstance(statement, ast.Return | ast.Raise):
            return []
        if self.receiver_name is not None and self.has_calls(statement):
            reason = "opaque_call_mutation"
        next_value = None if reason in {"condition_mutation", "opaque_call_mutation"} else current
        return [(next_value, reason, path_nodes)]


def guarded_call_paths(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    condition_name: str,
    *,
    receiver_name: str | None = None,
) -> tuple[GuardedCallPath, ...]:
    """Record call occurrences with a Boolean parameter path when the syntax proves one."""
    walker = _GuardPathWalker(function, condition_name, receiver_name)
    walker.block(function.body, None, ())
    return tuple(walker.calls)
