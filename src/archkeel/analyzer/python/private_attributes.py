# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only uncertainty for private accesses through unresolved parameter owners."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Sequence

from archkeel.ir.facts import Evidence, EvidenceClass, Record, stable_id
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified, parse_evidence, parse_record

from .source import (
    ParsedModule,
    add_evidence,
    annotation_text,
    attribute_path,
    function_class_owners,
    own_scope,
)

_BUILTIN_NAMES = frozenset(dir(builtins))


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


def _annotation_owner_unknown(
    annotation: ast.AST | None,
    *,
    module: ParsedModule,
    module_aliases: frozenset[str],
    shadowed: frozenset[str],
    module_bindings: frozenset[str],
) -> bool:
    """Return whether the annotation's outer owner cannot be resolved deterministically."""
    if annotation is None:
        return True
    owner = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    qualified = _qualified_name(owner, module, module_aliases)
    root = _qualified_root(owner)
    if qualified in {"typing.Any", "typing_extensions.Any"}:
        return root not in shadowed
    if not isinstance(owner, ast.Name | ast.Attribute):
        return False
    if root in shadowed:
        return False
    return root not in module.aliases and root not in module_bindings and root not in _BUILTIN_NAMES


def _private_parameter_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module: ParsedModule,
    module_aliases: frozenset[str],
    shadowed: frozenset[str],
    module_bindings: frozenset[str],
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
        or _annotation_owner_unknown(
            argument.annotation,
            module=module,
            module_aliases=module_aliases,
            shadowed=shadowed,
            module_bindings=module_bindings,
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
        rooted = attribute_path(node)
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


def _private_attribute_limits(
    modules: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    """Record private attribute access where the parameter's runtime owner is undecidable."""
    records: dict[str, RawRecord] = {}
    for module in modules:
        class_owners = function_class_owners(module.tree, module.module)
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
                module_bindings=module_shadowed,
            )
            if parameters:
                for record in _private_attribute_records(
                    module, function, parameters, class_owners.get(id(function)), evidence
                ):
                    records[record["id"]] = record
    return sorted(records.values(), key=lambda item: item["id"])


def collect_private_attributes(
    modules: Sequence[ParsedModule],
) -> tuple[tuple[Record, ...], tuple[Evidence, ...]]:
    evidence: dict[str, RawEvidence] = {}
    records = _private_attribute_limits(modules, evidence)
    return (
        tuple(parse_record(record) for record in records),
        tuple(parse_evidence(evidence[key]) for key in sorted(evidence)),
    )
