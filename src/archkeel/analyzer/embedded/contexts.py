# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Context/state evidence collection for the Python architecture scanner."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from typing import Any

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, classified, stable_id
from .source import ParsedModule, add_evidence, annotation_text, decorator_names

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


def _context_simple_name(annotation: str | None, context_names: dict[str, str]) -> str | None:
    if not annotation:
        return None
    normalized = annotation.replace('"', "").replace("'", "")
    for simple, qualified in context_names.items():
        if simple in normalized:
            return qualified
    return None


def _attribute_path(node: ast.Attribute) -> tuple[str, list[str]] | None:
    attributes: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        attributes.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    return current.id, list(reversed(attributes))


def _function_class_owners(tree: ast.Module, module_name: str) -> dict[int, str]:
    owners: dict[int, str] = {}

    class OwnerVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            qualified = (
                f"{self.stack[-1]}.{node.name}" if self.stack else f"{module_name}.{node.name}"
            )
            self.stack.append(qualified)
            self.generic_visit(node)
            self.stack.pop()

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            if self.stack:
                owners[id(node)] = self.stack[-1]
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

    OwnerVisitor().visit(tree)
    return owners


def collect_contexts(
    modules: Sequence[ParsedModule],
    symbols: Sequence[RawRecord],
    symbol_nodes: dict[str, ast.AST],
    symbol_owners: dict[str, ParsedModule],
    imports: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    declared_roots: Sequence[str],
    evidence: dict[str, RawEvidence],
) -> tuple[list[RawRecord], list[RawRecord]]:
    class_symbols = [item for item in symbols if item["kind"] == "class"]
    roots = set(declared_roots)
    for item in class_symbols:
        qualified = item["data"]["qualified_name"]
        if item["data"]["name"].endswith(("Context", "State")):
            roots.add(qualified)
    context_names = {name.rsplit(".", 1)[-1]: name for name in sorted(roots)}
    observations: dict[str, dict[str, list[dict[str, Any]]]] = {
        root: {"reads": [], "writes": [], "passes": [], "constructed_by": []} for root in roots
    }

    call_evidence = {call["id"]: call["evidence_ids"] for call in calls}
    for call in calls:
        for target in call["data"]["targets"]:
            if target in roots:
                observations[target]["constructed_by"].append(
                    {
                        "source": call["data"]["source_scope"],
                        "call_id": call["id"],
                        "evidence_ids": call_evidence[call["id"]],
                    }
                )

    for module in modules:
        class_owners = _function_class_owners(module.tree, module.module)
        functions = [
            node
            for node in ast.walk(module.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            bindings: dict[str, str] = {}
            class_owner = class_owners.get(id(function))
            if class_owner in roots and function.args.args:
                bindings[function.args.args[0].arg] = class_owner
            for argument in [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]:
                argument_context = _context_simple_name(
                    annotation_text(argument.annotation), context_names
                )
                if argument_context:
                    bindings[argument.arg] = argument_context
            scope = (
                f"{class_owner}.{function.name}"
                if class_owner
                else f"{module.module}.{function.name}"
            )
            parents = {
                id(child): parent
                for parent in ast.walk(function)
                for child in ast.iter_child_nodes(parent)
            }
            for node in ast.walk(function):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    assigned_context: str | None = None
                    if isinstance(value, ast.Call):
                        called = annotation_text(value.func)
                        assigned_context = _context_simple_name(called, context_names)
                    if isinstance(node, ast.AnnAssign):
                        assigned_context = assigned_context or _context_simple_name(
                            annotation_text(node.annotation), context_names
                        )
                    if isinstance(value, ast.Name):
                        assigned_context = assigned_context or bindings.get(value.id)
                    if assigned_context:
                        for target in targets:
                            if isinstance(target, ast.Name):
                                bindings[target.id] = assigned_context
                if isinstance(node, ast.Attribute):
                    parent = parents.get(id(node))
                    if isinstance(parent, ast.Attribute) and parent.value is node:
                        continue
                    rooted = _attribute_path(node)
                    if rooted is None or rooted[0] not in bindings:
                        continue
                    binding, path = rooted
                    bound_context = bindings[binding]
                    access = "write" if isinstance(node.ctx, (ast.Store, ast.Del)) else "read"
                    field_path = path
                    if (
                        isinstance(parent, ast.Call)
                        and parent.func is node
                        and path[-1] in _MUTATING_METHODS
                        and len(path) > 1
                    ):
                        access = "mutation"
                        field_path = path[:-1]
                    kind = "writes" if access in {"write", "mutation"} else "reads"
                    rendered_path = ".".join(field_path)
                    evidence_node = (
                        parent if access == "mutation" and isinstance(parent, ast.Call) else node
                    )
                    evidence_id = add_evidence(evidence, module, evidence_node)
                    observations[bound_context][kind].append(
                        {
                            "source": scope,
                            "field": field_path[0],
                            "path": rendered_path,
                            "access": access,
                            "evidence_ids": [evidence_id],
                        }
                    )
                if isinstance(node, ast.Call):
                    for call_argument in [
                        *node.args,
                        *(keyword.value for keyword in node.keywords),
                    ]:
                        if isinstance(call_argument, ast.Name) and call_argument.id in bindings:
                            passed_context = bindings[call_argument.id]
                            evidence_id = add_evidence(evidence, module, node)
                            observations[passed_context]["passes"].append(
                                {
                                    "source": scope,
                                    "target": annotation_text(node.func) or "<dynamic>",
                                    "evidence_ids": [evidence_id],
                                }
                            )

    result: list[RawRecord] = []
    all_detail_records: list[RawRecord] = []
    symbol_by_qname = {item["data"]["qualified_name"]: item for item in symbols}
    context_class_labels = {
        "declared_root": "DECLARED ROOT",
        "runtime_subscope": "RUNTIME SUB-SCOPE",
        "type_protocol_contract": "TYPE / PROTOCOL CONTRACT",
        "local_domain_state_candidate": "LOCAL / DOMAIN STATE CANDIDATE",
        "unknown_context_like_type": "UNKNOWN CONTEXT-LIKE TYPE",
    }
    for root in sorted(roots):
        symbol = symbol_by_qname.get(root)
        context_node = symbol_nodes.get(root)
        owner = symbol_owners.get(root)
        if root in declared_roots:
            context_class = "declared_root"
        elif symbol and symbol["data"].get("class_kind") == "protocol":
            context_class = "type_protocol_contract"
        else:
            context_class = "local_domain_state_candidate"
        fields: dict[str, dict[str, Any]] = {}
        methods: list[str] = []
        if isinstance(context_node, ast.ClassDef) and owner is not None:
            frozen = bool(symbol and symbol["data"].get("frozen_object"))
            properties: dict[str, bool] = {}
            assignments_after_init: set[str] = set()
            mutations: set[str] = set()
            for child in context_node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    annotation = annotation_text(child.annotation)
                    final_binding = bool(
                        annotation
                        and (
                            annotation in {"Final", "typing.Final"}
                            or annotation.startswith(("Final[", "typing.Final["))
                        )
                    )
                    referent = (
                        "mutable_container"
                        if annotation
                        and any(
                            token in annotation
                            for token in ("list[", "dict[", "set[", "List[", "Dict[", "Set[")
                        )
                        else "UNKNOWN"
                    )
                    fields[child.target.id] = {
                        "name": child.target.id,
                        "annotation": annotation,
                        "binding": "non_reassignable" if final_binding else "UNKNOWN",
                        "referent_mutability": referent,
                        "mutability": "object_immutable" if frozen else "UNKNOWN",
                        "evidence_ids": [add_evidence(evidence, owner, child)],
                    }
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(f"{root}.{child.name}")
                    decorator_list = decorator_names(child)
                    if "property" in decorator_list:
                        properties[child.name] = False
                    for decorator in decorator_list:
                        if decorator.endswith(".setter"):
                            properties[decorator.rsplit(".", 1)[0]] = True
                    for descendant in ast.walk(child):
                        if (
                            isinstance(descendant, ast.Attribute)
                            and isinstance(descendant.value, ast.Name)
                            and descendant.value.id == "self"
                        ):
                            field_data = fields.setdefault(
                                descendant.attr,
                                {
                                    "name": descendant.attr,
                                    "annotation": None,
                                    "binding": "UNKNOWN",
                                    "referent_mutability": "UNKNOWN",
                                    "mutability": "object_immutable" if frozen else "UNKNOWN",
                                    "evidence_ids": [],
                                },
                            )
                            if not field_data["evidence_ids"]:
                                field_data["evidence_ids"] = [
                                    add_evidence(evidence, owner, descendant)
                                ]
                            parent = next(
                                (
                                    candidate
                                    for candidate in ast.walk(child)
                                    if isinstance(candidate, ast.AnnAssign)
                                    and candidate.target is descendant
                                ),
                                None,
                            )
                            if isinstance(parent, ast.AnnAssign):
                                annotation = annotation_text(parent.annotation)
                                field_data["annotation"] = annotation
                                field_data["binding"] = (
                                    "non_reassignable"
                                    if annotation
                                    and (
                                        annotation in {"Final", "typing.Final"}
                                        or annotation.startswith(("Final[", "typing.Final["))
                                    )
                                    else field_data["binding"]
                                )
                                field_data["referent_mutability"] = (
                                    "mutable_container"
                                    if annotation
                                    and any(
                                        token in annotation
                                        for token in (
                                            "list[",
                                            "dict[",
                                            "set[",
                                            "List[",
                                            "Dict[",
                                            "Set[",
                                        )
                                    )
                                    else field_data["referent_mutability"]
                                )
                                field_data["evidence_ids"] = [add_evidence(evidence, owner, parent)]
                            if isinstance(descendant.ctx, ast.Store) and child.name != "__init__":
                                assignments_after_init.add(descendant.attr)
                        if isinstance(descendant, ast.Call) and isinstance(
                            descendant.func, ast.Attribute
                        ):
                            receiver = descendant.func.value
                            if (
                                isinstance(receiver, ast.Attribute)
                                and isinstance(receiver.value, ast.Name)
                                and receiver.value.id == "self"
                                and descendant.func.attr in _MUTATING_METHODS
                            ):
                                mutations.add(receiver.attr)
            for name, has_setter in properties.items():
                field_data = fields.setdefault(
                    name,
                    {
                        "name": name,
                        "annotation": None,
                        "binding": "UNKNOWN",
                        "referent_mutability": "UNKNOWN",
                        "mutability": "UNKNOWN",
                        "evidence_ids": [],
                    },
                )
                field_data["property_assignment"] = "available" if has_setter else "unavailable"
                if not has_setter and field_data["referent_mutability"] == "UNKNOWN":
                    field_data["referent_mutability"] = "UNKNOWN"
            for name in assignments_after_init | mutations:
                fields[name]["mutability"] = "mutable"

        detail_records: list[RawRecord] = []
        detail_ids: dict[str, list[str]] = {
            "fields": [],
            "reads": [],
            "writes": [],
            "passes": [],
            "constructed_by": [],
            "dependencies": [],
        }
        for field_data in sorted(fields.values(), key=lambda value: value["name"]):
            item = classified(
                item_id=stable_id("CONTEXT-FIELD", root, field_data["name"]),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_field",
                title=f"{root}.{field_data['name']}",
                subjects=[root, field_data["name"]],
                evidence_ids=field_data["evidence_ids"],
                data={"context": root, **field_data},
            )
            detail_records.append(item)
            detail_ids["fields"].append(item["id"])
        access_kinds = {
            "reads": "context_read",
            "writes": "context_write",
            "passes": "context_pass",
            "constructed_by": "context_construction",
        }
        for category, kind in access_kinds.items():
            for entry in observations[root][category]:
                call_id = entry.get("call_id")
                item = classified(
                    item_id=stable_id(
                        "CONTEXT-ACCESS",
                        root,
                        category,
                        entry.get("source"),
                        entry.get("field"),
                        entry.get("path"),
                        entry.get("target"),
                        *(entry.get("evidence_ids") or []),
                    ),
                    evidence_class=EvidenceClass.FACT,
                    area="contexts_state",
                    kind=kind,
                    title=(
                        f"{entry.get('source')} {category.replace('_', ' ')} "
                        f"{entry.get('path') or entry.get('target') or root}"
                    ),
                    subjects=[root, entry.get("source", ""), entry.get("target", "")],
                    evidence_ids=entry.get("evidence_ids", []),
                    fact_ids=[call_id] if call_id else [],
                    data={"context": root, "category": category, **entry},
                )
                detail_records.append(item)
                detail_ids[category].append(item["id"])
        dependencies = sorted(
            {
                item["data"]["target_module"]
                for item in imports
                if owner is not None
                and item["data"]["source_module"] == owner.module
                and item["data"]["target_module"] != owner.module
            }
        )
        for dependency in dependencies:
            import_facts = [
                item["id"]
                for item in imports
                if owner is not None
                and item["data"]["source_module"] == owner.module
                and item["data"]["target_module"] == dependency
            ]
            item = classified(
                item_id=stable_id("CONTEXT-DEP", root, dependency),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_dependency",
                title=f"{root} depends on {dependency}",
                subjects=[root, dependency],
                fact_ids=import_facts,
                data={"context": root, "target_module": dependency},
            )
            detail_records.append(item)
            detail_ids["dependencies"].append(item["id"])

        detail_records = sorted(
            {item["id"]: item for item in detail_records}.values(), key=lambda item: item["id"]
        )
        detail_ids = {key: sorted(set(value)) for key, value in detail_ids.items()}
        evidence_ids = symbol["evidence_ids"] if symbol else []
        all_detail_records.extend(detail_records)
        result.append(
            classified(
                item_id=stable_id("CONTEXT", root),
                evidence_class=EvidenceClass.FACT if symbol else EvidenceClass.UNKNOWN,
                area="contexts_state",
                kind="context_topology" if symbol else "declared_context_not_observed",
                title=root,
                subjects=[root],
                evidence_ids=evidence_ids,
                fact_ids=([symbol["id"]] if symbol else [])
                + [item["id"] for item in detail_records],
                data={
                    "qualified_name": root,
                    "declared_root": root in declared_roots,
                    "context_class": context_class,
                    "context_class_label": context_class_labels[context_class],
                    "methods": sorted(methods),
                    **{key: sorted(value) for key, value in detail_ids.items()},
                },
            )
        )
    return sorted(result, key=lambda item: item["id"]), sorted(
        all_detail_records, key=lambda item: item["id"]
    )
