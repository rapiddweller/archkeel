# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call graph collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, classified, stable_id
from .source import ParsedModule, add_evidence, annotation_text, location

_BUILTINS = frozenset(dir(builtins))


def _dotted_expression(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


class CallCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        symbol_names: set[str],
        method_names: dict[str, list[str]],
        symbol_evidence: dict[str, list[str]],
        evidence: dict[str, RawEvidence],
    ) -> None:
        self.module = module
        self.symbol_names = symbol_names
        self.method_names = method_names
        self.symbol_evidence = symbol_evidence
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [module.module]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
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

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        expression = annotation_text(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = self._resolve(node.func)
        target_evidence_ids = sorted(
            {
                evidence_id
                for target in targets
                for evidence_id in self.symbol_evidence.get(target, [])
            }
        )
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        item_id = stable_id(
            "CALL",
            self.module.rel_path,
            line,
            column,
            expression,
        )
        self.items.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind=f"{status}_call",
                title=f"Call {expression}",
                subjects=[self.scope_stack[-1], *targets],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": self.scope_stack[-1],
                    "source_module": self.module.module,
                    "expression": expression,
                    "status": status,
                    "targets": targets,
                    "candidate_count": candidate_count,
                    "candidates_truncated": candidate_count > len(targets),
                    "reason": reason,
                    "target_evidence_ids": target_evidence_ids,
                },
            )
        )
        self.generic_visit(node)

    def _resolve(self, func: ast.AST) -> tuple[str, list[str], str, int]:
        if isinstance(func, ast.Name):
            local = f"{self.module.module}.{func.id}"
            if local in self.symbol_names:
                return "resolved", [local], "module-local symbol", 1
            binding = self.module.aliases.get(func.id)
            if binding:
                return "resolved", [binding.target], f"imported {binding.kind} binding", 1
            if func.id in _BUILTINS:
                return "resolved", [f"builtins.{func.id}"], "Python builtin", 1
            candidates = self.method_names.get(func.id, [])
            if candidates:
                return (
                    "partially_resolved",
                    candidates[:5],
                    "name matches internal symbols without a proven binding",
                    len(candidates),
                )
            return "unresolved", [], "name has no statically indexed binding", 0

        dotted = _dotted_expression(func)
        if dotted:
            parts = dotted.split(".")
            binding = self.module.aliases.get(parts[0])
            if binding:
                target = ".".join([binding.target, *parts[1:]])
                return "resolved", [target], f"attribute of imported {binding.kind} binding", 1
            if parts[0] == "self" and self.class_stack:
                target = f"{self.class_stack[-1]}.{'.'.join(parts[1:])}"
                if target in self.symbol_names:
                    return "resolved", [target], "method on current class", 1
                return (
                    "partially_resolved",
                    [target],
                    "current-class attribute without indexed method target",
                    1,
                )
            local_class = f"{self.module.module}.{parts[0]}"
            target = f"{local_class}.{'.'.join(parts[1:])}"
            if target in self.symbol_names:
                return "resolved", [target], "class-qualified local method", 1
            candidates = self.method_names.get(parts[-1], [])
            if candidates:
                return (
                    "partially_resolved",
                    candidates[:5],
                    "dynamic receiver with matching internal methods",
                    len(candidates),
                )
            return "unresolved", [], "dynamic attribute receiver", 0
        return "unresolved", [], "call target is a dynamic expression", 0
