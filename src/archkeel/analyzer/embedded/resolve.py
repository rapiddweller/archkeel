# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve a name expression to the symbols it can mean.

Collectors are peers that never import each other (AD-25), so the resolution the call and
the reference collector both need lives here, in a module they may both reach.
"""

from __future__ import annotations

import ast
import builtins
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .receiver_types import (
    ReceiverType,
    constructor_receiver_type,
    literal_receiver_type,
    method_return_type,
    receiver_call_target,
)
from .records import RawRecord
from .source import ParsedModule

_BUILTINS = frozenset(dir(builtins))
_NO_RECEIVERS: Mapping[str, ReceiverType] = {}
# What each receiver origin lets a call on it claim (AD-37, AD-40).
_ORIGIN_VERDICT: dict[str, tuple[str, str]] = {
    "literal": ("resolved", "literal-bound receiver of known type"),
    "annotation": ("partially_resolved", "annotated receiver of known type, unproven at runtime"),
    "documented": (
        "partially_resolved",
        "receiver bound to a call result of documented type, unproven at runtime",
    ),
}


def dotted_expression(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


@dataclass(frozen=True, slots=True)
class SymbolIndex:
    """Every scanned symbol by qualified name, by trailing name, and by its evidence."""

    names: frozenset[str]
    by_tail: dict[str, list[str]]
    evidence: dict[str, list[str]]
    enum_members: dict[str, frozenset[str]]


def build_symbol_index(symbols: Sequence[RawRecord]) -> SymbolIndex:
    names: set[str] = {item["data"]["qualified_name"] for item in symbols}
    by_tail: dict[str, list[str]] = defaultdict(list)
    for name in sorted(names):
        by_tail[name.rsplit(".", 1)[-1]].append(name)
    evidence: dict[str, list[str]] = {
        item["data"]["qualified_name"]: item["evidence_ids"] for item in symbols
    }
    enum_members: dict[str, frozenset[str]] = {}
    for item in symbols:
        data = item["data"]
        if data.get("class_kind") == "enum" and "enum_members" in data:
            members = data["enum_members"]
            if isinstance(members, list):
                enum_members[data["qualified_name"]] = frozenset(members)
    return SymbolIndex(frozenset(names), dict(by_tail), evidence, enum_members)


def _static_receiver_type(
    node: ast.expr, *, module: ParsedModule, receiver_types: Mapping[str, ReceiverType | None]
) -> str | None:
    """Name the type of an expression used as a receiver, from what is already known."""
    if isinstance(node, ast.Name):
        receiver = receiver_types.get(node.id)
        return receiver.type_name if receiver else None
    if isinstance(node, ast.Call):
        return call_result_type(node, module=module, receiver_types=receiver_types)
    return literal_receiver_type(node)


def call_result_type(
    call: ast.Call, *, module: ParsedModule, receiver_types: Mapping[str, ReceiverType | None]
) -> str | None:
    """Name the documented type a call evaluates to, or None (AD-40).

    A method on a typed receiver is looked up by its documented return; anything else must
    be a callable the import bindings name, so a project's own `Table` never matches Rich's.
    """
    if isinstance(call.func, ast.Attribute):
        receiver = _static_receiver_type(
            call.func.value, module=module, receiver_types=receiver_types
        )
        if receiver is not None:
            return method_return_type(receiver, call.func.attr)
    dotted = dotted_expression(call.func)
    if dotted is None:
        return None
    parts = dotted.split(".")
    binding = module.aliases.get(parts[0])
    if binding is None:
        return None
    return constructor_receiver_type(".".join([binding.target, *parts[1:]]))


def _resolve_expression_receiver(
    node: ast.Attribute, *, module: ParsedModule, receiver_types: Mapping[str, ReceiverType]
) -> tuple[str, list[str], str, int] | None:
    """Resolve a call on a literal or on a call result written at the call site.

    Unlike `[]`/`{}`/`list(...)`, which AD-37 case 2 recognises only through a named local,
    a str or f-string here proves its own type outright (AD-37 case 1); a call result is
    typed from its documented table and so claims only `partially_resolved` (AD-40).
    """
    if isinstance(node.value, ast.Constant | ast.JoinedStr):
        literal_type = literal_receiver_type(node.value)
        status, reason = "resolved", "literal receiver of known type"
    elif isinstance(node.value, ast.Call):
        literal_type = call_result_type(node.value, module=module, receiver_types=receiver_types)
        status, reason = "partially_resolved", "call result of documented type, unproven at runtime"
    else:
        return None
    if literal_type is None:
        return None
    target = receiver_call_target(literal_type, node.attr)
    if target is None:
        return None
    return status, [target], reason, 1


def _resolve_name_node(
    node: ast.Name, *, module: ParsedModule, index: SymbolIndex
) -> tuple[str, list[str], str, int]:
    local = f"{module.module}.{node.id}"
    if local in index.names:
        return "resolved", [local], "module-local symbol", 1
    binding = module.aliases.get(node.id)
    if binding:
        return "resolved", [binding.target], f"imported {binding.kind} binding", 1
    if node.id in _BUILTINS:
        return "resolved", [f"builtins.{node.id}"], "Python builtin", 1
    candidates = index.by_tail.get(node.id, [])
    if candidates:
        return (
            "partially_resolved",
            candidates[:5],
            "name matches internal symbols without a proven binding",
            len(candidates),
        )
    return "unresolved", [], "name has no statically indexed binding", 0


def _resolve_receiver_bound_call(
    parts: list[str], receiver_types: Mapping[str, ReceiverType]
) -> tuple[str, list[str], str, int] | None:
    """Resolve `recv.method(...)` where `recv` is a locally typed name (AD-37 cases 2-3)."""
    if len(parts) != 2:
        return None
    receiver = receiver_types.get(parts[0])
    if receiver is None:
        return None
    target = receiver_call_target(receiver.type_name, parts[1])
    if target is None:
        return None
    status, reason = _ORIGIN_VERDICT[receiver.origin]
    return status, [target], reason, 1


def _resolve_dotted(
    dotted: str,
    *,
    module: ParsedModule,
    index: SymbolIndex,
    class_stack: Sequence[str],
    receiver_types: Mapping[str, ReceiverType],
) -> tuple[str, list[str], str, int]:
    parts = dotted.split(".")
    binding = module.aliases.get(parts[0])
    if binding:
        target = ".".join([binding.target, *parts[1:]])
        return "resolved", [target], f"attribute of imported {binding.kind} binding", 1
    receiver_result = _resolve_receiver_bound_call(parts, receiver_types)
    if receiver_result:
        return receiver_result
    if parts[0] == "self" and class_stack:
        target = f"{class_stack[-1]}.{'.'.join(parts[1:])}"
        if target in index.names:
            return "resolved", [target], "method on current class", 1
        return (
            "partially_resolved",
            [target],
            "current-class attribute without indexed method target",
            1,
        )
    local_class = f"{module.module}.{parts[0]}"
    target = f"{local_class}.{'.'.join(parts[1:])}"
    if target in index.names:
        return "resolved", [target], "class-qualified local method", 1
    candidates = index.by_tail.get(parts[-1], [])
    if candidates:
        return (
            "partially_resolved",
            candidates[:5],
            "dynamic receiver with matching internal methods",
            len(candidates),
        )
    return "unresolved", [], "dynamic attribute receiver", 0


def resolve_name(
    node: ast.AST,
    *,
    module: ParsedModule,
    index: SymbolIndex,
    class_stack: Sequence[str],
    receiver_types: Mapping[str, ReceiverType] = _NO_RECEIVERS,
) -> tuple[str, list[str], str, int]:
    """Name the symbols one expression can mean, with why the resolution holds.

    `receiver_types` names, for the enclosing function only, the locals and parameters whose
    type a literal or an annotation makes statically obvious (AD-37); every other collector
    that shares this resolver passes none, and gets the exact result it had before AD-37.
    """
    if isinstance(node, ast.Attribute):
        expression_result = _resolve_expression_receiver(
            node, module=module, receiver_types=receiver_types
        )
        if expression_result:
            return expression_result
    if isinstance(node, ast.Name):
        return _resolve_name_node(node, module=module, index=index)
    dotted = dotted_expression(node)
    if dotted:
        return _resolve_dotted(
            dotted,
            module=module,
            index=index,
            class_stack=class_stack,
            receiver_types=receiver_types,
        )
    return "unresolved", [], "expression is dynamic", 0
