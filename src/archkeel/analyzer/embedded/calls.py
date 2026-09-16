# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call graph collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, classified, stable_id
from .resolve import SymbolIndex, resolve_name
from .source import ParsedModule, add_evidence, annotation_text, location

_BUILTINS = frozenset(dir(builtins))


class CallCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        index: SymbolIndex,
        evidence: dict[str, RawEvidence],
    ) -> None:
        self.module = module
        self.index = index
        self.symbol_evidence = index.evidence
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [module.module]

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
        expression = annotation_text(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = resolve_name(
            node.func, module=self.module, index=self.index, class_stack=self.class_stack
        )
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


def collect_calls(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    """Run the call collector over every module and sort the records by id."""
    calls: list[RawRecord] = []
    for module in parsed:
        call_collector = CallCollector(module, index, evidence)
        call_collector.visit(module.tree)
        calls.extend(call_collector.items)
    calls.sort(key=lambda item: item["id"])
    return calls
