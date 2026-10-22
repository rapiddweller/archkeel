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
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.ir.facts import SourceResolution, SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import RawRecord

from .binding_types import BindingKind
from .receiver_types import (
    ReceiverOrigin,
    ReceiverType,
    annotation_receiver_type,
    constructor_receiver_type,
    literal_receiver_type,
    method_element_type,
    method_return_type,
    receiver_call_target,
)
from .scopes import LexicalScopes, NameBinding
from .source import own_scope

_BUILTINS = frozenset(dir(builtins))
_NO_RECEIVERS: Mapping[str, ReceiverType] = {}
# What each receiver origin lets a call on it claim (AD-37, AD-40).
_ORIGIN_VERDICT: dict[ReceiverOrigin, tuple[SourceResolution, str]] = {
    ReceiverOrigin.LITERAL: (SourceResolution.RESOLVED, "literal-bound receiver of known type"),
    ReceiverOrigin.ANNOTATION: (
        SourceResolution.PARTIALLY_RESOLVED,
        "annotated receiver of known type, unproven at runtime",
    ),
    ReceiverOrigin.DOCUMENTED: (
        SourceResolution.PARTIALLY_RESOLVED,
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
    definition_ids: frozenset[str]
    conditional_names: frozenset[str]
    constructor_results: dict[str, bool]
    binding_ids: frozenset[str]
    declaration_names: frozenset[str]
    binding_declarations: dict[str, RawRecord]
    symbol_ids: dict[str, str]


def build_symbol_index(symbols: Sequence[RawRecord]) -> SymbolIndex:
    counts = Counter(item["data"]["qualified_name"] for item in symbols)
    definition_ids = frozenset(
        item["id"] for item in symbols if item["kind"] in {"class", "function", "method"}
    )
    declarations = frozenset(
        item["data"]["qualified_name"]
        for item in symbols
        if item["kind"] in {"class", "function", "method"}
    )
    # Lexical declarations are visible by name, never as attributes of a function.
    names: set[str] = {
        item["data"]["qualified_name"]
        for item in symbols
        if item["data"].get("namespace_bound") is not False
    }
    by_tail: dict[str, list[str]] = defaultdict(list)
    for name in sorted(names):
        by_tail[name.rsplit(".", 1)[-1]].append(name)
    evidence: dict[str, list[str]] = {}
    conditional_names: set[str] = set()
    constructor_results: dict[str, bool] = {}
    for item in symbols:
        data = item["data"]
        name = data["qualified_name"]
        evidence[name] = sorted(set(evidence.get(name, [])).union(item["evidence_ids"]))
        if data.get("definition_contexts"):
            conditional_names.add(name)
        if item["kind"] == "class":
            constructor_results[name] = (
                name not in constructor_results and data.get("default_instance_result") is True
            )
    enum_members: dict[str, frozenset[str]] = {}
    for item in symbols:
        data = item["data"]
        if (
            parse_symbol_class_kind(data.get("class_kind")) is SymbolClassKind.ENUM
            and "enum_members" in data
        ):
            members = data["enum_members"]
            if isinstance(members, list):
                enum_members[data["qualified_name"]] = frozenset(members)
    return SymbolIndex(
        frozenset(names),
        dict(by_tail),
        evidence,
        enum_members,
        definition_ids,
        frozenset(conditional_names),
        constructor_results,
        frozenset(item["id"] for item in symbols if item["kind"] == "dynamic_binding"),
        declarations,
        {
            item["data"]["qualified_name"]: item
            for item in symbols
            if counts[item["data"]["qualified_name"]] == 1
            and item["kind"] in {"class", "function", "method"}
        },
        {
            item["data"]["qualified_name"]: item["id"]
            for item in symbols
            if counts[item["data"]["qualified_name"]] == 1
        },
    )


def _named_binding(
    target: str, index: SymbolIndex, reason: str
) -> tuple[SourceResolution, list[str], str, int]:
    parts = target.split(".")
    if any(".".join(parts[:end]) in index.conditional_names for end in range(1, len(parts) + 1)):
        return (
            SourceResolution.PARTIALLY_RESOLVED,
            [target],
            "conditional definition has no proven runtime binding",
            1,
        )
    return SourceResolution.RESOLVED, [target], reason, 1


def _static_receiver_type(
    node: ast.expr,
    *,
    receiver_types: Mapping[str, ReceiverType | None],
    scopes: LexicalScopes,
) -> str | None:
    """Name the type of an expression used as a receiver, from what is already known."""
    if isinstance(node, ast.Name):
        receiver = receiver_types.get(node.id)
        return receiver.type_name if receiver else None
    if isinstance(node, ast.Call):
        return call_result_type(node, receiver_types=receiver_types, scopes=scopes)
    return literal_receiver_type(node)


def _declared_function_result_type(call: ast.Call, scopes: LexicalScopes) -> str | None:
    if not isinstance(call.func, ast.Name) or scopes.module.binding_names is None:
        return None
    binding = scopes.lookup(call.func, call.func.id)
    if binding.owner is None or binding.kind is not BindingKind.DECLARATION or binding.uncertain:
        return None
    definitions = binding.owner.bindings.get(call.func.id, [])
    if len(definitions) != 1 or not isinstance(definitions[0], ast.FunctionDef):
        return None
    definition = definitions[0]
    if (
        definition.decorator_list
        or (sys.version_info >= (3, 12) and definition.type_params)
        or any(isinstance(node, ast.Yield | ast.YieldFrom) for node in own_scope(definition))
    ):
        return None
    annotation = definition.returns
    base = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    if (
        not isinstance(base, ast.Name)
        or base.id not in _BUILTINS
        or scopes.lookup(base, base.id).kind is not BindingKind.UNBOUND
    ):
        return None
    parent = scopes.parents.get(call)
    if isinstance(parent, ast.Assign | ast.AnnAssign) and parent.value is call:
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            return None
        target = targets[0]
        assigned = scopes.lookup(target, target.id)
        # A later helper assignment must not retain another assignment's literal origin.
        if (
            assigned.owner is None
            or assigned.uncertain
            or assigned.owner.bindings.get(target.id) != [target]
        ):
            return None
    return annotation_receiver_type(base.id)


def call_result_type(
    call: ast.Call,
    *,
    receiver_types: Mapping[str, ReceiverType | None],
    scopes: LexicalScopes,
) -> str | None:
    """Name the documented type a call evaluates to, or None (AD-40).

    Methods and imported constructors use documented returns. A unique local function may
    contribute its declared builtin return type, with runtime behavior still unproven.
    """
    if isinstance(call.func, ast.Attribute):
        receiver = _static_receiver_type(
            call.func.value, receiver_types=receiver_types, scopes=scopes
        )
        if receiver is not None:
            return method_return_type(receiver, call.func.attr)
    declared = _declared_function_result_type(call, scopes)
    if declared is not None:
        return declared
    dotted = dotted_expression(call.func)
    if dotted is None:
        return None
    parts = dotted.split(".")
    binding = scopes.lookup(call.func, parts[0])
    if (
        binding.kind not in {BindingKind.MODULE, BindingKind.SYMBOL}
        or binding.uncertain
        or len(binding.targets) != 1
    ):
        return None
    return constructor_receiver_type(".".join([binding.targets[0], *parts[1:]]))


def iterated_call_result_type(
    call: ast.Call,
    *,
    receiver_types: Mapping[str, ReceiverType],
    scopes: LexicalScopes,
) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    receiver = _static_receiver_type(call.func.value, receiver_types=receiver_types, scopes=scopes)
    return method_element_type(receiver, call.func.attr) if receiver is not None else None


def _resolve_expression_receiver(
    node: ast.Attribute,
    *,
    receiver_types: Mapping[str, ReceiverType],
    scopes: LexicalScopes,
) -> tuple[SourceResolution, list[str], str, int] | None:
    """Resolve a call on a literal or on a call result written at the call site.

    Unlike `[]`/`{}`/`list(...)`, which AD-37 case 2 recognises only through a named local,
    a str or f-string here proves its own type outright (AD-37 case 1); a call result is
    typed from its documented table and so claims only `partially_resolved` (AD-40).
    """
    if isinstance(node.value, ast.Constant | ast.JoinedStr):
        literal_type = literal_receiver_type(node.value)
        status, reason = SourceResolution.RESOLVED, "literal receiver of known type"
    elif isinstance(node.value, ast.Call):
        literal_type = call_result_type(node.value, receiver_types=receiver_types, scopes=scopes)
        status, reason = (
            SourceResolution.PARTIALLY_RESOLVED,
            "call result of documented type, unproven at runtime",
        )
    else:
        return None
    if literal_type is None:
        return None
    target = receiver_call_target(literal_type, node.attr)
    if target is None:
        return None
    return status, [target], reason, 1


def _resolve_name_node(
    node: ast.Name,
    *,
    index: SymbolIndex,
    scopes: LexicalScopes,
    value_reference: bool,
) -> tuple[SourceResolution, list[str], str, int]:
    binding = scopes.lookup(node, node.id)
    if binding.targets:
        reason = (
            ("module-local symbol" if binding.owner is scopes.root else "lexical declaration")
            if binding.kind is BindingKind.DECLARATION
            else (f"imported {binding.kind.value} binding")
        )
        return _scoped_binding(binding, binding.targets, index, reason)
    if value_reference and binding.kind is BindingKind.LOCAL and binding.owner is scopes.root:
        target = f"{binding.owner.qualified_name}.{node.id}"
        if target in index.names:
            return _scoped_binding(binding, (target,), index, "namespace value binding")
    if binding.kind is not BindingKind.UNBOUND:
        return SourceResolution.UNRESOLVED, [], "lexical binding has no proven callable value", 0
    if node.id in _BUILTINS:
        return SourceResolution.RESOLVED, [f"builtins.{node.id}"], "Python builtin", 1
    candidates = index.by_tail.get(node.id, [])
    if candidates:
        return (
            SourceResolution.PARTIALLY_RESOLVED,
            candidates[:5],
            "name matches internal symbols without a proven binding",
            len(candidates),
        )
    return SourceResolution.UNRESOLVED, [], "name has no statically indexed binding", 0


def _scoped_binding(
    binding: NameBinding, targets: tuple[str, ...], index: SymbolIndex, reason: str
) -> tuple[SourceResolution, list[str], str, int]:
    if len(targets) == 1:
        result = _named_binding(targets[0], index, reason)
        if result[0] == SourceResolution.PARTIALLY_RESOLVED:
            return result
    if binding.uncertain or len(targets) != 1:
        return (
            SourceResolution.PARTIALLY_RESOLVED,
            list(targets[:5]),
            "competing lexical binding sites",
            len(targets),
        )
    return _named_binding(targets[0], index, reason)


def _resolve_receiver_bound_call(
    parts: list[str], receiver_types: Mapping[str, ReceiverType]
) -> tuple[SourceResolution, list[str], str, int] | None:
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
    index: SymbolIndex,
    scopes: LexicalScopes,
    node: ast.AST,
    receiver_types: Mapping[str, ReceiverType],
) -> tuple[SourceResolution, list[str], str, int]:
    parts = dotted.split(".")
    binding = scopes.lookup(node, parts[0])
    if binding.kind is BindingKind.UNBOUND and len(parts) == 2 and parts[0] in _BUILTINS:
        target = receiver_call_target(parts[0], parts[1])
        if target is not None:
            return (
                SourceResolution.PARTIALLY_RESOLVED,
                [target],
                "Python builtin class member, unproven at runtime",
                1,
            )
    if binding.kind in {BindingKind.MODULE, BindingKind.SYMBOL} and binding.targets:
        targets = tuple(".".join([target, *parts[1:]]) for target in binding.targets)
        return _scoped_binding(
            binding, targets, index, f"attribute of imported {binding.kind.value} binding"
        )
    receiver_result = _resolve_receiver_bound_call(parts, receiver_types)
    if receiver_result:
        return receiver_result
    candidates = index.by_tail.get(parts[-1], [])
    receiver_class = scopes.receiver_class(binding, parts[0])
    if receiver_class:
        target = f"{receiver_class}.{'.'.join(parts[1:])}"
        if target in index.declaration_names:
            return _named_binding(target, index, "method on current class")
        # A stored receiver's method need not belong to the containing class.
        if len(parts) == 2 or not candidates:
            return (
                SourceResolution.PARTIALLY_RESOLVED,
                [target],
                "current-class attribute without indexed method target",
                1,
            )
    targets = tuple(
        target
        for root in binding.targets
        if (target := f"{root}.{'.'.join(parts[1:])}") in index.names
        or (root in index.constructor_results and target in index.declaration_names)
    )
    if targets:
        return _scoped_binding(binding, targets, index, "class-qualified local method")
    if candidates:
        return (
            SourceResolution.PARTIALLY_RESOLVED,
            candidates[:5],
            "dynamic receiver with matching internal methods",
            len(candidates),
        )
    return SourceResolution.UNRESOLVED, [], "dynamic attribute receiver", 0


def resolve_name(
    node: ast.AST,
    *,
    index: SymbolIndex,
    scopes: LexicalScopes,
    receiver_types: Mapping[str, ReceiverType] = _NO_RECEIVERS,
    value_reference: bool = False,
) -> tuple[SourceResolution, list[str], str, int]:
    """Name the symbols one expression can mean, with why the resolution holds.

    `receiver_types` contains only bindings visible at this expression. Lexical ownership
    is shared with references; neither collector can fall back past a local binder.
    """
    if isinstance(node, ast.Attribute):
        expression_result = _resolve_expression_receiver(
            node, receiver_types=receiver_types, scopes=scopes
        )
        if expression_result:
            return expression_result
    if isinstance(node, ast.Name):
        return _resolve_name_node(node, index=index, scopes=scopes, value_reference=value_reference)
    dotted = dotted_expression(node)
    if dotted:
        return _resolve_dotted(
            dotted,
            index=index,
            scopes=scopes,
            node=node,
            receiver_types=receiver_types,
        )
    return SourceResolution.UNRESOLVED, [], "expression is dynamic", 0
