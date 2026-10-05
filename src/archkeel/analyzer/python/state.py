# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect all class state and ordered function traces without architecture declarations."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Literal

from archkeel.ir.facts import Evidence, Record
from archkeel.ir.facts_codec import RawEvidence, parse_evidence
from archkeel.ir.state_facts import (
    ArgumentPass,
    Assignment,
    AttributeAccess,
    ClassStateFacts,
    FieldState,
    FunctionStateTrace,
    StateEvent,
    StateFacts,
    StateParameter,
)

from .source import (
    ParsedModule,
    add_evidence,
    annotation_text,
    attribute_path,
    decorator_names,
    function_class_owners,
)

_MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "popitem",
    "remove",
    "reverse",
    "setdefault",
    "sort",
    "update",
}


def _field(name: str, frozen: bool, evidence_ids: tuple[str, ...] = ()) -> FieldState:
    return FieldState(
        name, None, "UNKNOWN", "UNKNOWN", "object_immutable" if frozen else "UNKNOWN", evidence_ids
    )


def _annotated_field(field: FieldState, annotation: str | None, evidence_id: str) -> FieldState:
    is_final = annotation is not None and (
        annotation in {"Final", "typing.Final"}
        or annotation.startswith(("Final[", "typing.Final["))
    )
    is_container = annotation is not None and any(
        token in annotation for token in ("list[", "dict[", "set[", "List[", "Dict[", "Set[")
    )
    return replace(
        field,
        annotation=annotation,
        binding="non_reassignable" if is_final else field.binding,
        referent_mutability="mutable_container" if is_container else field.referent_mutability,
        evidence_ids=(evidence_id,),
    )


def _class_state(
    qualified: str,
    node: ast.ClassDef,
    owner: ParsedModule,
    frozen: bool,
    protocol: bool,
    evidence: dict[str, RawEvidence],
) -> ClassStateFacts:
    local_evidence: dict[str, RawEvidence] = {}
    fields: dict[str, FieldState] = {}
    methods: list[str] = []
    properties: dict[str, bool] = {}
    mutable: set[str] = set()
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            fields[child.target.id] = _annotated_field(
                _field(child.target.id, frozen),
                annotation_text(child.annotation),
                add_evidence(local_evidence, owner, child),
            )
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods.append(f"{qualified}.{child.name}")
        decorators = decorator_names(child)
        if "property" in decorators:
            properties[child.name] = False
        for decorator in decorators:
            if decorator.endswith(".setter"):
                properties[decorator.rsplit(".", 1)[0]] = True
        descendants = tuple(ast.walk(child))
        annotated_targets = {
            id(item.target): item for item in descendants if isinstance(item, ast.AnnAssign)
        }
        for descendant in descendants:
            if (
                isinstance(descendant, ast.Attribute)
                and isinstance(descendant.value, ast.Name)
                and descendant.value.id == "self"
            ):
                field = fields.setdefault(descendant.attr, _field(descendant.attr, frozen))
                if not field.evidence_ids:
                    field = replace(
                        field, evidence_ids=(add_evidence(local_evidence, owner, descendant),)
                    )
                parent = annotated_targets.get(id(descendant))
                if parent is not None:
                    field = _annotated_field(
                        field,
                        annotation_text(parent.annotation),
                        add_evidence(local_evidence, owner, parent),
                    )
                fields[descendant.attr] = field
                if isinstance(descendant.ctx, ast.Store) and child.name != "__init__":
                    mutable.add(descendant.attr)
            if isinstance(descendant, ast.Call) and isinstance(descendant.func, ast.Attribute):
                receiver = descendant.func.value
                if (
                    isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                    and descendant.func.attr in _MUTATING_METHODS
                ):
                    mutable.add(receiver.attr)
    for name, has_setter in properties.items():
        fields[name] = replace(
            fields.get(name, _field(name, False)),
            property_assignment="available" if has_setter else "unavailable",
        )
    for name in mutable:
        fields[name] = replace(fields[name], mutability="mutable")
    evidence.update(local_evidence)
    return ClassStateFacts(
        qualified,
        owner.module,
        frozen,
        protocol,
        tuple(fields.values()),
        tuple(methods),
        tuple(sorted(local_evidence)),
    )


def _function_events(
    module: ParsedModule,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    evidence: dict[str, RawEvidence],
) -> tuple[StateEvent, ...]:
    events: list[StateEvent] = []
    nodes = tuple(ast.walk(function))
    parents = {id(child): parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            events.append(
                Assignment(
                    tuple(target.id for target in targets if isinstance(target, ast.Name)),
                    annotation_text(value.func) if isinstance(value, ast.Call) else None,
                    annotation_text(node.annotation) if isinstance(node, ast.AnnAssign) else None,
                    value.id if isinstance(value, ast.Name) else None,
                )
            )
        if isinstance(node, ast.Attribute):
            parent = parents.get(id(node))
            if isinstance(parent, ast.Attribute) and parent.value is node:
                continue
            rooted = attribute_path(node)
            if rooted is None:
                continue
            binding, path = rooted
            access: Literal["read", "write", "mutation"] = (
                "write" if isinstance(node.ctx, (ast.Store, ast.Del)) else "read"
            )
            evidence_node: ast.AST = node
            if (
                isinstance(parent, ast.Call)
                and parent.func is node
                and path[-1] in _MUTATING_METHODS
                and len(path) > 1
            ):
                access = "mutation"
                evidence_node = parent
            events.append(
                AttributeAccess(
                    binding, tuple(path), access, add_evidence(evidence, module, evidence_node)
                )
            )
        if isinstance(node, ast.Call):
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                if isinstance(argument, ast.Name):
                    events.append(
                        ArgumentPass(
                            argument.id,
                            annotation_text(node.func) or "<dynamic>",
                            add_evidence(evidence, module, node),
                        )
                    )
    return tuple(events)


def collect_state(
    modules: Sequence[ParsedModule],
    symbols: Sequence[Record],
    symbol_nodes: Mapping[str, ast.AST],
    symbol_owners: Mapping[ast.AST, ParsedModule],
) -> tuple[StateFacts, tuple[Evidence, ...]]:
    evidence: dict[str, RawEvidence] = {}
    symbols_by_name = {
        name: symbol
        for symbol in symbols
        if isinstance(name := symbol.data.get("qualified_name"), str)
    }
    classes: list[ClassStateFacts] = []
    for qualified, node in symbol_nodes.items():
        owner = symbol_owners.get(node)
        if not isinstance(node, ast.ClassDef) or owner is None:
            continue
        symbol = symbols_by_name.get(qualified)
        classes.append(
            _class_state(
                qualified,
                node,
                owner,
                bool(symbol and symbol.data.get("frozen_object")),
                bool(symbol and symbol.data.get("class_kind") == "protocol"),
                evidence,
            )
        )
    functions: list[FunctionStateTrace] = []
    for module in modules:
        owners = function_class_owners(module.tree, module.module)
        for function in ast.walk(module.tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            class_owner = owners.get(id(function))
            functions.append(
                FunctionStateTrace(
                    f"{class_owner}.{function.name}"
                    if class_owner
                    else f"{module.module}.{function.name}",
                    module.module,
                    class_owner,
                    function.args.args[0].arg if function.args.args else None,
                    tuple(
                        StateParameter(argument.arg, annotation_text(argument.annotation))
                        for argument in [
                            *function.args.posonlyargs,
                            *function.args.args,
                            *function.args.kwonlyargs,
                        ]
                    ),
                    _function_events(module, function, evidence),
                )
            )
    return StateFacts(tuple(classes), tuple(functions)), tuple(
        parse_evidence(evidence[key]) for key in sorted(evidence)
    )
