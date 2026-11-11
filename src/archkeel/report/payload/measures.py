# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Findings, node counts and measures of the payload (AD-361).

Every value is a join or a count over the tree, the units and the direct edges. A measure has
a budget only when a root contract rule sets it, and a verdict only with a budget.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from archkeel.report.payload.codes import (
    ABSENT,
    DATA_KINDS,
    DISPOSITION,
    EDGE_TARGET,
    KIND,
    LEVEL,
    MEASURE,
    MEASURE_STATE,
    VERDICT,
    VIS,
    code,
)
from archkeel.report.payload.findings import Finding
from archkeel.report.payload.graph import Edge, Unit
from archkeel.report.payload.records import Records
from archkeel.report.payload.tree import SYSTEM, Tree

_FIRST_EVIDENCE = code(MEASURE, "E.known")
_MODULE, _COMPONENT, _PACKAGE = (
    code(LEVEL, "module"),
    code(LEVEL, "component"),
    code(LEVEL, "package"),
)
_PER_LEVEL = {
    code(LEVEL, "system"): MEASURE,
    _PACKAGE: (
        "R.clear",
        "R.owned",
        "R.size",
        "I.surface",
        "D.resolved",
        "D.types",
        "D.signatures",
        "E.known",
    ),
    _COMPONENT: tuple(m for m in MEASURE if m not in ("E.parsed", "E.excluded")),
    _MODULE: ("R.clear", "R.size", "I.surface", "D.resolved", "D.types", "D.signatures", "E.known"),
}


@dataclass(frozen=True)
class MeasureRow:
    node: int
    measure: int
    state: int
    value: int = ABSENT
    of: int = ABSENT
    gap: str | None = None
    budget: int = ABSENT
    budget_source: str | None = None
    verdict: int = field(default=0)


@dataclass(frozen=True)
class NodeCounts:
    modules: tuple[int, ...]
    units: tuple[int, ...]
    fan_in: tuple[int, ...]
    fan_out: tuple[int, ...]


def _module_edges(edges: Sequence[Edge]) -> list[Edge]:
    return [e for e in edges if e.level == _MODULE]


def _under(tree: Tree) -> dict[int, set[int]]:
    under: dict[int, set[int]] = {n: set() for n in range(len(tree.level))}
    for module, above in tree.ancestors.items():
        for node in above:
            under[node].add(module)
    return under


def node_counts(tree: Tree, units: Sequence[Unit], edges: Sequence[Edge]) -> NodeCounts:
    """Return modules, units, fan-in and fan-out per node (distinct modules outside the node)."""
    under = _under(tree)
    per_module: dict[int, int] = {}
    for unit in units:
        per_module[unit.module] = per_module.get(unit.module, 0) + 1
    fan_in: defaultdict[int, set[int]] = defaultdict(set)
    fan_out: defaultdict[int, set[int]] = defaultdict(set)
    for edge in _module_edges(edges):
        above_s, above_t = tree.ancestors[edge.source], tree.ancestors[edge.target]
        for node in above_t - above_s:
            fan_in[node].add(edge.source)
        for node in above_s - above_t:
            fan_out[node].add(edge.target)
    nodes = range(len(tree.level))
    return NodeCounts(
        modules=tuple(len(under[n]) for n in nodes),
        units=tuple(sum(per_module.get(m, 0) for m in under[n]) for n in nodes),
        fan_in=tuple(len(fan_in.get(n, ())) for n in nodes),
        fan_out=tuple(len(fan_out.get(n, ())) for n in nodes),
    )


class _Tally:
    def __init__(self) -> None:
        self.resolved: dict[int, list[int]] = {}
        self.types: dict[int, list[int]] = {}
        self.used: defaultdict[int, set[int]] = defaultdict(set)
        self.api: dict[int, list[int]] = {}

    def add(self, table: dict[int, list[int]], node: int, hit: bool) -> None:
        pair = table.setdefault(node, [0, 0])
        pair[0] += int(hit)
        pair[1] += 1


def _tally(tree: Tree, edges: Sequence[Edge]) -> _Tally:
    tally = _Tally()
    unknown, module_kind = code(KIND, "unknown"), code(KIND, "module")
    data = {code(KIND, k) for k in DATA_KINDS}
    for edge in _module_edges(edges):
        above_s, above_t = tree.ancestors[edge.source], tree.ancestors[edge.target]
        entering = above_t - above_s
        for crossing in edge.crossings:
            if crossing.kind == module_kind:
                continue
            for node in above_s | above_t:
                tally.add(tally.resolved, node, crossing.kind != unknown)
                if crossing.kind != unknown:
                    tally.add(tally.types, node, crossing.kind in data)
            for node in entering:
                if crossing.unit != ABSENT:
                    tally.used[node].add(crossing.unit)
                component = tree.component_of_node.get(node)
                if component is not None and component.public_api is not None:
                    tally.add(tally.api, node, crossing.name in component.public_api)
    return tally


def _budget(records: Records, evaluated: frozenset[str], kind: str) -> str | None:
    """Return the root rule that sets the budget, only when the evaluator proved that rule."""
    rules = sorted(
        r.id
        for r in records.rule_declarations
        if r.kind == kind and r.parent_id is None and r.id in evaluated
    )
    return rules[0] if rules and records.contract is not None else None


def _ratio(
    node: int, measure: str, value: int, of: int, source: str | None = None
) -> MeasureRow | None:
    if of <= 0:
        return None
    if source is None:
        # No budget and no baseline: G-BUDGETS says "no limit", which differs from "not collected".
        return MeasureRow(node, code(MEASURE, measure), 0, value, of, "G-BUDGETS")
    verdict = code(VERDICT, "within" if value >= of else "over")
    return MeasureRow(node, code(MEASURE, measure), 0, value, of, None, of, source, verdict)


def _gap(node: int, measure: str, state: str, gap: str) -> MeasureRow:
    return MeasureRow(node, code(MEASURE, measure), code(MEASURE_STATE, state), gap=gap)


@dataclass(frozen=True)
class _Context:
    records: Records
    tree: Tree
    tally: _Tally
    evaluated: frozenset[str]
    ranked: frozenset[int]
    owned: frozenset[int]
    observed: tuple[Edge, ...]
    public_of: Mapping[int, frozenset[int]]
    callables: frozenset[int]
    lists: bool


def _context(
    records: Records,
    tree: Tree,
    units: Sequence[Unit],
    edges: Sequence[Edge],
    findings: Sequence[Finding],
    evaluated: frozenset[str],
) -> _Context:
    public = code(VIS, "public")
    callable_kinds = {code(KIND, "function"), code(KIND, "method")}
    public_of: defaultdict[int, set[int]] = defaultdict(set)
    for position, unit in enumerate(units):
        if unit.vis == public and unit.parent == ABSENT:
            public_of[unit.module].add(position)
    return _Context(
        records=records,
        tree=tree,
        tally=_tally(tree, edges),
        evaluated=evaluated,
        ranked=frozenset(
            f.subject for f in findings if f.disposition == code(DISPOSITION, "ranked")
        ),
        owned=frozenset(tree.module_node[m] for m in tree.chain),
        observed=tuple(e for e in edges if e.level == _COMPONENT and e.sites > 0),
        public_of={m: frozenset(found) for m, found in public_of.items()},
        callables=frozenset(
            u.module for u in units if u.vis == public and u.kind in callable_kinds
        ),
        lists=any(tree.component_of_node[c].public_api is not None for c in tree.component_of_node),
    )


def _declared(
    ctx: _Context, node: int, level: int, mods: set[int], comps: set[int]
) -> dict[str, MeasureRow | None]:
    """Return the measures that need a contract; undeclared rows without one."""
    if ctx.records.contract is None:
        return {
            m: _gap(node, m, "undeclared", "G-NO-CONTRACT") if mods else None
            for m in ("R.clear", "R.owned", "I.api", "D.declared")
        }
    components = ctx.tree.component_of_node
    stated = sum(1 for c in comps if components[c].responsibilities and components[c].forbidden)
    mine = [e for e in ctx.observed if e.source in comps]
    hits = sum(1 for e in mine if e.target_state == code(EDGE_TARGET, "declared"))
    owner = _budget(ctx.records, ctx.evaluated, "complete_assignment")
    requires = _budget(ctx.records, ctx.evaluated, "complete_requires")
    api = (
        ctx.tally.api.get(node)
        if level == _COMPONENT
        else _sum_api(ctx.tally, comps)
        if node == SYSTEM
        else None
    )
    return {
        "R.clear": _ratio(node, "R.clear", len((mods & ctx.owned) - ctx.ranked), len(mods)),
        "R.owned": _ratio(node, "R.owned", len(mods & ctx.owned), len(mods), owner),
        "R.stated": _ratio(node, "R.stated", stated, len(comps)),
        "I.declared": _ratio(node, "I.declared", hits, len(mine), requires),
        "I.api": _ratio(node, "I.api", api[0], api[1])
        if api and ctx.lists
        else _gap(node, "I.api", "undeclared", "G-PUBLIC-API"),
        "D.declared": _gap(node, "D.declared", "undeclared", "G-BOUNDARY-TYPES"),
    }


def _observed(ctx: _Context, node: int, mods: set[int]) -> dict[str, MeasureRow | None]:
    """Return the measures that need no contract."""
    top_public = {unit for m in mods for unit in ctx.public_of.get(m, frozenset())}
    used = ctx.tally.used.get(node, set())
    resolved, types = ctx.tally.resolved.get(node, [0, 0]), ctx.tally.types.get(node, [0, 0])
    out = {
        "R.size": _gap(node, "R.size", "unknown", "G-CODE-LINES") if mods else None,
        "I.surface": _ratio(node, "I.surface", len(top_public & used), len(top_public))
        if node != SYSTEM
        else None,
        "D.resolved": _ratio(node, "D.resolved", resolved[0], resolved[1]),
        "D.types": _ratio(node, "D.types", types[0], types[1]),
        "D.signatures": _gap(node, "D.signatures", "unknown", "G-SIGNATURES")
        if mods & ctx.callables
        else None,
    }
    if node == SYSTEM:
        discovered, _, parsed = ctx.records.coverage
        out["E.parsed"] = _ratio(node, "E.parsed", parsed, discovered)
        out["E.excluded"] = _gap(node, "E.excluded", "unknown", "G-EXCLUDED")
    return out


def build_measures(
    records: Records,
    tree: Tree,
    units: Sequence[Unit],
    edges: Sequence[Edge],
    findings: Sequence[Finding],
    evaluated: frozenset[str],
) -> tuple[MeasureRow, ...]:
    """Return the measure rows by node, then measure; a row that does not apply is left out."""
    ctx = _context(records, tree, units, edges, findings, evaluated)
    under = _under(tree)
    rows: list[MeasureRow] = []
    for node, level in enumerate(tree.level):
        mods = under[node]
        comps = set()
        if level not in (_PACKAGE, _MODULE):
            comps = {
                c
                for c in tree.component_of_node
                if node == SYSTEM or c == node or _below(tree, c, node)
            }
        out = {**_declared(ctx, node, level, mods, comps), **_observed(ctx, node, mods)}
        kept = [r for m, r in out.items() if r is not None and m in _PER_LEVEL[level]]
        panels = [r for r in kept if r.measure < _FIRST_EVIDENCE]
        known = sum(1 for r in panels if r.state == code(MEASURE_STATE, "measured"))
        unknown = sum(1 for r in panels if r.state == code(MEASURE_STATE, "unknown"))
        evidence = _ratio(node, "E.known", known, known + unknown)
        rows.extend((*kept, evidence) if evidence is not None else kept)
    rows.sort(key=lambda r: (r.node, r.measure))
    return tuple(rows)


def _below(tree: Tree, node: int, ancestor: int) -> bool:
    cursor = tree.parent[node]
    while cursor != ABSENT:
        if cursor == ancestor:
            return True
        cursor = tree.parent[cursor]
    return False


def _sum_api(tally: _Tally, comps: set[int]) -> list[int] | None:
    pairs = [tally.api[c] for c in comps if c in tally.api]
    return [sum(p[0] for p in pairs), sum(p[1] for p in pairs)] if pairs else None


def gap_blocks(rows: Sequence[MeasureRow]) -> Mapping[str, int]:
    """Count the measure rows that each gap blocks."""
    out: dict[str, int] = {}
    for row in rows:
        if row.gap is not None:
            out[row.gap] = out.get(row.gap, 0) + 1
    return out
