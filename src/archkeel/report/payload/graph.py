# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Units, direct edges and the names that cross them (AD-361).

A crossing is stored once, on its module edge. A component or package edge lists its module
edges in `via` and carries no crossing of its own. A pair that the contract allows and
that no import uses is a component edge with zero sites: the target is visible next to the actual.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import (
    ABSENT,
    DECL_CHARS,
    EDGE_TARGET,
    KIND,
    LEVEL,
    PERMISSION,
    VIS,
    code,
)
from archkeel.report.payload.permissions import Permission, permission_of, requires_pairs
from archkeel.report.payload.records import Import, Records, Symbol
from archkeel.report.payload.tree import Tree

_VISIBILITY = {
    "public": "public",
    "crate": "package",
    "package": "package",
    "internal": "package",
    "private": "private",
}
_SIMPLE_KINDS = {
    "function": "function",
    "method": "method",
    "constant": "constant",
    "type_alias": "type_alias",
    "macro": "macro",
    "dynamic_binding": "variable",
    "variable": "variable",
}


@dataclass(frozen=True)
class Unit:
    module: int
    name: str
    kind: int
    vis: int
    line: int
    parent: int
    decl: str
    static: int
    qualified_name: str
    variants: tuple[str, ...]


@dataclass(frozen=True)
class Crossing:
    name: str
    kind: int
    unit: int
    sites: int
    line: int
    reexport: int


@dataclass(frozen=True)
class Edge:
    level: int
    source: int
    target: int
    names: int
    sites: int
    target_state: int
    rationale: str | None
    via: tuple[int, ...]
    crossings: tuple[Crossing, ...]


def unit_kind(symbol: Symbol, language: str) -> str:
    """Map a symbol record to one kind of the closed list."""
    rust = language == "rust"
    if symbol.kind == "class":
        if symbol.class_kind == "enum":
            return "enum"
        if symbol.class_kind in ("protocol", "trait", "interface"):
            return "trait" if rust else "interface"
        return "struct" if rust else "class"
    if symbol.kind == "static_constant":
        return "static" if rust else "constant"
    return _SIMPLE_KINDS.get(symbol.kind, "unknown")


def decl_text(text: str) -> str:
    """Cut a declaration line: strip ASCII spaces and tabs, keep at most 72 code points."""
    return text.strip(" \t")[:DECL_CHARS]


def build_units(records: Records, tree: Tree) -> tuple[Unit, ...]:
    """Return the units, sorted by module, line, name, kind and record id."""
    rows = []
    for symbol in records.symbols:
        module = tree.module_node.get(symbol.module)
        if module is None:
            continue
        kind = unit_kind(symbol, records.language)
        vis = _VISIBILITY.get(symbol.visibility or "", "unknown")
        rows.append((module, symbol.line, symbol.name, code(KIND, kind), symbol.id, symbol, vis))
    rows.sort(key=lambda r: r[:5])
    first: dict[str, int] = {}
    for position, row in enumerate(rows):
        first.setdefault(row[5].qualified_name, position)
    return tuple(
        Unit(
            module=module,
            name=name,
            kind=kind,
            vis=code(VIS, vis),
            line=line,
            parent=first.get(symbol.parent, ABSENT) if symbol.parent else ABSENT,
            decl=decl_text(symbol.decl),
            static=int(symbol.static),
            qualified_name=symbol.qualified_name,
            variants=symbol.variants if kind == code(KIND, "enum") else (),
        )
        for module, line, name, kind, _, symbol, vis in rows
    )


class _Binder:
    def __init__(self, units: Sequence[Unit]) -> None:
        self.by_name: dict[str, int] = {}
        top: defaultdict[tuple[int, str], list[int]] = defaultdict(list)
        for position, unit in enumerate(units):
            self.by_name.setdefault(unit.qualified_name, position)
            if unit.parent == ABSENT:
                top[(unit.module, unit.name)].append(position)
        self.top = {key: found[0] for key, found in top.items() if len(found) == 1}
        self.units = units

    def bind(self, name: str, target: int, imports: Sequence[Import]) -> tuple[int, int]:
        if name == "*":
            return code(KIND, "module"), ABSENT
        for item in imports:
            if item.origin and item.origin in self.by_name:
                found = self.by_name[item.origin]
                return self.units[found].kind, found
        found = self.top.get((target, name), ABSENT)
        return (
            (self.units[found].kind, found) if found != ABSENT else (code(KIND, "unknown"), ABSENT)
        )


def _crossings(imports: Sequence[Import], target: int, binder: _Binder) -> tuple[Crossing, ...]:
    groups: defaultdict[str, list[Import]] = defaultdict(list)
    for item in sorted(imports, key=lambda i: i.id):
        groups[item.symbol or "*"].append(item)
    out = []
    for name in sorted(groups):
        group = groups[name]
        lines = [i.line for i in group if i.line > 0]
        kind, unit = binder.bind(name, target, group)
        reexport = int(any(i.reexport for i in group))
        out.append(
            Crossing(name, kind, unit, len(group), min(lines) if lines else ABSENT, reexport)
        )
    return tuple(out)


_STATE = {"allowed": "declared", "forbidden": "forbidden", "undecided": "undeclared"}


def _state(
    pair: tuple[int, int] | None,
    permissions: Mapping[tuple[int, int], Permission],
    has_target: bool,
) -> int:
    """The target of an edge: the permission of its component pair; none without Target."""
    if pair is None or not has_target or pair not in permissions:
        return code(EDGE_TARGET, "no_target")
    return code(EDGE_TARGET, _STATE[PERMISSION[permissions[pair].status]])


def _pair(tree: Tree, source: str, target: str) -> tuple[int, int] | None:
    left, right = tree.chain.get(source, ()), tree.chain.get(target, ())
    for depth in range(min(len(left), len(right))):
        if left[depth] != right[depth]:
            return left[depth], right[depth]
    return None


def _aggregate(
    level: str,
    pair: tuple[int, int],
    via: list[int],
    modules: Sequence[Edge],
    state: int,
    why: str | None,
) -> Edge:
    names = {(modules[i].target, c.name) for i in via for c in modules[i].crossings}
    sites = sum(modules[i].sites for i in via)
    return Edge(code(LEVEL, level), pair[0], pair[1], len(names), sites, state, why, tuple(via), ())


def _module_facts(records: Records, tree: Tree) -> dict[tuple[str, str], set[str]]:
    facts: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for edge in records.module_edges:
        if (
            edge.source != edge.target
            and edge.source in tree.module_node
            and edge.target in tree.module_node
        ):
            facts[(edge.source, edge.target)].update(edge.fact_ids)
    return facts


def build_edges(
    records: Records, tree: Tree, units: Sequence[Unit], permissions: Sequence[Permission]
) -> tuple[Edge, ...]:
    """Return module edges, then component edges, then package edges; each by from, then to.

    A pair that the contract allows and that no import uses is a component edge with zero sites.
    """
    facts = _module_facts(records, tree)
    allowed = permission_of(permissions)
    has_target = records.contract is not None
    rationale = {
        (tree.component_node[a], tree.component_node[b]): why
        for (a, b), why in requires_pairs(records).items()
    }
    binder = _Binder(units)
    modules: list[Edge] = []
    by_component: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    by_package: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for source, target in sorted(
        facts, key=lambda p: (tree.module_node[p[0]], tree.module_node[p[1]])
    ):
        imports = [records.imports[i] for i in facts[(source, target)] if i in records.imports]
        crossings = _crossings(imports, tree.module_node[target], binder)
        pair = _pair(tree, source, target)
        s, t = tree.module_node[source], tree.module_node[target]
        state = _state(pair, allowed, has_target)
        modules.append(
            Edge(
                code(LEVEL, "module"),
                s,
                t,
                len(crossings),
                max(1, len(imports)),
                state,
                None,
                (),
                crossings,
            )
        )
        if pair is not None:
            by_component[pair].append(len(modules) - 1)
        ps, pt = tree.package[s], tree.package[t]
        if ABSENT not in (ps, pt) and ps != pt:
            by_package[(ps, pt)].append(len(modules) - 1)
    unused = {
        pair for pair, p in allowed.items() if has_target and PERMISSION[p.status] == "allowed"
    }
    components = [
        _aggregate(
            "component",
            pair,
            by_component.get(pair, []),
            modules,
            _state(pair, allowed, has_target),
            rationale.get(pair),
        )
        for pair in sorted(set(by_component) | unused)
    ]
    packages = [
        _aggregate("package", pair, by_package[pair], modules, code(EDGE_TARGET, "no_target"), None)
        for pair in sorted(by_package)
    ]
    return (*modules, *components, *packages)
