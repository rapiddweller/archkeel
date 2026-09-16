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
from collections.abc import Sequence
from dataclasses import dataclass

from .records import RawRecord
from .source import ParsedModule

_BUILTINS = frozenset(dir(builtins))


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


def build_symbol_index(symbols: Sequence[RawRecord]) -> SymbolIndex:
    names: set[str] = {item["data"]["qualified_name"] for item in symbols}
    by_tail: dict[str, list[str]] = defaultdict(list)
    for name in sorted(names):
        by_tail[name.rsplit(".", 1)[-1]].append(name)
    evidence: dict[str, list[str]] = {
        item["data"]["qualified_name"]: item["evidence_ids"] for item in symbols
    }
    return SymbolIndex(frozenset(names), dict(by_tail), evidence)


def resolve_name(
    node: ast.AST,
    *,
    module: ParsedModule,
    index: SymbolIndex,
    class_stack: Sequence[str],
) -> tuple[str, list[str], str, int]:
    """Name the symbols one expression can mean, with why the resolution holds."""
    if isinstance(node, ast.Name):
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

    dotted = dotted_expression(node)
    if dotted:
        parts = dotted.split(".")
        binding = module.aliases.get(parts[0])
        if binding:
            target = ".".join([binding.target, *parts[1:]])
            return "resolved", [target], f"attribute of imported {binding.kind} binding", 1
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
    return "unresolved", [], "expression is dynamic", 0
