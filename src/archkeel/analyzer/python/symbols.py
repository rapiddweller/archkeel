# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Class and function symbol collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import sys
from collections.abc import Sequence
from types import EllipsisType

from archkeel.ir.facts import EvidenceClass, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified

from .resolve import dotted_expression
from .source import (
    DATACLASS_DECORATORS,
    DefinitionContexts,
    ParsedModule,
    add_evidence,
    annotation_text,
    class_header_static,
    decorator_names,
    definition_id,
    definition_sites,
    is_static_type_alias_value,
    location,
    module_scope_bindings,
    property_bindings,
    stable_direct_module_bindings,
    unproven_class_body,
    unproven_member_bindings,
)
from .source import (
    binding_may_exist_before as _binding_may_exist_before,
)
from .source import (
    is_proven_decorator as _is_proven_decorator,
)
from .source import (
    method_decorator_data as _method_decorator_data,
)
from .source import (
    resolve_static_name as _resolve_static_name,
)

_BUILTIN_NAMES = frozenset(dir(builtins))
_KNOWN_CLASS_KINDS = {
    "typing.Protocol": "protocol",
    "typing_extensions.Protocol": "protocol",
    "enum.Enum": "enum",
    "enum.IntEnum": "enum",
    "enum.StrEnum": "enum",
    "pydantic.BaseModel": "pydantic_model",
}


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> RecordData:
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + node.args.defaults
    parameters = [
        _parameter(
            argument,
            "positional_only" if index < len(node.args.posonlyargs) else "positional",
            defaults[index],
        )
        for index, argument in enumerate(positional)
    ]
    if node.args.vararg:
        parameters.append(_parameter(node.args.vararg, "varargs", None, "*"))
    parameters.extend(
        _parameter(argument, "keyword_only", default)
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
    )
    if node.args.kwarg:
        parameters.append(_parameter(node.args.kwarg, "kwargs", None, "**"))
    return {
        "parameters": parameters,
        "receiver_parameter": positional[0].arg if positional else None,
        "returns": annotation_text(node.returns),
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def _parameter(
    argument: ast.arg, kind: str, default: ast.expr | None, prefix: str = ""
) -> RecordData:
    return {
        "name": prefix + argument.arg,
        "annotation": annotation_text(argument.annotation),
        "kind": kind,
        "default": annotation_text(default),
        "default_known": True,
    }


def _python_visibility(name: str) -> RecordData:
    special = name.startswith("__") and name.endswith("__") and len(name) > 4
    return {
        "kind": "private" if name.startswith("_") and not special else "public",
        "basis": "convention",
        "spelling": name,
    }


def _class_attribute_declarations(
    node: ast.ClassDef, module: ParsedModule, evidence: dict[str, RawEvidence]
) -> list[RecordData]:
    """Keep private annotations for UML without widening AD-70's public API inventory."""
    return [
        {
            "name": child.target.id,
            "annotation": annotation_text(child.annotation),
            "visibility": _python_visibility(child.target.id),
            "definition_id": stable_id("ATTR", module.rel_path, *location(child), child.target.id),
            "evidence_ids": [add_evidence(evidence, module, child)],
        }
        for child in node.body
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
    ]


def _class_member_names(node: ast.ClassDef) -> list[str]:
    """Names bound directly in a class body, including non-method overrides."""
    names: set[str] = set()
    deleted: set[str] = set()
    for child in node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(child.name)
        elif isinstance(child, ast.AnnAssign | ast.Assign) and (
            not isinstance(child, ast.AnnAssign) or child.value is not None
        ):
            targets = [child.target] if isinstance(child, ast.AnnAssign) else child.targets
            names.update(
                item.id
                for target in targets
                for item in ast.walk(target)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
            )
        elif isinstance(child, ast.Import):
            names.update(alias.asname or alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in child.names if alias.name != "*")
        elif isinstance(child, ast.Delete):
            deleted.update(target.id for target in child.targets if isinstance(target, ast.Name))
    return sorted(names - deleted)


def _shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    """Digest the body's node types in walk order, dropping every name and literal value.

    Two functions share a shape when they have the same structure, so a renamed copy still
    matches its original (AD-30). Operators are node types of their own, so `a + b` and
    `a * b` stay apart. How small a shape may be before it carries no information is the
    derivation's decision, which is why the node count travels with the digest.
    """
    body = node.body
    # A docstring documents the logic instead of being part of it, exactly as body_is_empty
    # reads it: counting it would let one sentence of prose disguise a copy.
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    kinds = [type(child).__name__ for statement in body for child in ast.walk(statement)]
    return hashlib.sha256("\n".join(kinds).encode()).hexdigest()[:16], len(kinds)


def _class_is_frozen(
    node: ast.ClassDef, module: ParsedModule, *, allow_pydantic: bool = False
) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = _resolve_static_name(module, decorator.func)
        if name in DATACLASS_DECORATORS and any(
            keyword.arg == "frozen"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        ):
            return True
    if not allow_pydantic:
        return False
    for child in node.body:
        if not isinstance(child, (ast.Assign, ast.AnnAssign)):
            continue
        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
        value = child.value
        if not any(
            isinstance(target, ast.Name) and target.id == "model_config" for target in targets
        ):
            continue
        if (
            isinstance(value, ast.Call)
            and _resolve_static_name(module, value.func) == "pydantic.ConfigDict"
            and any(
                keyword.arg == "frozen"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in value.keywords
            )
        ):
            return True
    return False


def _symbol_data(
    module: ParsedModule,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    qualname: str,
    parent: str | None,
    parent_node: ast.ClassDef | None = None,
    *,
    evidence: dict[str, RawEvidence],
) -> RecordData:
    data: RecordData = {
        "qualified_name": qualname,
        "module": module.module,
        "package": module.package,
        "name": node.name,
        "visibility": "private" if node.name.startswith("_") else "public_name",
        "visibility_detail": _python_visibility(node.name),
        "declared_in_all": node.name in module.all_exports,
        "parent": parent,
        "decorators": decorator_names(node),
    }
    if isinstance(node, ast.ClassDef):
        data.update(_class_symbol_data(module, node, evidence))
        if data["source_binding_unique"] is True and (
            properties := property_bindings(module, node)
        ):
            data["property_members"] = sorted({method.name for method in properties})
    else:
        data.update(_function_signature(node))
        data["symbol_category"] = "method" if parent_node else "function"
        data["overload_signature"] = any(
            _is_proven_decorator(
                module,
                decorator,
                node,
                parent_node,
                frozenset({"typing.overload", "typing_extensions.overload"}),
            )
            for decorator in node.decorator_list
        )
        if parent_node:
            data.update(_method_decorator_data(module, node, parent_node))
        shape, shape_nodes = _shape(node)
        data["shape"] = shape
        data["shape_nodes"] = shape_nodes
    return data


def _class_symbol_data(
    module: ParsedModule, node: ast.ClassDef, evidence: dict[str, RawEvidence]
) -> RecordData:
    attributes = _class_attribute_declarations(node, module, evidence)
    generic_parameters = _generic_parameters(module, node)
    generic_bases = _generic_bases(node)
    return {
        "bases": sorted(filter(None, (annotation_text(base) for base in node.bases))),
        "base_roots": _class_bases(module, node),
        "frozen_object": _class_is_frozen(node, module),
        "symbol_category": "class",
        "fields": [
            {"name": item["name"], "annotation": item["annotation"]}
            for item in attributes
            if not item["name"].startswith("_")
        ],
        "attribute_declarations": attributes,
        "source_binding_unique": node in module.tree.body
        and node.name in stable_direct_module_bindings(module),
        "source_member_binding_static": node.name not in unproven_member_bindings(module),
        "class_header_static": class_header_static(node),
        "class_members": _class_member_names(node),
        "class_body_control_flow": any(
            isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.Try,
                    ast.TryStar,
                    ast.Match,
                ),
            )
            for child in node.body
        )
        or unproven_class_body(module, node),
        **({"generic_parameters": generic_parameters} if generic_parameters else {}),
        **({"generic_bases": generic_bases} if generic_bases else {}),
    }


def _annotation_binding_uncertainties(
    module: ParsedModule,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.ClassDef | None,
) -> dict[str, list[str]]:
    """Keep class/generic lookup uncertainty instead of assuming the module binding wins."""
    annotations: list[tuple[str, ast.expr | None, ast.stmt]]
    scope: ast.ClassDef | None
    if isinstance(node, ast.ClassDef):
        scope = node
        annotations = [
            (child.target.id, child.annotation, child)
            for child in node.body
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
        ]
    else:
        scope = parent
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        annotations = [(argument.arg, argument.annotation, node) for argument in arguments]
        if node.args.vararg:
            annotations.append((f"*{node.args.vararg.arg}", node.args.vararg.annotation, node))
        if node.args.kwarg:
            annotations.append((f"**{node.args.kwarg.arg}", node.args.kwarg.annotation, node))
        annotations.append(("return", node.returns, node))
    generic_names = {
        value
        for owner in (node, scope)
        if owner is not None
        for field, parameters in ast.iter_fields(owner)
        if field == "type_params"
        for parameter in parameters
        for name, value in ast.iter_fields(parameter)
        if name == "name"
    }
    deferred = any(
        isinstance(child, ast.ImportFrom)
        and child.module == "__future__"
        and any(alias.name == "annotations" for alias in child.names)
        for child in module.tree.body
    )
    uncertain: dict[str, list[str]] = {}
    for position, annotation, statement in annotations:
        if annotation is None:
            continue
        names = {child.id for child in ast.walk(annotation) if isinstance(child, ast.Name)}
        shadowed = sorted(
            name
            for name in names
            if name in generic_names
            or (
                scope is not None
                and (
                    _binding_may_exist_before(scope.body, None if deferred else statement, name)
                    or (
                        isinstance(statement, ast.AnnAssign)
                        and statement.value is not None
                        and isinstance(statement.target, ast.Name)
                        and statement.target.id == name
                    )
                )
            )
        )
        if shadowed:
            uncertain[position] = shadowed
    return uncertain


def _bound_once_before(statements: Sequence[ast.stmt], stop: ast.AST, name: str) -> bool:
    """Prove one direct module binding exists before a class definition."""
    count = 0
    for statement in statements:
        if statement is stop:
            return count == 1
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bindings = [statement.name]
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            if isinstance(statement, ast.ImportFrom) and any(
                alias.name == "*" for alias in statement.names
            ):
                return False
            bindings = [
                alias.asname
                or (alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name)
                for alias in statement.names
            ]
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            bindings = [
                child.id
                for target in targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            ]
        else:
            if any(
                isinstance(child, ast.Name)
                and child.id == name
                and isinstance(child.ctx, ast.Store | ast.Del)
                for child in ast.walk(statement)
            ):
                return False
            continue
        count += bindings.count(name)
        if count > 1:
            return False
    return False


def _generic_parameters(module: ParsedModule, node: ast.ClassDef) -> list[str]:
    """Return verified TypeVars from one explicit ``Generic[...]`` base."""
    typevars: set[str] = set()
    for statement in module.tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        value = statement.value
        if not isinstance(value, ast.Call):
            continue
        typevar_root = (
            value.func.id
            if isinstance(value.func, ast.Name)
            else value.func.value.id
            if isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name)
            else None
        )
        if (
            not isinstance(typevar_root, str)
            or not _bound_once_before(module.tree.body, statement, typevar_root)
            or _resolve_static_name(module, value.func)
            not in {"typing.TypeVar", "typing_extensions.TypeVar"}
            or not value.args
            or not isinstance(value.args[0], ast.Constant)
            or value.args[0].value != name
            or not _bound_once_before(module.tree.body, node, name)
        ):
            continue
        typevars.add(name)

    generic_bases = [
        base
        for base in node.bases
        if isinstance(base, ast.Subscript)
        and _resolve_static_name(module, base.value)
        in {"typing.Generic", "typing_extensions.Generic"}
    ]
    if len(generic_bases) != 1:
        return []
    root = generic_bases[0].value
    root_name = (
        root.id
        if isinstance(root, ast.Name)
        else root.value.id
        if isinstance(root, ast.Attribute) and isinstance(root.value, ast.Name)
        else None
    )
    if not isinstance(root_name, str) or not _bound_once_before(module.tree.body, node, root_name):
        return []
    arguments = generic_bases[0].slice
    values = list(arguments.elts) if isinstance(arguments, ast.Tuple) else [arguments]
    names = [value.id for value in values if isinstance(value, ast.Name)]
    if len(names) != len(values) or len(set(names)) != len(names) or not set(names) <= typevars:
        return []
    return names


def _generic_bases(node: ast.ClassDef) -> list[RecordData]:
    """Keep one resolvable spelling and its explicit type arguments for each generic base."""
    bases: list[RecordData] = []
    for base in node.bases:
        if not isinstance(base, ast.Subscript):
            continue
        arguments = list(base.slice.elts) if isinstance(base.slice, ast.Tuple) else [base.slice]
        bases.append(
            {
                "base": annotation_text(base.value) or "",
                "arguments": [annotation_text(argument) or "" for argument in arguments],
                "arguments_are_names": [isinstance(argument, ast.Name) for argument in arguments],
            }
        )
    return bases


def _class_bases(module: ParsedModule, node: ast.ClassDef) -> list[str]:
    stable_bindings = stable_direct_module_bindings(module)

    def base_root(base: ast.expr) -> str | None:
        target = base.value if isinstance(base, ast.Subscript) else base
        resolved = _resolve_static_name(module, target)
        root = (
            target.id
            if isinstance(target, ast.Name)
            else target.value.id
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
            else None
        )
        if isinstance(target, ast.Name) and target.id == "object":
            alias = module.aliases.get(target.id)
            if not _binding_may_exist_before(module.tree.body, node, target.id):
                return "object"
            if (
                alias is not None
                and alias.target == "builtins.object"
                and target.id in stable_bindings
            ):
                return "builtins.object"
            return f"{module.module}.object"
        if root in module.aliases and (
            root not in stable_bindings
            or not _binding_may_exist_before(module.tree.body, node, root)
        ):
            return f"{module.module}.{root}"
        return resolved

    return sorted(
        filter(
            None,
            (base_root(base) for base in node.bases),
        )
    )


def _resolve_class_kinds(
    classes: dict[str, ast.ClassDef],
    owners: dict[str, ParsedModule],
    symbols: Sequence[RawRecord],
) -> None:
    symbol_by_id = {item["id"]: item for item in symbols}
    by_name: dict[str, list[RawRecord]] = {}
    for item in symbols:
        data = item["data"]
        if data.get("definition_contexts"):
            continue
        definitions: list[RawRecord] = by_name.setdefault(data["qualified_name"], [])
        definitions.append(item)
    changed = True
    while changed:
        changed = False
        for identity, node in classes.items():
            item = symbol_by_id[identity]
            qualname = item["data"]["qualified_name"]
            current = item["data"].get("class_kind")
            data = item["data"]
            if data.get("definition_contexts"):
                continue
            candidates: set[str] = set()
            for resolved_base in item["data"]["base_roots"]:
                tail = resolved_base.rsplit(".", 1)[-1]
                if resolved_base in _KNOWN_CLASS_KINDS:
                    candidates.add(_KNOWN_CLASS_KINDS[resolved_base])
                local_target = f"{owners[qualname].module}.{tail}"
                bases = by_name.get(resolved_base) or by_name.get(local_target) or []
                inherited = bases[0]["data"].get("class_kind") if len(bases) == 1 else None
                # A Protocol subclass is a normal class unless Protocol is an explicit base.
                if inherited and inherited not in {"class", "protocol"}:
                    candidates.add(inherited)
            if any(
                _resolve_static_name(
                    owners[qualname],
                    decorator.func if isinstance(decorator, ast.Call) else decorator,
                )
                in DATACLASS_DECORATORS
                for decorator in node.decorator_list
            ):
                candidates.add("dataclass")
            class_kind = sorted(candidates)[0] if candidates else "class"
            if current != class_kind:
                item["data"]["class_kind"] = class_kind
                changed = True
            if class_kind == "enum":
                item["data"]["enum_members"] = _static_enum_members(node)
    for identity, node in classes.items():
        item = symbol_by_id[identity]
        qualname = item["data"]["qualified_name"]
        # frozen_object depends on class_kind, which is final only after the fixpoint.
        item["data"]["frozen_object"] = _class_is_frozen(
            node,
            owners[qualname],
            allow_pydantic=item["data"].get("class_kind") == "pydantic_model",
        )


def _base_binding(
    module: ParsedModule,
    node: ast.ClassDef,
    owner: RawRecord,
    base: ast.expr,
    by_name: dict[str, list[RawRecord]],
    stable_bindings: frozenset[str],
) -> tuple[str, list[str], str]:
    classifier = base.value if isinstance(base, ast.Subscript) else base
    dotted: str = dotted_expression(classifier) or ""
    targets: list[str] = []
    status, reason = "unresolved", "dynamic base expression has no proven classifier binding"
    if dotted:
        root, _, tail = dotted.partition(".")
        alias = module.aliases.get(root)
        target = (
            ".".join([alias.target, tail])
            if alias and tail
            else alias.target
            if alias
            else f"{module.module}.{dotted}"
        )
        known = by_name.get(target, [])
        proven = (
            owner["data"]["lexical_parent_id"] is None
            and root in stable_bindings
            and _bound_once_before(module.tree.body, node, root)
        )
        if alias or known:
            targets = [target]
            status, reason = (
                "partially_resolved",
                "base name has candidates without a proven binding",
            )
            if proven and (alias or (len(known) == 1 and known[0]["kind"] == "class")):
                status, reason = "resolved", "explicit base with a stable direct module binding"
                if len(known) > 1 or (known and known[0]["kind"] != "class"):
                    status, reason = (
                        "partially_resolved",
                        "imported classifier identity is ambiguous or unavailable",
                    )
                elif _base_namespace_uncertain(target, by_name):
                    status, reason = "partially_resolved", "classifier or qualifier may be replaced"
                elif not known and target not in _KNOWN_CLASS_KINDS and target != "builtins.object":
                    status, reason = "partially_resolved", "external classifier kind is unavailable"
        elif (
            dotted == "object"
            and owner["data"]["lexical_parent_id"] is None
            and not _binding_may_exist_before(module.tree.body, node, root)
        ):
            targets = ["builtins.object"]
            status, reason = "resolved", "unshadowed builtin object base"
        if (
            isinstance(base, ast.Subscript)
            and status == "resolved"
            and target not in {"typing.Protocol", "typing_extensions.Protocol"}
        ):
            status, reason = (
                "partially_resolved",
                "generic base may replace its classifier through __class_getitem__",
            )
    return status, targets, reason


def _base_declaration(
    module: ParsedModule,
    node: ast.ClassDef,
    owner: RawRecord,
    base: ast.expr,
    by_name: dict[str, list[RawRecord]],
    stable_bindings: frozenset[str],
    evidence: dict[str, RawEvidence],
) -> RecordData:
    status, targets, reason = _base_binding(module, node, owner, base, by_name, stable_bindings)
    expression = annotation_text(base) or "<unparseable>"
    known = by_name.get(targets[0], []) if targets else []
    kind = "inherits"
    if (
        status == "resolved"
        and len(known) == 1
        and known[0]["data"]["class_kind"] == "protocol"
        and owner["data"]["class_kind"] != "protocol"
    ):
        kind = "realizes"
    line, _, column = location(base)
    return {
        "id": stable_id("BASE", owner["id"], line, column, expression),
        "relationship_kind": kind,
        "expression": expression,
        "status": status,
        "targets": targets,
        "candidate_count": len(targets),
        "reason": reason,
        "evidence_ids": [add_evidence(evidence, module, base)],
    }


def _base_namespace_uncertain(
    target: str, by_name: dict[str, list[RawRecord]], ancestors: frozenset[str] = frozenset()
) -> bool:
    if target in ancestors:
        return True
    ancestors = ancestors | {target}
    parts = target.split(".")
    for end in range(1, len(parts) + 1):
        definitions = by_name.get(".".join(parts[:end]), [])
        if len(definitions) > 1:
            return True
        for item in definitions:
            data = item["data"]
            if (
                data.get("definition_contexts")
                or item["kind"] == "class"
                and (
                    data["class_header_static"] is not True
                    or data["class_body_control_flow"]
                    or any(
                        base["status"] != "resolved"
                        or any(
                            _base_namespace_uncertain(parent, by_name, ancestors)
                            for parent in base["targets"]
                        )
                        for base in data.get("base_declarations", [])
                    )
                )
            ):
                return True
    return False


def _record_class_bases(
    classes: dict[str, ast.ClassDef],
    owners: dict[str, ParsedModule],
    symbols: Sequence[RawRecord],
    evidence: dict[str, RawEvidence],
) -> None:
    by_name: dict[str, list[RawRecord]] = {}
    by_id = {item["id"]: item for item in symbols}
    for item in symbols:
        definitions: list[RawRecord] = by_name.setdefault(item["data"]["qualified_name"], [])
        definitions.append(item)
    for identity, node in classes.items():
        item = by_id[identity]
        module = owners[item["data"]["qualified_name"]]
        stable_bindings = stable_direct_module_bindings(module)
        item["data"]["base_declarations"] = [
            _base_declaration(module, node, item, base, by_name, stable_bindings, evidence)
            for base in node.bases
        ]
    # All ancestry declarations must exist before their uncertainty can reach descendants.
    for item in symbols:
        if item["kind"] != "class":
            continue
        for base in item["data"]["base_declarations"]:
            if base["status"] == "resolved" and any(
                _base_namespace_uncertain(target, by_name) for target in base["targets"]
            ):
                base["status"] = "partially_resolved"
                base["reason"] = "classifier or qualifier may be replaced"


def _static_enum_members(node: ast.ClassDef) -> list[str]:
    """Return enum members assigned one literal value exactly once in the class body."""
    assignments: dict[str, ast.expr | None] = {}
    for child in node.body:
        value: ast.expr | None
        if isinstance(child, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_ignore_" for target in child.targets
        ):
            return []
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            if child.target.id == "_ignore_":
                return []
        if isinstance(child, ast.Delete):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = None
            continue
        if isinstance(child, ast.Assign) and len(child.targets) == 1:
            target = child.targets[0]
            value = child.value
        elif isinstance(child, ast.AnnAssign):
            target = child.target
            value = child.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id[:1] != "_":
            if target.id in assignments:
                assignments[target.id] = None
            else:
                assignments[target.id] = value
    return sorted(name for name, value in assignments.items() if isinstance(value, ast.Constant))


def _assignment_symbol(
    module: ParsedModule,
    node: ast.AST,
    name: str,
    kind: str,
    evidence: dict[str, RawEvidence],
    **details: object,
) -> RawRecord:
    evidence_id = add_evidence(evidence, module, node)
    line, _, column = location(node)
    return classified(
        item_id=stable_id("SYM", f"{module.module}.{name}", module.rel_path, line, column),
        evidence_class=EvidenceClass.FACT,
        area="repository_topology",
        kind=kind,
        title=name,
        subjects=[f"{module.module}.{name}", module.module],
        evidence_ids=[evidence_id],
        data={
            "record_kind": kind,
            "qualified_name": f"{module.module}.{name}",
            "module": module.module,
            "name": name,
            "parent": None,
            "visibility": "private" if name.startswith("_") else "public_name",
            **(
                {
                    "source_binding_unique": name in stable_direct_module_bindings(module),
                    "source_member_binding_static": name not in unproven_member_bindings(module),
                }
                if kind == "type_alias"
                else {}
            ),
            **details,
        },
    )


def _json_literal(value: str | bytes | int | float | complex | EllipsisType | None) -> bool:
    """Whether the observation, UTF-8 JSON, can hold a constant's value (AD-102).

    Asking the encoder itself also rules out what a type check misses: a `str` with a lone
    surrogate, an `int` beyond Python's digit limit and a non-finite `float`.
    """
    if value is not None and not isinstance(value, str | int | float):
        return False
    try:
        text: str = json.dumps(value, ensure_ascii=False, allow_nan=False)
        text.encode("utf-8")
    except ValueError:
        return False
    return True


def _direct_assignment_names(module: ParsedModule, node: ast.AST) -> set[str]:
    if node not in module.tree.body or not isinstance(
        node, ast.Assign | ast.AnnAssign | ast.AugAssign
    ):
        return set()
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _pep695_alias_symbol(
    module: ParsedModule,
    node: ast.AST,
    name: str,
    evidence: dict[str, RawEvidence],
) -> RawRecord | None:
    if not (sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias)):
        return None
    if node in module.tree.body and not node.type_params:
        return _assignment_symbol(
            module, node, name, "type_alias", evidence, alias=annotation_text(node.value)
        )
    return _assignment_symbol(module, node, name, "dynamic_binding", evidence)


def _module_assignment_symbols(
    module: ParsedModule, evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    aliases = {
        node.target.id
        for node in module.tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and _resolve_static_name(module, node.annotation) == "typing.TypeAlias"
    }
    symbols: list[RawRecord] = []
    seen: set[tuple[ast.AST, str]] = set()
    for node, name in module_scope_bindings(module):
        event = (node, name)
        if event in seen:
            continue
        seen.add(event)
        direct_names = _direct_assignment_names(module, node)
        if (
            isinstance(node, ast.AnnAssign)
            and node in module.tree.body
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.expr)
            and _resolve_static_name(module, node.annotation) == "typing.TypeAlias"
        ):
            symbols.append(
                _assignment_symbol(
                    module,
                    node,
                    name,
                    "type_alias",
                    evidence,
                    alias=annotation_text(node.value),
                )
            )
        elif symbol := _pep695_alias_symbol(module, node, name, evidence):
            symbols.append(symbol)
        elif (
            isinstance(node, ast.Assign)
            and node in module.tree.body
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and name == node.targets[0].id
            and name[:1].isupper()
            and is_static_type_alias_value(module, node.value)
        ):
            symbols.append(
                _assignment_symbol(
                    module,
                    node,
                    name,
                    "type_alias",
                    evidence,
                    alias=annotation_text(node.value),
                )
            )
        elif (
            name in direct_names
            and isinstance(node, ast.Assign | ast.AnnAssign)
            and isinstance(node.value, ast.Constant)
        ):
            value = node.value.value
            symbols.append(
                _assignment_symbol(
                    module,
                    node,
                    name,
                    "static_constant",
                    evidence,
                    **({"constant": value} if _json_literal(value) else {}),
                )
            )
        elif (
            name in _BUILTIN_NAMES
            or name in direct_names
            and (name[:1].isupper() or name in aliases)
        ):
            symbols.append(_assignment_symbol(module, node, name, "dynamic_binding", evidence))
    return symbols


def _definition_symbol(
    module: ParsedModule,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    qualname: str,
    parent: str | None,
    parent_node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | None,
    evidence: dict[str, RawEvidence],
    namespace_bound: bool,
    contexts: DefinitionContexts,
) -> RawRecord:
    classifier = parent_node if isinstance(parent_node, ast.ClassDef) else None
    data = _symbol_data(module, node, qualname, parent, classifier, evidence=evidence)
    data["namespace_bound"] = namespace_bound
    if isinstance(node, ast.ClassDef):
        data["default_instance_result"] = (
            parent_node is None
            and node.name in stable_direct_module_bindings(module)
            and not contexts
            and not node.bases
            and not node.keywords
            and not node.decorator_list
            and not data["class_body_control_flow"]
            and _default_constructor_body(node)
            and "__new__" not in data["class_members"]
            and "__init__" not in data["class_members"]
        )
    data["definition_contexts"] = [
        {
            "kind": kind,
            "branch": branch,
            "evidence_ids": [add_evidence(evidence, module, statement)],
        }
        for statement, kind, branch in contexts
    ]
    data["lexical_parent_id"] = (
        definition_id(module, parent_node, parent) if parent_node and parent else None
    )
    uncertainties = _annotation_binding_uncertainties(module, node, classifier)
    if uncertainties:
        data["annotation_binding_uncertainties"] = uncertainties
        data["annotation_scope"] = (
            qualname if isinstance(node, ast.ClassDef) else parent or qualname
        )
    return classified(
        item_id=definition_id(module, node, qualname),
        evidence_class=EvidenceClass.FACT,
        area="repository_topology",
        kind="class" if isinstance(node, ast.ClassDef) else "method" if classifier else "function",
        title=node.name,
        subjects=[qualname, module.module],
        evidence_ids=[add_evidence(evidence, module, node)],
        data=data,
    )


def _default_constructor_body(node: ast.ClassDef) -> bool:
    """Class-body execution can replace allocation; only inert declarations prove it here."""
    for child in node.body:
        if isinstance(child, ast.Pass):
            continue
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
            continue
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            args = child.args
            arguments = (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg)
            if (
                not child.decorator_list
                and not args.defaults
                and not any(args.kw_defaults)
                and child.returns is None
                and all(arg is None or arg.annotation is None for arg in arguments)
            ):
                continue
        return False
    return True


def collect_symbols(
    modules: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> tuple[list[RawRecord], dict[str, ast.AST], dict[str, ParsedModule]]:
    symbols: list[RawRecord] = []
    nodes: dict[str, ast.AST] = {}
    owners: dict[str, ParsedModule] = {}
    classes: dict[str, ast.ClassDef] = {}

    for module in modules:
        names: dict[ast.AST, str] = {}
        namespace_bindings: dict[ast.AST, bool] = {}
        for node, parent_node, contexts in definition_sites(module.tree):
            parent = names.get(parent_node) if parent_node else None
            qualname = f"{parent or module.module}.{node.name}"
            names[node] = qualname
            bound = parent_node is None or (
                isinstance(parent_node, ast.ClassDef) and namespace_bindings[parent_node]
            )
            namespace_bindings[node] = bound
            symbol = _definition_symbol(
                module, node, qualname, parent, parent_node, evidence, bound, contexts
            )
            symbols.append(symbol)
            if not contexts:
                nodes[qualname] = node
            owners[qualname] = module
            if isinstance(node, ast.ClassDef):
                classes[symbol["id"]] = node
        definition_ids = {item["id"] for item in symbols}
        symbols.extend(
            item
            for item in _module_assignment_symbols(module, evidence)
            if item["id"] not in definition_ids
        )

    _resolve_class_kinds(classes, owners, symbols)
    _record_class_bases(classes, owners, symbols, evidence)
    symbols = _mark_overloaded_symbols(symbols)
    return sorted(symbols, key=lambda item: item["id"]), nodes, owners


def _mark_overloaded_symbols(symbols: list[RawRecord]) -> list[RawRecord]:
    overloaded = {
        (data["module"], data["parent"], data["name"])
        for item in symbols
        if (data := item["data"]).get("overload_signature") is True
    }
    return [
        {**item, "data": {**item["data"], "overloaded": True}}
        if (item["data"]["module"], item["data"]["parent"], item["data"]["name"]) in overloaded
        else item
        for item in symbols
    ]
