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

from archkeel.ir.model import EvidenceClass, in_scope, stable_id

from .records import RawEvidence, RawRecord, classified
from .resolve import SymbolIndex, dotted_expression, resolve_name
from .source import (
    ParsedModule,
    add_evidence,
    annotation_text,
    location,
    unique_direct_module_bindings,
)


def _enum_member_classes(
    parsed: Sequence[ParsedModule], index: SymbolIndex, roots: dict[str, frozenset[str]]
) -> frozenset[str]:
    eligible: set[str] = {
        f"{module.module}.{name}"
        for module in parsed
        for name in roots[module.module]
        if f"{module.module}.{name}" in index.enum_members
    }
    for module in parsed:
        wildcard = any(
            isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(module.tree)
        )
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Store | ast.Del):
                continue
            if wildcard:
                return frozenset()
            dotted = dotted_expression(node)
            if dotted is None:
                continue
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if not isinstance(root, ast.Name):
                continue
            binding = module.aliases.get(root.id)
            if binding is not None:
                if root.id not in roots[module.module]:
                    # An ambiguous writer may refer to any of its competing imported targets.
                    return frozenset()
                written = binding.target + dotted[len(root.id) :]
            elif f"{module.module}.{root.id}" in index.enum_members:
                written = f"{module.module}.{dotted}"
            else:
                continue
            eligible.difference_update(
                [name for name in eligible if in_scope(name, written) or in_scope(written, name)]
            )
    return frozenset(eligible)


class ReferenceCollector(ast.NodeVisitor):
    """Walk one module and record every non-call use of an indexed symbol."""

    def __init__(
        self,
        module: ParsedModule,
        index: SymbolIndex,
        evidence: dict[str, RawEvidence],
        enum_member_roots: frozenset[str],
        enum_member_classes: frozenset[str],
    ) -> None:
        self.module = module
        self.index = index
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [module.module]
        self.enum_member_roots = enum_member_roots
        self.enum_member_classes = enum_member_classes

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = f"{self.scope_stack[-1]}.{node.name}"
        self.class_stack.append(qualname)
        self.scope_stack.append(qualname)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.generic_visit(node)
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
        root = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name) or root.id not in self.enum_member_roots:
            return None
        status, targets, _, _ = resolve_name(
            node.value, module=self.module, index=self.index, class_stack=self.class_stack
        )
        if status != "resolved" or len(targets) != 1:
            return None
        enum_name = targets[0]
        if enum_name not in self.enum_member_classes:
            return None
        members = self.index.enum_members.get(enum_name)
        return enum_name if members is not None and node.attr in members else None


def collect_references(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    """Run the reference collector over every module and sort the records by id."""
    references: list[RawRecord] = []
    roots = {module.module: unique_direct_module_bindings(module) for module in parsed}
    enum_classes = _enum_member_classes(parsed, index, roots)
    for module in parsed:
        collector = ReferenceCollector(module, index, evidence, roots[module.module], enum_classes)
        collector.visit(module.tree)
        references.extend(collector.items)
    references.sort(key=lambda item: item["id"])
    return references
