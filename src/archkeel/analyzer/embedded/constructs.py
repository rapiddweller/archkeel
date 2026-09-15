# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Statement construct collection: assert statements and broad except handlers."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, RecordData, classified, stable_id
from .source import ParsedModule, add_evidence, location

_BROAD_NAMES = frozenset({"Exception", "BaseException"})


def _is_broad_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _BROAD_NAMES
    if isinstance(node, ast.Attribute):
        return (
            node.attr in _BROAD_NAMES
            and isinstance(node.value, ast.Name)
            and node.value.id == "builtins"
        )
    if isinstance(node, ast.Tuple):
        return any(_is_broad_type(element) for element in node.elts)
    return False


def _handled_types(caught: ast.expr) -> list[str]:
    elements = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return sorted(ast.unparse(element) for element in elements)


class ConstructCollector(ast.NodeVisitor):
    """Walk one module, recording assert statements and broad except handlers."""

    def __init__(self, module: ParsedModule, evidence: dict[str, RawEvidence]) -> None:
        self.module = module
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scope_stack: list[str] = [module.module]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self._record(node, kind="assert_statement", construct="assert", handled=None)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if node.type is None or _is_broad_type(node.type):
            handled = [] if node.type is None else _handled_types(node.type)
            self._record(node, kind="broad_except", construct="broad_except", handled=handled)
        self.generic_visit(node)

    def _record(
        self, node: ast.AST, *, kind: str, construct: str, handled: list[str] | None
    ) -> None:
        owner = self.scope_stack[-1]
        line, _, column = location(node)
        evidence_id = add_evidence(self.evidence, self.module, node)
        data: RecordData = {"owner": owner, "construct": construct}
        if handled is not None:
            data["handled"] = handled
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
