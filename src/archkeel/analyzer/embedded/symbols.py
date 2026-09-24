# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Class and function symbol collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import hashlib
import math
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, stable_id

from .records import RawEvidence, RawRecord, RecordData, classified
from .source import ParsedModule, add_evidence, annotation_text, decorator_names, location


def _resolve_static_name(module: ParsedModule, node: ast.AST) -> str:
    text = annotation_text(node) or ""
    parts = text.split(".")
    binding = module.aliases.get(parts[0]) if parts else None
    if binding is None:
        return text
    return ".".join([binding.target, *parts[1:]])


def _is_static_type_alias_value(module: ParsedModule, node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    if isinstance(node, ast.Subscript):
        head = _resolve_static_name(module, node.value)
        return head in {
            "typing.Annotated",
            "typing.Literal",
            "typing.Optional",
            "typing.Union",
            "typing_extensions.Annotated",
            "typing_extensions.Literal",
            "typing_extensions.TypeAliasType",
            "dict",
            "list",
            "set",
            "tuple",
            "frozenset",
        }
    return False


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
        if name in {"dataclasses.dataclass", "pydantic.dataclasses.dataclass"} and any(
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
        data.update(
            {
                "bases": sorted(filter(None, (annotation_text(base) for base in node.bases))),
                "frozen_object": _class_is_frozen(node, module),
                "symbol_category": "class",
                "fields": _class_field_annotations(node),
            }
        )
    else:
        data.update(_function_signature(node))
        data["symbol_category"] = "method" if parent else "function"
        shape, shape_nodes = _shape(node)
        data["shape"] = shape
        data["shape_nodes"] = shape_nodes
    return data


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
                in {"dataclasses.dataclass", "pydantic.dataclasses.dataclass"}
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
    node: ast.Assign | ast.AnnAssign,
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
            **details,
        },
    )


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
    for node in module.tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.expr)
            and _resolve_static_name(module, node.annotation) == "typing.TypeAlias"
        ):
            symbols.append(
                _assignment_symbol(
                    module,
                    node,
                    node.target.id,
                    "type_alias",
                    evidence,
                    alias=annotation_text(node.value),
                )
            )
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id[:1].isupper()
            and _is_static_type_alias_value(module, node.value)
        ):
            symbols.append(
                _assignment_symbol(
                    module,
                    node,
                    node.targets[0].id,
                    "type_alias",
                    evidence,
                    alias=annotation_text(node.value),
                )
            )
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if isinstance(node.value, ast.Constant):
                    value = node.value.value
                    # The observation is JSON: bytes, complex, Ellipsis and non-finite floats
                    # have no JSON value, so such a constant is recorded without one (AD-102).
                    json_value = (
                        value is None
                        or isinstance(value, str | int)
                        or (isinstance(value, float) and math.isfinite(value))
                    )
                    symbols.append(
                        _assignment_symbol(
                            module,
                            node,
                            target.id,
                            "static_constant",
                            evidence,
                            **({"constant": value} if json_value else {}),
                        )
                    )
                elif target.id[:1].isupper() or target.id in aliases:
                    symbols.append(
                        _assignment_symbol(module, node, target.id, "dynamic_binding", evidence)
                    )
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
    ) -> None:
        evidence_id = add_evidence(evidence, module, node)
        data = _symbol_data(module, node, qualname, parent)
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
    return sorted(symbols, key=lambda item: item["id"]), nodes, owners
