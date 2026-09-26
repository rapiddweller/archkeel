# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record uses of a scanned symbol that are not calls (AD-26).

A function handed to a dictionary, passed as an argument or read as a property is used,
but no call site names it. Without this signal a call graph reports such a symbol as
unreferenced, which was wrong for every candidate it produced on Archkeel itself.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, stable_id

from .records import RawEvidence, RawRecord, classified
from .resolve import SymbolIndex, dotted_expression, resolve_name
from .source import ParsedModule, add_evidence, annotation_text, location, own_scope


class ReferenceCollector(ast.NodeVisitor):
    """Walk one module and record every non-call use of an indexed symbol."""

    def __init__(
        self,
        module: ParsedModule,
        index: SymbolIndex,
        evidence: dict[str, RawEvidence],
    ) -> None:
        self.module = module
        self.index = index
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [module.module]
        self.shadowed_names: list[frozenset[str]] = []

    @staticmethod
    def _target_names(node: ast.AST) -> set[str]:
        return {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        }

    @classmethod
    def _class_bound_names(cls, node: ast.ClassDef) -> frozenset[str]:
        names: set[str] = set()
        for statement in node.body:
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names.add(statement.name)
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    names.update(cls._target_names(target))
            elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
                names.update(cls._target_names(statement.target))
            elif isinstance(statement, ast.Import):
                names.update(alias.asname or alias.name.split(".")[0] for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom):
                names.update(alias.asname or alias.name for alias in statement.names)
        return frozenset(names)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = f"{self.scope_stack[-1]}.{node.name}"
        for child in ast.iter_child_nodes(node):
            if child not in node.body:
                self.visit(child)
        self.class_stack.append(qualname)
        self.scope_stack.append(qualname)
        self.shadowed_names.append(self._class_bound_names(node))
        for statement in node.body:
            self.visit(statement)
        self.shadowed_names.pop()
        self.scope_stack.pop()
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for child in ast.iter_child_nodes(node):
            if child not in node.body:
                self.visit(child)

        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        bound_names = {argument.arg for argument in arguments}
        bound_names.update(
            child.id
            for child in own_scope(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        )
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.shadowed_names.append(frozenset(bound_names))
        for statement in node.body:
            self.visit(statement)
        self.shadowed_names.pop()
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        # The callee belongs to the call collector; its arguments are ordinary uses.
        for child in ast.iter_child_nodes(node):
            if child is not node.func:
                self.visit(child)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record(node, node.id, "value")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        dotted = dotted_expression(node) if isinstance(node.ctx, ast.Load) else None
        if dotted is None:
            self.generic_visit(node)
            return
        # One record per chain: descending would count `a.b.c` again as `a.b`.
        self._record(node, dotted, "attribute")

    def _record(self, node: ast.expr, expression: str, use: str) -> None:
        enum_member = self._enum_member_class(node)
        if enum_member is None:
            status, targets, _, _ = resolve_name(
                node, module=self.module, index=self.index, class_stack=self.class_stack
            )
        else:
            status, targets = "resolved", [enum_member]
        internal = [target for target in targets if target in self.index.names]
        if status == "unresolved" or not internal:
            return
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        text = annotation_text(node) or expression
        self.items.append(
            classified(
                item_id=stable_id("REF", self.module.rel_path, line, column, text),
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind=f"{use}_reference",
                title=f"Reference {text}",
                subjects=[self.scope_stack[-1], *internal],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": self.scope_stack[-1],
                    "source_module": self.module.module,
                    "expression": text,
                    "status": status,
                    "targets": sorted(internal),
                    "use": use,
                },
            )
        )

    def _enum_member_class(self, node: ast.expr) -> str | None:
        """Resolve only a member listed on one statically bound enum class."""
        if not isinstance(node, ast.Attribute):
            return None
        dotted = dotted_expression(node)
        if dotted is None:
            return None
        parts = dotted.split(".")
        if len(parts) < 2:
            return None
        if any(parts[0] in names for names in self.shadowed_names):
            return None
        status, targets, _, _ = resolve_name(
            node.value, module=self.module, index=self.index, class_stack=self.class_stack
        )
        if status != "resolved" or len(targets) != 1:
            return None
        enum_name = targets[0]
        members = self.index.enum_members.get(enum_name)
        return enum_name if members is not None and parts[-1] in members else None


def collect_references(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    """Run the reference collector over every module and sort the records by id."""
    references: list[RawRecord] = []
    for module in parsed:
        collector = ReferenceCollector(module, index, evidence)
        collector.visit(module.tree)
        references.extend(collector.items)
    references.sort(key=lambda item: item["id"])
    return references
