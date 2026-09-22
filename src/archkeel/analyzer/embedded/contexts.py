# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Context/state evidence collection for the Python architecture scanner."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, stable_id

from .records import RawEvidence, RawRecord, RecordData, classified
from .source import ParsedModule, add_evidence, annotation_text, decorator_names, own_scope

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

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
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

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

    OwnerVisitor().visit(tree)
    return owners


def _module_binding_names(module: ParsedModule) -> frozenset[str]:
    """Names that can shadow an import at module scope; ambiguity fails closed."""
    names: set[str] = set()
    for node in module.tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return frozenset(names)


def _module_scope_aliases(module: ParsedModule) -> frozenset[str]:
    names: set[str] = set()
    for node in module.tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
    return frozenset(names)


def _local_binding_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    names = {argument.arg for argument in function.args.args}
    names.update(argument.arg for argument in function.args.posonlyargs)
    names.update(argument.arg for argument in function.args.kwonlyargs)
    if function.args.vararg is not None:
        names.add(function.args.vararg.arg)
    if function.args.kwarg is not None:
        names.add(function.args.kwarg.arg)
    for node in own_scope(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
    return frozenset(names)


def _class_binding_names(node: ast.ClassDef) -> frozenset[str]:
    names: set[str] = set()
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
        elif isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            names.update(target.id for target in targets if isinstance(target, ast.Name))
        elif isinstance(child, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in child.names if alias.name != "*")
    return frozenset(names)


def _lexical_shadowed_names(tree: ast.Module) -> dict[int, frozenset[str]]:
    shadowed: dict[int, frozenset[str]] = {}
    scopes: list[frozenset[str]] = []

    class ScopeVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            shadowed[id(node)] = frozenset().union(*scopes)
            scopes.append(_local_binding_names(node))
            self.generic_visit(node)
            scopes.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            shadowed[id(node)] = frozenset().union(*scopes)
            scopes.append(_local_binding_names(node))
            self.generic_visit(node)
            scopes.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            scopes.append(_class_binding_names(node))
            self.generic_visit(node)
            scopes.pop()

    ScopeVisitor().visit(tree)
    return shadowed


def _qualified_name(
    node: ast.AST, module: ParsedModule, module_aliases: frozenset[str]
) -> str | None:
    if isinstance(node, ast.Name):
        binding = module.aliases.get(node.id) if node.id in module_aliases else None
        return binding.target if binding is not None else None
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value, module, module_aliases)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _qualified_root(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _annotation_is_any(
    annotation: ast.AST | None,
    *,
    module: ParsedModule,
    module_aliases: frozenset[str],
    shadowed: frozenset[str],
) -> bool:
    if annotation is None:
        return False
    return any(
        _qualified_name(node, module, module_aliases) in {"typing.Any", "typing_extensions.Any"}
        and _qualified_root(node) not in shadowed
        for node in ast.walk(annotation)
    )


def _private_parameter_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module: ParsedModule,
    module_aliases: frozenset[str],
    shadowed: frozenset[str],
) -> dict[str, str]:
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    if function.args.vararg is not None:
        arguments.append(function.args.vararg)
    if function.args.kwarg is not None:
        arguments.append(function.args.kwarg)
    return {
        argument.arg: annotation_text(argument.annotation) or "untyped"
        for argument in arguments
        if argument.arg not in {"self", "cls"}
        if argument.annotation is None
        or _annotation_is_any(
            argument.annotation,
            module=module,
            module_aliases=module_aliases,
            shadowed=shadowed,
        )
    }


def _private_attribute_records(
    module: ParsedModule,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: dict[str, str],
    class_owner: str | None,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    scope = f"{class_owner}.{function.name}" if class_owner else f"{module.module}.{function.name}"
    parents = {
        id(child): parent
        for parent in own_scope(function)
        for child in ast.iter_child_nodes(parent)
    }
    records: list[RawRecord] = []
    for node in own_scope(function):
        if not isinstance(node, ast.Attribute):
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.Attribute) and parent.value is node:
            continue
        rooted = _attribute_path(node)
        if rooted is None or rooted[0] not in parameters:
            continue
        parameter, path = rooted
        private = next((name for name in path if name.startswith("_")), None)
        if private is None:
            continue
        annotation = parameters[parameter]
        evidence_id = add_evidence(evidence, module, node)
        item_id = stable_id(
            "UNKNOWN-PRIVATE-ATTRIBUTE",
            module.rel_path,
            scope,
            parameter,
            private,
            *path,
            evidence_id,
        )
        records.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.UNKNOWN,
                area="type_architecture",
                kind="private_attribute_access_limit",
                title=f"{scope} accesses {private} through untyped parameter {parameter}",
                subjects=[scope, parameter, private],
                evidence_ids=[evidence_id],
                data={
                    "function": scope,
                    "parameter": parameter,
                    "annotation": annotation,
                    "attribute": private,
                    "path": ".".join(path),
                    "reason": "The parameter's runtime component owner is unknown.",
                },
            )
        )
    return records


def private_attribute_limits(
    modules: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    """Record private attribute access where the parameter's runtime owner is undecidable."""
    records: dict[str, RawRecord] = {}
    for module in modules:
        class_owners = _function_class_owners(module.tree, module.module)
        module_aliases = _module_scope_aliases(module)
        module_shadowed = _module_binding_names(module)
        lexical_shadowed = _lexical_shadowed_names(module.tree)
        functions = [
            node
            for node in ast.walk(module.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            parameters = _private_parameter_names(
                function,
                module=module,
                module_aliases=module_aliases,
                shadowed=(
                    module_shadowed
                    | lexical_shadowed.get(id(function), frozenset())
                    | _local_binding_names(function)
                ),
            )
            if parameters:
                for record in _private_attribute_records(
                    module, function, parameters, class_owners.get(id(function)), evidence
                ):
                    records[record["id"]] = record
    return sorted(records.values(), key=lambda item: item["id"])


def _access_observations(
    modules: Sequence[ParsedModule],
    calls: Sequence[RawRecord],
    roots: set[str],
    context_names: dict[str, str],
    evidence: dict[str, RawEvidence],
) -> dict[str, dict[str, list[RecordData]]]:
    observations: dict[str, dict[str, list[RecordData]]] = {
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
    return observations


def _annotation_binding(annotation: str | None) -> tuple[str | None, str | None]:
    """Classify Final and mutable-container annotations shared by class and self.x fields."""
    if not annotation:
        return None, None
    is_final = annotation in {"Final", "typing.Final"} or annotation.startswith(
        ("Final[", "typing.Final[")
    )
    is_container = any(
        token in annotation for token in ("list[", "dict[", "set[", "List[", "Dict[", "Set[")
    )
    binding = "non_reassignable" if is_final else None
    referent = "mutable_container" if is_container else None
    return binding, referent


def _class_fields(
    root: str,
    context_node: ast.ClassDef,
    owner: ParsedModule,
    frozen: bool,
    evidence: dict[str, RawEvidence],
) -> tuple[dict[str, RecordData], list[str]]:
    fields: dict[str, RecordData] = {}
    methods: list[str] = []
    properties: dict[str, bool] = {}
    assignments_after_init: set[str] = set()
    mutations: set[str] = set()
    for child in context_node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            annotation = annotation_text(child.annotation)
            binding, referent = _annotation_binding(annotation)
            fields[child.target.id] = {
                "name": child.target.id,
                "annotation": annotation,
                "binding": binding or "UNKNOWN",
                "referent_mutability": referent or "UNKNOWN",
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
                        field_data["evidence_ids"] = [add_evidence(evidence, owner, descendant)]
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
                        binding, referent = _annotation_binding(annotation)
                        field_data["binding"] = binding or field_data["binding"]
                        field_data["referent_mutability"] = (
                            referent or field_data["referent_mutability"]
                        )
                        field_data["evidence_ids"] = [add_evidence(evidence, owner, parent)]
                    if isinstance(descendant.ctx, ast.Store) and child.name != "__init__":
                        assignments_after_init.add(descendant.attr)
                if isinstance(descendant, ast.Call) and isinstance(descendant.func, ast.Attribute):
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
    for name in assignments_after_init | mutations:
        fields[name]["mutability"] = "mutable"
    return fields, methods


def _field_detail_records(root: str, fields: dict[str, RecordData]) -> list[RawRecord]:
    records: list[RawRecord] = []
    for field_data in sorted(fields.values(), key=lambda value: value["name"]):
        records.append(
            classified(
                item_id=stable_id("CONTEXT-FIELD", root, field_data["name"]),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_field",
                title=f"{root}.{field_data['name']}",
                subjects=[root, field_data["name"]],
                evidence_ids=field_data["evidence_ids"],
                data={"context": root, **field_data},
            )
        )
    return records


def _access_detail_records(
    root: str, accesses: dict[str, list[RecordData]]
) -> list[tuple[str, RawRecord]]:
    access_kinds = {
        "reads": "context_read",
        "writes": "context_write",
        "passes": "context_pass",
        "constructed_by": "context_construction",
    }
    records: list[tuple[str, RawRecord]] = []
    for category, kind in access_kinds.items():
        for entry in accesses[category]:
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
            records.append((category, item))
    return records


def _dependency_detail_records(
    root: str, owner: ParsedModule | None, imports: Sequence[RawRecord]
) -> list[RawRecord]:
    dependencies = sorted(
        {
            item["data"]["target_module"]
            for item in imports
            if owner is not None
            and item["data"]["source_module"] == owner.module
            and item["data"]["target_module"] != owner.module
        }
    )
    records: list[RawRecord] = []
    for dependency in dependencies:
        import_facts = [
            item["id"]
            for item in imports
            if owner is not None
            and item["data"]["source_module"] == owner.module
            and item["data"]["target_module"] == dependency
        ]
        records.append(
            classified(
                item_id=stable_id("CONTEXT-DEP", root, dependency),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_dependency",
                title=f"{root} depends on {dependency}",
                subjects=[root, dependency],
                fact_ids=import_facts,
                data={"context": root, "target_module": dependency},
            )
        )
    return records


def _detail_records(
    root: str,
    owner: ParsedModule | None,
    fields: dict[str, RecordData],
    accesses: dict[str, list[RecordData]],
    imports: Sequence[RawRecord],
) -> tuple[list[RawRecord], dict[str, list[str]]]:
    detail_records: list[RawRecord] = []
    detail_ids: dict[str, list[str]] = {
        "fields": [],
        "reads": [],
        "writes": [],
        "passes": [],
        "constructed_by": [],
        "dependencies": [],
    }
    field_records = _field_detail_records(root, fields)
    detail_records.extend(field_records)
    detail_ids["fields"] = [item["id"] for item in field_records]
    for category, item in _access_detail_records(root, accesses):
        detail_records.append(item)
        detail_ids[category].append(item["id"])
    dependency_records = _dependency_detail_records(root, owner, imports)
    detail_records.extend(dependency_records)
    detail_ids["dependencies"] = [item["id"] for item in dependency_records]
    return detail_records, detail_ids


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
    observations = _access_observations(modules, calls, roots, context_names, evidence)

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
        fields: dict[str, RecordData] = {}
        methods: list[str] = []
        if isinstance(context_node, ast.ClassDef) and owner is not None:
            frozen = bool(symbol and symbol["data"].get("frozen_object"))
            fields, methods = _class_fields(root, context_node, owner, frozen, evidence)

        detail_records, detail_ids = _detail_records(
            root, owner, fields, observations[root], imports
        )

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
