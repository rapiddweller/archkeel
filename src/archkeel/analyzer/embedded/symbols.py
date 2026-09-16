# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Class and function symbol collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import hashlib
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
    for qualname, node in classes.items():
        item = symbol_by_name[qualname]
        # frozen_object depends on class_kind, which is final only after the fixpoint.
        item["data"]["frozen_object"] = _class_is_frozen(
            node,
            owners[qualname],
            allow_pydantic=item["data"].get("class_kind") == "pydantic_model",
        )


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

    symbol_by_name: dict[str, RawRecord] = {
        item["data"]["qualified_name"]: item for item in symbols
    }
    _resolve_class_kinds(classes, owners, symbol_by_name)
    return sorted(symbols, key=lambda item: item["id"]), nodes, owners
