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
from .resolve import SymbolIndex, call_result_type, resolve_name
from .source import FunctionNode, ParsedModule, add_evidence, annotation_text, location, own_scope

_BUILTINS = frozenset(dir(builtins))


def _bind_receiver(
    receivers: dict[str, ReceiverType | None], name: str, candidate: ReceiverType | None
) -> None:
    """Merge one binding of `name` into the running receiver map.

    AD-37 requires every binding of a name to agree before a call on it resolves, so a
    conflicting or untyped binding is remembered as None — permanently voiding the name for
    this function — rather than letting whichever binding is merged first or last win.
    """
    if name not in receivers:
        receivers[name] = candidate
        return
    existing = receivers[name]
    if existing is None or candidate is None or existing.type_name != candidate.type_name:
        receivers[name] = None
        return
    if existing.origin == "literal" or candidate.origin == "literal":
        receivers[name] = ReceiverType(existing.type_name, "literal")


def _void_targets(receivers: dict[str, ReceiverType | None], target: ast.expr) -> None:
    """Void every name a `for`, `with` or unpacking target binds (AD-37 case 3).

    None of these prove a single type the way a literal or an annotation does, and a target
    can nest names inside a tuple or list, so every `Name` under it is walked and voided.
    """
    for child in ast.walk(target):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            _bind_receiver(receivers, child.id, None)


def _value_receiver_type(
    value: ast.expr, module: ParsedModule, receivers: dict[str, ReceiverType | None]
) -> ReceiverType | None:
    """Type an assigned value: a literal proves itself, a call result is documented (AD-40)."""
    literal_type = literal_receiver_type(value)
    if literal_type:
        return ReceiverType(literal_type, "literal")
    if isinstance(value, ast.Call):
        result_type = call_result_type(value, module=module, receiver_types=receivers)
        if result_type:
            return ReceiverType(result_type, "documented")
    return None


def _local_receiver_types(node: FunctionNode, module: ParsedModule) -> dict[str, ReceiverType]:
    """Map each name this function binds to its receiver type, where every binding agrees.

    Reuses the own-scope walk `bindings.py` already defines (via `source.own_scope`) instead
    of a second full traversal of the same body.
    """
    receivers: dict[str, ReceiverType | None] = {}
    arguments = node.args
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        type_name = annotation_receiver_type(annotation_text(argument.annotation))
        if type_name:
            _bind_receiver(receivers, argument.arg, ReceiverType(type_name, "annotation"))
    for statement in own_scope(node):
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            candidate = (
                _value_receiver_type(statement.value, module, receivers)
                if statement.value
                else None
            )
            if candidate is None:
                annotated_type = annotation_receiver_type(annotation_text(statement.annotation))
                candidate = ReceiverType(annotated_type, "annotation") if annotated_type else None
            _bind_receiver(receivers, statement.target.id, candidate)
        elif isinstance(statement, ast.Assign):
            candidate = _value_receiver_type(statement.value, module, receivers)
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    _bind_receiver(receivers, target.id, candidate)
                else:
                    _void_targets(receivers, target)
        elif isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            _bind_receiver(receivers, statement.target.id, None)
        elif isinstance(statement, ast.For | ast.AsyncFor):
            _void_targets(receivers, statement.target)
        elif isinstance(statement, ast.withitem) and statement.optional_vars is not None:
            _void_targets(receivers, statement.optional_vars)
        elif isinstance(statement, ast.NamedExpr):
            _bind_receiver(receivers, statement.target.id, None)
        elif isinstance(statement, ast.ExceptHandler) and statement.name:
            _bind_receiver(receivers, statement.name, None)
    return {name: value for name, value in receivers.items() if value is not None}


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
        self.receiver_stack.append(_local_receiver_types(node, self.module))
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
