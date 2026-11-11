# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Drop the gap of a module pair that the contract allows (#953, AD-355).

The Rust collector writes a pair gap when it cannot tell whether module `a` uses module `b`: a
method call that may reach a method of an `impl` block in `b`, or a trait of `b` that a glob brings
in. The gap names `a` as `source_module` and `b` as `module`. The edge `a -> b`, if it exists,
changes no verdict when the contract lets `a` use `b`:

- the component of `a` is the component of `b`, or requires it without a `through` port;
- no rule that names modules (`forbidden_dependency`, `allowed_dependency`, `sibling_isolation`)
  names a module of `a` or `b`, and no other rule kind than the ones listed below is declared;
- the edge closes no cycle that a cycle rule reads: at the module level `b` does not reach `a`,
  and at the component level `b` reaches no module of the component of `a`.

Only then the host drops the gap. A contract with inside contracts keeps every gap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, replace
from itertools import groupby
from operator import itemgetter

from archkeel.ir.facts import Record, SourceFacts, SourceProfile, SourceSectionName
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    CycleLevel,
    NoComponentCyclesRule,
)
from archkeel.ir.model import ArchitectureRuleKind as Kind

# The fields that name a module in a rule that reads the edges between modules.
_MODULE_FIELDS: dict[Kind, tuple[str, ...]] = {
    Kind.FORBIDDEN_DEPENDENCY: ("source", "target", "allowed_sources"),
    Kind.ALLOWED_DEPENDENCY: ("source", "target"),
    Kind.SIBLING_ISOLATION: ("members",),
}
# The rule kinds that an allowed edge between two modules cannot change: they read components and
# their declared requires, the files, the external edges or constructs. Cycles are checked below.
_UNCHANGED = frozenset(
    {
        Kind.COMPLETE_ASSIGNMENT,
        Kind.COMPLETE_EXTERNAL_SCOPE,
        Kind.COMPLETE_REQUIRES,
        Kind.EXTERNAL_DEPENDENCY_SCOPE,
        Kind.FORBIDDEN_CONSTRUCT,
        Kind.ROOT_LAYOUT,
        Kind.NO_COMPONENT_CYCLES,
    }
)


def _overlap(first: str, second: str) -> bool:
    return first == second or first.startswith(second + ".") or second.startswith(first + ".")


def _named_by_rule(contract: ArchitectureContract, modules: tuple[str, str]) -> bool:
    """Whether a rule names one of the modules, or is of a kind that this module does not know."""
    for rule in contract.rules:
        fields = _MODULE_FIELDS.get(rule.kind)
        if fields is None:
            if rule.kind not in _UNCHANGED:
                return True
            continue
        values = asdict(rule)
        names = [
            name
            for field in fields
            for name in ([values[field]] if isinstance(values[field], str) else values[field] or ())
        ]
        if any(_overlap(name, module) for name in names for module in modules):
            return True
    return False


def _requires(source: ContractComponent, target: ContractComponent) -> bool:
    if source.id == target.id:
        return True
    entries = source.requires or ()
    return any(entry.component == target.label and not entry.through for entry in entries)


def _reaches(edges: Mapping[str, frozenset[str]], start: str, goal: frozenset[str]) -> bool:
    seen = frozenset({start})
    frontier = seen
    while frontier and not frontier & goal:
        frontier = frozenset(t for m in frontier for t in edges.get(m, frozenset())) - seen
        seen = seen | frontier
    return bool(frontier & goal)


def _edges(facts: SourceFacts) -> dict[str, frozenset[str]]:
    pairs = [
        (record.data.get("source_module"), record.data.get("target_module"))
        for section in facts.sections
        if section.name == SourceSectionName.IMPORTS
        for record in section.records
        if record.kind != "macro_body"
    ]
    named = sorted((s, t) for s, t in pairs if isinstance(s, str) and isinstance(t, str))
    return {
        source: frozenset(target for _, target in group)
        for source, group in groupby(named, key=itemgetter(0))
    }


def _allowed(
    gap: Record,
    contract: ArchitectureContract,
    edges: Mapping[str, frozenset[str]],
    modules: Iterable[str],
) -> bool:
    source, target = gap.data.get("source_module"), gap.data.get("module")
    if not isinstance(source, str) or not isinstance(target, str) or source == target:
        return False
    owner, used = contract.component_for(source), contract.component_for(target)
    if owner is None or used is None or not _requires(owner, used):
        return False
    if _named_by_rule(contract, (source, target)):
        return False
    levels = {
        rule.level or CycleLevel.COMPONENT
        for rule in contract.rules
        if isinstance(rule, NoComponentCyclesRule)
    }
    if CycleLevel.MODULE in levels and _reaches(edges, target, frozenset({source})):
        return False
    if CycleLevel.COMPONENT in levels and owner.id != used.id:
        goal = frozenset(module for module in modules if contract.component_for(module) == owner)
        return not _reaches(edges, target, goal)
    return True


def drop_allowed_pair_gaps(
    facts: SourceFacts, contract: ArchitectureContract, *, has_insides: bool
) -> SourceFacts:
    """The facts without each Rust pair gap that the contract allows; the same object otherwise."""
    pairs = [gap for gap in facts.coverage.gaps if gap.data.get("source_module") is not None]
    if facts.profile != SourceProfile.RUST or has_insides or not pairs:
        return facts
    edges = _edges(facts)
    modules = tuple(item.module for item in facts.files)
    dropped = {gap.id for gap in pairs if _allowed(gap, contract, edges, modules)}
    if not dropped:
        return facts
    kept = tuple(gap for gap in facts.coverage.gaps if gap.id not in dropped)
    sections = tuple(
        replace(section, records=tuple(r for r in section.records if r.id not in dropped))
        if section.name == SourceSectionName.UNKNOWNS
        else section
        for section in facts.sections
    )
    coverage = replace(facts.coverage, gaps=kept, full_scope=not kept)
    return replace(facts, sections=sections, coverage=coverage)
