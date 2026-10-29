# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small, source-only path facts for guarded-effect rules."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass

# (condition value, unknown reason): what the walker knows about the guard at one point.
_State = tuple[bool | None, str | None]


@dataclass(frozen=True, slots=True)
class GuardedCallPath:
    call_name: str
    line: int
    column: int
    condition_value: bool | None
    path_nodes: tuple[ast.AST, ...] = ()
    unknown_reason: str | None = None
    raised_exception_constructor: bool = False


def _function_header_expressions(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.expr]:
    """The decorators and default values of a `def`: they run when the statement runs."""
    arguments = function.args
    return [
        *function.decorator_list,
        *arguments.defaults,
        *(item for item in arguments.kw_defaults if item is not None),
    ]


def _function_annotations(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
    """The annotations of a `def`. Python 3.13 and older run them when the statement runs."""
    arguments = function.args
    parameters = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    if arguments.vararg:
        parameters.append(arguments.vararg)
    if arguments.kwarg:
        parameters.append(arguments.kwarg)
    return [
        *(parameter.annotation for parameter in parameters if parameter.annotation is not None),
        *([function.returns] if function.returns is not None else []),
    ]


def _class_runs_hooks(statement: ast.ClassDef) -> bool:
    """Whether the class statement runs a hook after its body, with no call node in the source.

    The hooks are `__init_subclass__` of a base, a metaclass `__new__` or `__init__`, and
    `__set_name__` of a body value. Only a class without base and keyword, and with a body of
    literal fields and undecorated methods, runs none.
    """
    if statement.bases or statement.keywords:
        return True
    return not all(_is_plain_class_field(item) for item in statement.body)


def _is_plain_class_field(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
        return not statement.decorator_list
    if isinstance(statement, ast.Expr):
        return isinstance(statement.value, ast.Constant)
    if isinstance(statement, ast.Assign):
        return _is_literal(statement.value) and all(
            isinstance(target, ast.Name) for target in statement.targets
        )
    if isinstance(statement, ast.AnnAssign):
        return isinstance(statement.target, ast.Name) and (
            statement.value is None or _is_literal(statement.value)
        )
    return isinstance(statement, ast.Pass)


def _is_literal(expression: ast.expr) -> bool:
    try:
        ast.literal_eval(expression)
    except (ValueError, TypeError):
        return False
    return True


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
        # Rebinding the receiver (`self = other`) moves the guard just like rebinding the name.
        self.bound_names = {condition_name} | ({receiver_name} if receiver_name else set())
        self.calls: list[GuardedCallPath] = []

    def writes_name(self, node: ast.AST) -> bool:
        direct = any(self._rebinds(child) for child in ast.walk(node))
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

    def _rebinds(self, child: ast.AST) -> bool:
        # Store and Del both end the guard: after `del flag` the name is no longer the parameter.
        if isinstance(child, ast.Name):
            return child.id in self.bound_names and isinstance(child.ctx, ast.Store | ast.Del)
        if isinstance(child, ast.Attribute):
            return (
                child.attr == self.condition_name
                and isinstance(child.ctx, ast.Store | ast.Del)
                and isinstance(child.value, ast.Name)
                and child.value.id == self.receiver_name
            )
        if isinstance(child, ast.alias):
            # `import a.b` binds `a`.
            bound = child.asname or child.name
            return any(
                bound == name or bound[: len(name) + 1] == f"{name}." for name in self.bound_names
            )
        return False

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
            # Identical states walk identically, so merging them keeps every distinct record
            # and stops sequential `if` blocks from doubling the states (2^k).
            active = list(dict.fromkeys(next_active))
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
            state = self._definition_state(
                statement.name,
                _function_header_expressions(statement),
                _function_annotations(statement),
                len(statement.decorator_list),
                current,
                reason,
                path_nodes,
            )
            return [(*state, path_nodes)]
        if isinstance(statement, ast.ClassDef):
            header = (
                *statement.decorator_list,
                *statement.bases,
                *(keyword.value for keyword in statement.keywords),
            )
            # A decorator and a class keyword are each one call: `@d` is `d(cls)`, and the
            # keywords go to the metaclass or to `__init_subclass__`.
            applied = len(statement.decorator_list) + len(statement.keywords)
            state = self._definition_state(
                statement.name, header, [], applied, current, reason, path_nodes
            )
            # The body runs now, in order, so the code after the class starts from its end states.
            ends = self.block(statement.body, state[0], path_nodes, state[1])
            if self.receiver_name is None or not _class_runs_hooks(statement):
                return ends
            # The hooks run after the body, so they can change the member after the body ends.
            return list(
                dict.fromkeys(
                    (None, end_reason or "opaque_call_mutation", end_nodes)
                    for _, end_reason, end_nodes in ends
                )
            )
        return self._ordinary_paths(statement, current, reason, path_nodes)

    def _call_states(
        self,
        nodes: Sequence[ast.AST],
        rebinds: bool,
        applied: int,
        current: bool | None,
        reason: str | None,
    ) -> tuple[_State, _State]:
        """Return the state in which the calls of `nodes` are recorded, and the state after them.

        With a receiver, any call can change the member. A second call runs after the first, so
        it has no value. `applied` counts calls that the syntax makes without a call node, and
        they run last, so they change only the state after.
        """
        current_state: _State = (current, reason)
        opaque: _State = (None, "opaque_call_mutation")
        calls = sum(isinstance(child, ast.Call) for node in nodes for child in ast.walk(node))
        calls_mutate = self.receiver_name is not None
        record: _State
        after: _State
        if rebinds or any(self.writes_name(node) for node in nodes):
            record = (None, "condition_mutation")
            after = record
        else:
            record = opaque if calls_mutate and calls > 1 else current_state
            after = current_state
        return record, (opaque if calls_mutate and calls + applied else after)

    def _definition_state(
        self,
        name: str,
        header: Sequence[ast.expr],
        annotations: Sequence[ast.expr],
        applied: int,
        current: bool | None,
        reason: str | None,
        path_nodes: tuple[ast.AST, ...],
    ) -> _State:
        """Run the header of a `def` or `class`, record its calls, return the state after it.

        An annotation can rebind or call too, but it only changes the state: a deferred
        annotation (Python 3.14, or the `__future__` import) never runs, so its call is no
        effect. With such an annotation the walker reports a false UNKNOWN, never a false proof.
        """
        record, after = self._call_states(
            [*header, *annotations], name in self.bound_names, applied, current, reason
        )
        for expression in header:
            self.expression(expression, record[0], path_nodes, record[1])
        return after

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
        self._unsupported_children(statement, (*path_nodes, statement))

    def _unsupported_children(self, node: ast.AST, path_nodes: tuple[ast.AST, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self.expression(child, None, path_nodes, "unsupported_control_flow")
            elif isinstance(child, ast.stmt):
                self.block([child], None, path_nodes, "unsupported_control_flow")
            else:
                # except handlers, with items and match cases hold statements and expressions.
                self._unsupported_children(child, path_nodes)

    def _ordinary_paths(
        self,
        statement: ast.stmt,
        current: bool | None,
        current_reason: str | None,
        path_nodes: tuple[ast.AST, ...],
    ) -> list[tuple[bool | None, str | None, tuple[ast.AST, ...]]]:
        record, after = self._call_states((statement,), False, 0, current, current_reason)
        expression = (
            statement.exc if isinstance(statement, ast.Raise) and statement.exc else statement
        )
        self.expression(
            expression,
            record[0],
            path_nodes,
            record[1],
            raised_exception_constructor=isinstance(statement, ast.Raise)
            and isinstance(statement.exc, ast.Call),
        )
        if isinstance(statement, ast.Return | ast.Raise):
            return []
        return [(*after, path_nodes)]


def guarded_call_paths(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    condition_name: str,
    *,
    receiver_name: str | None = None,
) -> tuple[GuardedCallPath, ...]:
    """Record call occurrences with a Boolean parameter path when the syntax proves one."""
    walker = _GuardPathWalker(function, condition_name, receiver_name)
    # A nested function can rebind the name later, through a call the walker does not follow.
    closure_rebinds = any(
        isinstance(node, ast.Nonlocal) and any(name in walker.bound_names for name in node.names)
        for node in ast.walk(function)
    )
    walker.block(function.body, None, (), "condition_mutation" if closure_rebinds else None)
    return tuple(walker.calls)
