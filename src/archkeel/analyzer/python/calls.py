# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call graph collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Sequence

from archkeel.ir.facts import EvidenceClass, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified

from .receiver_types import ReceiverType, annotation_receiver_type, literal_receiver_type
from .resolve import SymbolIndex, call_result_type, dotted_expression, resolve_name
from .scopes import LexicalScopes
from .source import (
    FunctionNode,
    ParsedModule,
    add_evidence,
    annotation_text,
    control_flow_contexts,
    definition_id,
    lexical_binding_names,
    location,
    own_scope,
    stable_direct_module_bindings,
)

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
    value: ast.expr,
    receivers: dict[str, ReceiverType | None],
    scopes: LexicalScopes,
) -> ReceiverType | None:
    """Type an assigned value: a literal proves itself, a call result is documented (AD-40)."""
    literal_type = literal_receiver_type(value)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        if scopes.lookup(value.func, value.func.id).kind != "unbound":
            literal_type = None
    if literal_type:
        return ReceiverType(literal_type, "literal")
    if isinstance(value, ast.Call):
        result_type = call_result_type(value, receiver_types=receivers, scopes=scopes)
        if result_type:
            return ReceiverType(result_type, "documented")
    return None


def _local_receiver_types(node: FunctionNode, scopes: LexicalScopes) -> dict[str, ReceiverType]:
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
        scope = scopes.by_node.get(statement)
        if scope is None or scope.node is not node:
            continue
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            candidate = (
                _value_receiver_type(statement.value, receivers, scopes)
                if statement.value
                else None
            )
            if candidate is None:
                annotated_type = annotation_receiver_type(annotation_text(statement.annotation))
                candidate = ReceiverType(annotated_type, "annotation") if annotated_type else None
            _bind_receiver(receivers, statement.target.id, candidate)
        elif isinstance(statement, ast.Assign):
            candidate = _value_receiver_type(statement.value, receivers, scopes)
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
        self.scopes = LexicalScopes(module)
        self.receivers = {
            node: _local_receiver_types(node, self.scopes)
            for node in ast.walk(module.tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        self.parents = {
            child: parent
            for parent in ast.walk(module.tree)
            for child in ast.iter_child_nodes(parent)
        }
        self.stable_bindings = stable_direct_module_bindings(module)
        self.scope_bindings = {
            node: lexical_binding_names(node)
            for node in ast.walk(module.tree)
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }

    def _construction(
        self, node: ast.Call, expression: str, status: str, targets: list[str], truncated: bool
    ) -> RecordData | None:
        if dotted_expression(node.func) is None:
            return None
        root = expression.split(".")[0]
        child: ast.AST = node
        while child in self.parents:
            parent = self.parents[child]
            if isinstance(
                parent, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
            ):
                return None
            if isinstance(parent, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if child not in parent.body or root in self.scope_bindings[parent]:
                    return None
            child = parent
        classes = [target for target in targets if target in self.index.constructor_results]
        if not classes:
            return None
        proven = (
            isinstance(node.func, ast.Name)
            and status == "resolved"
            and len(classes) == 1
            and root in self.stable_bindings
            and self.index.constructor_results[classes[0]]
        )
        return {
            "status": "resolved" if proven else "partially_resolved",
            "targets": classes,
            "candidates_truncated": truncated,
            "reason": "Stable class with default allocation and initialization"
            if proven
            else "Class call recorded; constructor result type is not proven",
        }

    def _result_bindings(self, node: ast.Call, call_id: str) -> list[RecordData]:
        parent = self.parents.get(node)
        if not isinstance(parent, ast.Assign | ast.AnnAssign) or parent.value is not node:
            return []
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        contexts = [
            {
                "kind": kind,
                "branch": branch,
                "evidence_ids": [add_evidence(self.evidence, self.module, site)],
            }
            for site, kind, branch in control_flow_contexts(parent, self.parents)
        ]
        result: list[RecordData] = []
        for target in targets:
            if not isinstance(target, ast.Name | ast.Attribute | ast.Subscript):
                continue
            name = annotation_text(target) or "<unparseable>"
            line, _, column = location(target)
            legacy_id = definition_id(self.module, parent, f"{self.module.module}.{name}")
            identity = (
                legacy_id
                if (
                    self.scopes.by_node[node] is self.scopes.root
                    and isinstance(target, ast.Name)
                    and legacy_id in self.index.binding_ids
                )
                else stable_id("VALUEBIND", call_id, line, column, name)
            )
            result.append(
                {
                    "id": identity,
                    "name": name,
                    "target_kind": "name"
                    if isinstance(target, ast.Name)
                    else "attribute"
                    if isinstance(target, ast.Attribute)
                    else "subscript",
                    "annotation": annotation_text(parent.annotation)
                    if isinstance(parent, ast.AnnAssign)
                    else None,
                    "initializer": annotation_text(node),
                    "evidence_ids": [add_evidence(self.evidence, self.module, target)],
                    "definition_contexts": contexts,
                }
            )
        return result

    def visit_Call(self, node: ast.Call) -> None:
        scope = self.scopes.by_node[node]
        receivers = {}
        for name in {child.id for child in ast.walk(node.func) if isinstance(child, ast.Name)}:
            owner = self.scopes.lookup(node.func, name).owner
            receiver = (
                self.receivers.get(owner.node, {}).get(name)
                if owner is not None
                and isinstance(owner.node, ast.FunctionDef | ast.AsyncFunctionDef)
                else None
            )
            if receiver is not None:
                receivers[name] = receiver
        expression = annotation_text(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = resolve_name(
            node.func,
            index=self.index,
            scopes=self.scopes,
            receiver_types=receivers,
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
                subjects=[scope.qualified_name, *targets],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": scope.qualified_name,
                    "source_definition_id": scope.definition_id
                    if scope is self.scopes.root or scope.definition_id in self.index.definition_ids
                    else None,
                    "source_module": self.module.module,
                    "expression": expression,
                    "status": status,
                    "targets": targets,
                    "candidate_count": candidate_count,
                    "candidates_truncated": candidate_count > len(targets),
                    "reason": reason,
                    "target_evidence_ids": target_evidence_ids,
                    "result_bindings": self._result_bindings(node, item_id),
                    "construction": self._construction(
                        node, expression, status, targets, candidate_count > len(targets)
                    ),
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
