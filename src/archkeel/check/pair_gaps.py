# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Drop the gap of a module pair that the contract allows (#953, AD-357).

The Rust collector writes a pair gap (`source_module` `a`, `module` `b`) when it cannot tell
whether `a` uses `b`. The host drops it only when the edge `a -> b` changes no verdict: one
component or a `requires` without `through`; no rule names `a` or `b` by module, and every rule kind
is edge-free or a cycle rule; and `b` does not reach `a` (module level) or the component of `a`
(component level) through the edges and every pair gap, which each may be an edge. A contract with
inside contracts keeps every gap.
"""

from __future__ import annotations

from dataclasses import asdict, replace

from archkeel.ir.facts import Record, SourceFacts, SourceProfile, SourceSectionName, in_scope
from archkeel.ir.model import ArchitectureContract, CycleLevel, NoComponentCyclesRule
from archkeel.ir.model import ArchitectureRuleKind as Kind

_MODULE_FIELDS = {
    Kind.FORBIDDEN_DEPENDENCY: ("source", "target", "allowed_sources"),
    Kind.ALLOWED_DEPENDENCY: ("source", "target"),
    Kind.SIBLING_ISOLATION: ("members",),
}
_EDGE_FREE = {Kind.COMPLETE_ASSIGNMENT, Kind.COMPLETE_EXTERNAL_SCOPE, Kind.COMPLETE_REQUIRES}
_EDGE_FREE |= {Kind.EXTERNAL_DEPENDENCY_SCOPE, Kind.FORBIDDEN_CONSTRUCT, Kind.ROOT_LAYOUT}
_EDGE_FREE |= {Kind.NO_COMPONENT_CYCLES}
Edges = frozenset[tuple[str, str]]


def _named(contract: ArchitectureContract, modules: tuple[str, str]) -> bool:
    """Whether a rule names one of the modules, or is of a kind that this module does not know."""
    for rule in contract.rules:
        values, fields = asdict(rule), _MODULE_FIELDS.get(rule.kind, ())
        names = [
            n
            for f in fields
            for n in ([values[f]] if isinstance(values[f], str) else values[f] or ())
        ]
        overlap = any(in_scope(m, n) or in_scope(n, m) for n in names for m in modules)
        if overlap or (not fields and rule.kind not in _EDGE_FREE):
            return True
    return False


def _reaches(edges: Edges, start: str, goal: frozenset[str]) -> bool:
    seen = frontier = frozenset({start})
    while frontier and not frontier & goal:
        frontier = frozenset(t for s, t in edges if s in frontier) - seen
        seen |= frontier
    return bool(frontier & goal)


def _allowed(
    gap: Record, contract: ArchitectureContract, edges: Edges, modules: tuple[str, ...]
) -> bool:
    source, target = gap.data.get("source_module"), gap.data.get("module")
    if not isinstance(source, str) or not isinstance(target, str) or source == target:
        return False
    owner, used = contract.component_for(source), contract.component_for(target)
    if owner is None or used is None or _named(contract, (source, target)):
        return False
    if owner.id != used.id and not any(
        r.component == used.label and not r.through for r in owner.requires or ()
    ):
        return False
    levels = {
        r.level or CycleLevel.COMPONENT
        for r in contract.rules
        if isinstance(r, NoComponentCyclesRule)
    }
    if CycleLevel.MODULE in levels and _reaches(edges, target, frozenset({source})):
        return False
    owned = frozenset(m for m in modules if contract.component_for(m) == owner)
    return not (
        CycleLevel.COMPONENT in levels and owner.id != used.id and _reaches(edges, target, owned)
    )


def drop_allowed_pair_gaps(
    facts: SourceFacts, contract: ArchitectureContract, *, has_insides: bool
) -> SourceFacts:
    """The facts without each Rust pair gap that the contract allows; the same object otherwise."""
    pairs = [gap for gap in facts.coverage.gaps if gap.data.get("source_module") is not None]
    if facts.profile != SourceProfile.RUST or has_insides or not pairs:
        return facts
    records = [r for s in facts.sections if s.name == SourceSectionName.IMPORTS for r in s.records]
    ends = [
        (r.data.get("source_module"), r.data.get("target_module"))
        for r in records
        if r.kind != "macro_body"
    ]
    ends += [(gap.data.get("source_module"), gap.data.get("module")) for gap in pairs]
    edges = frozenset((s, t) for s, t in ends if isinstance(s, str) and isinstance(t, str))
    modules = tuple(item.module for item in facts.files)
    dropped = {gap.id for gap in pairs if _allowed(gap, contract, edges, modules)}
    if not dropped:
        return facts
    kept = tuple(gap for gap in facts.coverage.gaps if gap.id not in dropped)
    sections = tuple(
        replace(s, records=tuple(r for r in s.records if r.id not in dropped))
        if s.name == SourceSectionName.UNKNOWNS
        else s
        for s in facts.sections
    )
    return replace(
        facts, sections=sections, coverage=replace(facts.coverage, gaps=kept, full_scope=not kept)
    )
