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

from .source import (
    DATACLASS_DECORATORS,
    ParsedModule,
    add_evidence,
    annotation_text,
    class_header_static,
    decorator_names,
    is_static_type_alias_value,
    location,
    module_scope_bindings,
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


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> RecordData:
    positional = [*node.args.posonlyargs, *node.args.args]
    parameters = [
        {"name": argument.arg, "annotation": annotation_text(argument.annotation)}
        for argument in [*positional, *node.args.kwonlyargs]
    ]
    if node.args.vararg:
        parameters.append(
            {
                "name": f"*{node.args.vararg.arg}",
                "annotation": annotation_text(node.args.vararg.annotation),
            }
        )
    if node.args.kwarg:
        parameters.append(
            {
                "name": f"**{node.args.kwarg.arg}",
                "annotation": annotation_text(node.args.kwarg.annotation),
            }
        )
    return {
        "parameters": parameters,
        "receiver_parameter": positional[0].arg if positional else None,
        "returns": annotation_text(node.returns),
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def _class_field_annotations(node: ast.ClassDef) -> list[RecordData]:
    """A class's own public attribute annotations: `check.validation` (AD-70) needs the type
    a declared class hands out through each attribute, the same way it already needs a
    declared function's parameter and return annotations.

    Only a class-body `AnnAssign` counts: that is the shape a dataclass or Pydantic field
    always has, and the one AD-70's own example (`ViolationRow.fingerprint`) is. This is
    narrower than `contexts._class_fields`, which also infers a field from `self.x` inside a
    method for context/state tracking; a public API promise is about what the class declares
    on its own, not what some method happens to assign. A private name is never part of that
    promise either.
    """
    return [
        {"name": child.target.id, "annotation": annotation_text(child.annotation)}
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and not child.target.id.startswith("_")
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
) -> RecordData:
    data: RecordData = {
        "qualified_name": qualname,
        "module": module.module,
        "package": module.package,
        "name": node.name,
        "visibility": "private" if node.name.startswith("_") else "public_name",
        "declared_in_all": node.name in module.all_exports,
        "parent": parent,
        "decorators": decorator_names(node),
    }
    if isinstance(node, ast.ClassDef):
        generic_parameters = _generic_parameters(module, node)
        generic_bases = _generic_bases(node)
        data.update(
            {
                "bases": sorted(filter(None, (annotation_text(base) for base in node.bases))),
                "base_roots": _class_bases(module, node),
                "frozen_object": _class_is_frozen(node, module),
                "symbol_category": "class",
                "fields": _class_field_annotations(node),
                "class_members": _class_member_names(node),
                "source_binding_unique": node.name in stable_direct_module_bindings(module),
                "source_member_binding_static": node.name not in unproven_member_bindings(module),
                "class_header_static": class_header_static(node),
                "class_body_control_flow": unproven_class_body(module, node),
                **({"generic_parameters": generic_parameters} if generic_parameters else {}),
                **({"generic_bases": generic_bases} if generic_bases else {}),
            }
        )
    else:
        data.update(_function_signature(node))
        data["symbol_category"] = "method" if parent else "function"
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
        if parent:
            data.update(_method_decorator_data(module, node, parent_node))
        shape, shape_nodes = _shape(node)
        data["shape"] = shape
        data["shape_nodes"] = shape_nodes
    return data


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
    symbol_by_name: dict[str, RawRecord],
) -> None:
    known_categories = {
        "typing.Protocol": "protocol",
        "typing_extensions.Protocol": "protocol",
        "enum.Enum": "enum",
        "enum.IntEnum": "enum",
        "enum.StrEnum": "enum",
        "pydantic.BaseModel": "pydantic_model",
    }
    changed = True
    while changed:
        changed = False
        for qualname, node in classes.items():
            item = symbol_by_name[qualname]
            current = item["data"].get("class_kind")
            candidates: set[str] = set()
            for base in node.bases:
                base_text = annotation_text(base) or ""
                tail = base_text.rsplit(".", 1)[-1]
                resolved_base = _resolve_static_name(owners[qualname], base)
                if resolved_base in known_categories:
                    candidates.add(known_categories[resolved_base])
                local_target = f"{owners[qualname].module}.{tail}"
                resolved_symbol = symbol_by_name.get(resolved_base)
                local_symbol = symbol_by_name.get(local_target)
                inherited = (
                    resolved_symbol["data"].get("class_kind") if resolved_symbol else None
                ) or (local_symbol["data"].get("class_kind") if local_symbol else None)
                if inherited:
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
    for qualname, node in classes.items():
        item = symbol_by_name[qualname]
        # frozen_object depends on class_kind, which is final only after the fixpoint.
        item["data"]["frozen_object"] = _class_is_frozen(
            node,
            owners[qualname],
            allow_pydantic=item["data"].get("class_kind") == "pydantic_model",
        )


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


def collect_symbols(
    modules: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> tuple[list[RawRecord], dict[str, ast.AST], dict[str, ParsedModule]]:
    symbols: list[RawRecord] = []
    nodes: dict[str, ast.AST] = {}
    owners: dict[str, ParsedModule] = {}
    classes: dict[str, ast.ClassDef] = {}

    def add_symbol(
        module: ParsedModule,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        qualname: str,
        kind: str,
        parent: str | None = None,
        parent_node: ast.ClassDef | None = None,
    ) -> None:
        evidence_id = add_evidence(evidence, module, node)
        data = _symbol_data(module, node, qualname, parent, parent_node)
        uncertainties = _annotation_binding_uncertainties(module, node, parent_node)
        if uncertainties:
            data["annotation_binding_uncertainties"] = uncertainties
            data["annotation_scope"] = (
                qualname if isinstance(node, ast.ClassDef) else parent or qualname
            )
        if isinstance(node, ast.ClassDef):
            classes[qualname] = node
        line, _, column = location(node)
        symbols.append(
            classified(
                item_id=stable_id(
                    "SYM",
                    qualname,
                    module.rel_path,
                    line,
                    column,
                ),
                evidence_class=EvidenceClass.FACT,
                area="repository_topology",
                kind=kind,
                title=node.name,
                subjects=[qualname, module.module],
                evidence_ids=[evidence_id],
                data=data,
            )
        )
        nodes[qualname] = node
        owners[qualname] = module

    def walk_class(module: ParsedModule, node: ast.ClassDef, parent: str | None = None) -> None:
        qualname = f"{module.module}.{node.name}" if parent is None else f"{parent}.{node.name}"
        add_symbol(module, node, qualname=qualname, kind="class", parent=parent)
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(
                    module,
                    child,
                    qualname=f"{qualname}.{child.name}",
                    kind="method",
                    parent=qualname,
                    parent_node=node,
                )
            elif isinstance(child, ast.ClassDef):
                walk_class(module, child, parent=qualname)

    for module in modules:
        for node in module.tree.body:
            if isinstance(node, ast.ClassDef):
                walk_class(module, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(module, node, qualname=f"{module.module}.{node.name}", kind="function")
        symbols.extend(_module_assignment_symbols(module, evidence))

    symbol_by_name: dict[str, RawRecord] = {
        item["data"]["qualified_name"]: item for item in symbols if "qualified_name" in item["data"]
    }
    _resolve_class_kinds(classes, owners, symbol_by_name)
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
