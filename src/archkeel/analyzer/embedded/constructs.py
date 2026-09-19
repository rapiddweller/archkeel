# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct collection: asserts, broad excepts, empty bodies, reflection and string dispatch."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, stable_id

from .records import RawEvidence, RawRecord, RecordData, classified
from .source import ParsedModule, add_evidence, body_is_empty, decorator_names, location

_BROAD_NAMES = frozenset({"Exception", "BaseException"})
_REFLECTION_CALLS = {"setattr": "setattr_call", "delattr": "delattr_call", "vars": "vars_call"}
# A stub carrying one of these declares a shape; emptiness is its interface, not a gap (AD-29).
_STUB_DECORATORS = frozenset(
    {
        "abstractmethod",
        "abstractproperty",
        "abstractclassmethod",
        "abstractstaticmethod",
        "overload",
    }
)


def _raises_not_implemented(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [
        statement
        for statement in node.body
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
    ]
    return (
        len(body) == 1
        and isinstance(body[0], ast.Raise)
        and "NotImplementedError" in ast.unparse(body[0])
    )


def _as_written(node: ast.AST) -> str | None:
    """The name a node spells as written, bare or as `builtins.<name>`; aliases stay unseen."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.attr if node.value.id == "builtins" else None
    return None


def _is_broad_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Tuple):
        return any(_is_broad_type(element) for element in node.elts)
    return _as_written(node) in _BROAD_NAMES


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_main_guard(node: ast.Compare) -> bool:
    operands = (node.left, *node.comparators)
    return (
        len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and [operand.id for operand in operands if isinstance(operand, ast.Name)] == ["__name__"]
        and [operand.value for operand in operands if isinstance(operand, ast.Constant)]
        == ["__main__"]
    )


def _dispatch_form(node: ast.Compare) -> str | None:
    """Name how a comparison branches on a str literal, or nothing when it does not (AD-48)."""
    # The interpreter's entry protocol, not a vocabulary an enum could replace.
    if _is_main_guard(node):
        return None
    operands = [node.left, *node.comparators]
    for operator, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
        if isinstance(operator, ast.Eq | ast.NotEq) and (_is_str(left) or _is_str(right)):
            return "compare"
        if (
            isinstance(operator, ast.In | ast.NotIn)
            and isinstance(right, ast.Tuple | ast.List | ast.Set)
            and right.elts
            and all(_is_str(element) for element in right.elts)
        ):
            return "membership"
    return None


def _matches_str_literal(node: ast.Match) -> bool:
    """A mapping key is structure, not a value pattern, so only `MatchValue` counts."""
    return any(
        isinstance(pattern, ast.MatchValue) and _is_str(pattern.value)
        for case in node.cases
        for pattern in ast.walk(case.pattern)
    )


def _handled_types(caught: ast.expr) -> list[str]:
    elements = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return sorted(ast.unparse(element) for element in elements)


class ConstructCollector(ast.NodeVisitor):
    """Walk one module, recording each construct under the scope that owns it."""

    def __init__(self, module: ParsedModule, evidence: dict[str, RawEvidence]) -> None:
        self.module = module
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scope_stack: list[str] = [module.module]
        self.inherits_stack: list[bool] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.inherits_stack.append(bool(node.bases))
        self.generic_visit(node)
        self.inherits_stack.pop()
        self.scope_stack.pop()

    def _placeholder_form(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        """Name what the body holds instead of an implementation, or nothing when it is one."""
        if _STUB_DECORATORS.intersection(decorator_names(node)):
            return None
        # A class with a base declares a shape its members may leave empty on purpose.
        if self.inherits_stack and self.inherits_stack[-1]:
            return None
        if body_is_empty(node):
            return "empty"
        return "not_implemented" if _raises_not_implemented(node) else None

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        form = self._placeholder_form(node)
        if form is not None:
            self._record(
                node, kind="placeholder_body", construct="placeholder_body", handled=None, form=form
            )
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._record(node, kind="assert_statement", construct="assert", handled=None)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None or _is_broad_type(node.type):
            handled = [] if node.type is None else _handled_types(node.type)
            self._record(node, kind="broad_except", construct="broad_except", handled=handled)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _as_written(node.func)
        if name is not None and name in _REFLECTION_CALLS:
            self._record(node, kind=_REFLECTION_CALLS[name], construct=name, handled=None)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Both nodes of `x.__dict__.__dict__` start at one column, so one id; the inner records.
        outer_of_chain = isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
        if node.attr == "__dict__" and not outer_of_chain:
            self._record(node, kind="dunder_dict", construct="dunder_dict", handled=None)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        form = _dispatch_form(node)
        if form is not None:
            self._record(
                node, kind="string_dispatch", construct="string_dispatch", handled=None, form=form
            )
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        if _matches_str_literal(node):
            self._record(
                node,
                kind="string_dispatch",
                construct="string_dispatch",
                handled=None,
                form="match",
            )
        self.generic_visit(node)

    def _record(
        self,
        node: ast.AST,
        *,
        kind: str,
        construct: str,
        handled: list[str] | None,
        form: str | None = None,
    ) -> None:
        owner = self.scope_stack[-1]
        line, _, column = location(node)
        evidence_id = add_evidence(self.evidence, self.module, node)
        data: RecordData = {"owner": owner, "construct": construct}
        if handled is not None:
            data["handled"] = handled
        if form is not None:
            data["form"] = form
        self.items.append(
            classified(
                item_id=stable_id("CONSTRUCT", self.module.rel_path, line, column, kind),
                evidence_class=EvidenceClass.FACT,
                area="constructs",
                kind=kind,
                title=f"{owner} uses {construct}",
                subjects=[owner],
                evidence_ids=[evidence_id],
                data=data,
            )
        )


def collect_constructs(
    parsed: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    """Run the construct collector over every module and sort records by id."""
    items: list[RawRecord] = []
    for module in parsed:
        collector = ConstructCollector(module, evidence)
        collector.visit(module.tree)
        items.extend(collector.items)
    items.sort(key=lambda item: item["id"])
    return items
