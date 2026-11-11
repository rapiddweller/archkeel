# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Drop the gap of a module pair that the contract allows (#953, AD-357).

The Rust collector writes a pair gap (`source_module` `a`, `module` `b`) when it cannot tell
whether `a` uses `b`. The host drops it only when the edge changes no verdict: one component or a
`requires` without `through`; no rule names `a` or `b` by module and each rule kind is edge-free or
a cycle rule; and, for each cycle level, `b` does not reach `a` in the graph of the known edges plus
every pair gap. A contract with inside contracts keeps every gap.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from itertools import groupby
from operator import itemgetter

from archkeel.ir.facts import Record, SourceFacts, SourceProfile, SourceSectionName, in_scope
from archkeel.ir.model import ArchitectureContract, CycleLevel, NoComponentCyclesRule
from archkeel.ir.model import ArchitectureRuleKind as Kind

Pairs = frozenset[tuple[str, str]]
_FIELDS: dict[Kind, tuple[str, ...]] = {
    Kind.FORBIDDEN_DEPENDENCY: ("source", "target", "allowed_sources")
}
_FIELDS |= {Kind.ALLOWED_DEPENDENCY: ("source", "target"), Kind.SIBLING_ISOLATION: ("members",)}
_EDGE_FREE = {Kind.COMPLETE_ASSIGNMENT, Kind.COMPLETE_EXTERNAL_SCOPE, Kind.COMPLETE_REQUIRES}
_EDGE_FREE |= {Kind.EXTERNAL_DEPENDENCY_SCOPE, Kind.FORBIDDEN_CONSTRUCT, Kind.ROOT_LAYOUT}
_EDGE_FREE |= {Kind.NO_COMPONENT_CYCLES}


def _named(contract: ArchitectureContract, ends: tuple[str, str]) -> bool:
    """Whether a rule names one of the modules, or is of a kind that this module does not know."""
    for rule in contract.rules:
        values, fields = asdict(rule), _FIELDS.get(rule.kind, ())
        found = [values[f] for f in fields]
        names = [n for v in found for n in ([v] if isinstance(v, str) else v or ())]
        if any(in_scope(m, n) or in_scope(n, m) for n in names for m in ends):
            return True
        if not fields and rule.kind not in _EDGE_FREE:
            return True
    return False


def _cyclic(edges: Pairs, starts: set[str], active: bool) -> Pairs:
    """Each (x, y) where the start y reaches x: with the edge x -> y, one cycle group."""
    succ = {s: frozenset(t for _, t in g) for s, g in groupby(sorted(edges), key=itemgetter(0))}
    found: set[tuple[str, str]] = set()
    for start in (starts & succ.keys()) if active else set():
        seen = frontier = succ[start]
        while frontier:
            frontier = frozenset(t for m in frontier for t in succ.get(m, frozenset())) - seen
            seen |= frontier
        found |= {(target, start) for target in seen}
    return frozenset(found)


def drop_allowed_pair_gaps(
    facts: SourceFacts, contract: ArchitectureContract, *, has_insides: bool
) -> SourceFacts:
    """The facts without each Rust pair gap that the contract allows; the same object otherwise."""
    gaps = [(g, g.data.get("source_module"), g.data.get("module")) for g in facts.coverage.gaps]
    pairs = [(g, a, b) for g, a, b in gaps if isinstance(a, str) and isinstance(b, str) and a != b]
    if facts.profile != SourceProfile.RUST or has_insides or not pairs:
        return facts
    imports = [s.records for s in facts.sections if s.name == SourceSectionName.IMPORTS]
    found = [r for rs in imports for r in rs if r.kind != "macro_body"]
    ends = [(r.data.get("source_module"), r.data.get("target_module")) for r in found]
    edges: Pairs = frozenset((s, t) for s, t in ends if isinstance(s, str) and isinstance(t, str))
    edges |= {(a, b) for _, a, b in pairs}
    owner = {m: c for m in {x for e in edges for x in e} if (c := contract.component_for(m))}
    rules = [r.level for r in contract.rules if isinstance(r, NoComponentCyclesRule)]
    module_cycles = _cyclic(edges, {b for _, _, b in pairs}, CycleLevel.MODULE in rules)
    parts = frozenset((owner[s].id, owner[t].id) for s, t in edges if s in owner and t in owner)
    used = {owner[b].id for _, _, b in pairs if b in owner}
    part_cycles = _cyclic(parts, used, any(level != CycleLevel.MODULE for level in rules))
    dropped: set[str] = set()
    for gap, a, b in pairs:
        source, target = owner.get(a), owner.get(b)
        if source is None or target is None or _named(contract, (a, b)) or (a, b) in module_cycles:
            continue
        through = [r.through for r in source.requires or () if r.component == target.label]
        crossing = () in through and (source.id, target.id) not in part_cycles
        dropped |= {gap.id} if source.id == target.id or crossing else set()
    if not dropped:
        return facts

    def without(records: tuple[Record, ...]) -> tuple[Record, ...]:
        return tuple(r for r in records if r.id not in dropped)

    u = SourceSectionName.UNKNOWNS
    sections = [
        replace(s, records=without(s.records)) if s.name == u else s for s in facts.sections
    ]
    kept = without(facts.coverage.gaps)
    coverage = replace(facts.coverage, gaps=kept, full_scope=not kept)
    return replace(facts, sections=tuple(sections), coverage=coverage)
