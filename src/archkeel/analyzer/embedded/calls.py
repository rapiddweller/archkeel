# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call graph collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, stable_id

from .receiver_types import ReceiverType, annotation_receiver_type, literal_receiver_type
from .records import RawEvidence, RawRecord, classified
from .resolve import SymbolIndex, resolve_name
from .source import FunctionNode, ParsedModule, add_evidence, annotation_text, location, own_scope

_BUILTINS = frozenset(dir(builtins))


def _local_receiver_types(node: FunctionNode) -> dict[str, ReceiverType]:
    """Map each parameter and local this function binds to its known receiver type.

    Reuses the own-scope walk `bindings.py` already defines (via `source.own_scope`) instead
    of a second full traversal of the same body; a literal assignment overwrites an
    annotation the same name carried, the way `contexts.py` already lets a call's context
    win over a bare annotation for the identical precedence question (AD-37).
    """
    receivers: dict[str, ReceiverType] = {}
    arguments = node.args
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        type_name = annotation_receiver_type(annotation_text(argument.annotation))
        if type_name:
            receivers[argument.arg] = ReceiverType(type_name, "annotation")
    for statement in own_scope(node):
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            literal_type = literal_receiver_type(statement.value) if statement.value else None
            if literal_type:
                receivers[statement.target.id] = ReceiverType(literal_type, "literal")
                continue
            annotated_type = annotation_receiver_type(annotation_text(statement.annotation))
            if annotated_type:
                receivers[statement.target.id] = ReceiverType(annotated_type, "annotation")
        elif isinstance(statement, ast.Assign):
            literal_type = literal_receiver_type(statement.value)
            if not literal_type:
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    receivers[target.id] = ReceiverType(literal_type, "literal")
    return receivers


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
        # No enclosing function at module scope, so no receiver is statically typed there.
        self.receiver_stack: list[dict[str, ReceiverType]] = [{}]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = f"{self.scope_stack[-1]}.{node.name}"
        self.class_stack.append(qualname)
        self.scope_stack.append(qualname)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.receiver_stack.append(_local_receiver_types(node))
        self.generic_visit(node)
        self.receiver_stack.pop()
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        expression = annotation_text(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = resolve_name(
            node.func,
            module=self.module,
            index=self.index,
            class_stack=self.class_stack,
            receiver_types=self.receiver_stack[-1],
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
