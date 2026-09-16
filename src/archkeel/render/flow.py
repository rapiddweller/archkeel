# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive the component flow view from one observation alone (AD-10)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Literal

from archkeel.ir.decisions import decided_module_pairs, inner_opt_ins, open_decisions
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.model import Observation, Record, text_value

EdgeState = Literal["conforms", "violation", "undecided", "observed"]


@dataclass(frozen=True, slots=True)
class FlowInnerEdge:
    """One import between two modules of the same component.

    Inside a component no rule decides a pair by default (AD-24), so an inner edge is
    `observed` unless a rule speaks about those two modules directly - `sibling_isolation`
    over peers, or a dependency rule scoped below the component. Reporting every inner edge
    as undecided hid those verdicts, which is why the state travels with the edge.

    `observed` is not `undecided`: at component level undecided means a decision is owed and
    `validate` reports it, while here none is expected and validate demands none. Sharing one
    colour claimed 90 open decisions this repository does not have.
    """

    source: str
    target: str
    import_sites: int
    rule_ids: tuple[str, ...] = ()
    state: EdgeState = "observed"


@dataclass(frozen=True, slots=True)
class FlowSymbol:
    """One top-level function or class of a module, with the methods it owns (AD-24a)."""

    name: str
    kind: str
    visibility: str
    members: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FlowSymbolEdge:
    """One call or reference between two top-level symbols of the same module."""

    source: str
    target: str


@dataclass(frozen=True, slots=True)
class FlowModule:
    """What one module holds, and the names that cross its edge in either direction."""

    symbols: tuple[FlowSymbol, ...]
    edges: tuple[FlowSymbolEdge, ...]
    exports: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FlowComponent:
    label: str
    modules: tuple[str, ...]
    public: tuple[str, ...] | None
    inner_edges: tuple[FlowInnerEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class FlowEdge:
    source: str
    target: str
    import_sites: int
    rule_ids: tuple[str, ...]
    state: EdgeState


@dataclass(frozen=True, slots=True)
class FlowData:
    components: tuple[FlowComponent, ...]
    edges: tuple[FlowEdge, ...]
    modules: dict[str, FlowModule] = field(default_factory=dict)


def _public_interface(record: Record) -> tuple[str, ...] | None:
    public = record.data.get("public")
    if not isinstance(public, tuple):
        return None
    return tuple(entry for entry in public if isinstance(entry, str))


def _modules_by_owner(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for module in observation.records("modules") or ():
        name = module.data.get("qualified_name")
        if not isinstance(name, str):
            continue
        owner = owner_of(name, components)
        if owner is not None:
            grouped[owner].append(name)
    return grouped


def _component_edges(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[tuple[str, str], int]:
    """Sum import-site counts per observed module edge onto its owning component pair."""
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for edge in observation.records("dependency_edges") or ():
        if edge.data.get("level") != "module":
            continue
        source, target, count = (edge.data.get(key) for key in ("source", "target", "count"))
        if not isinstance(source, str) or not isinstance(target, str) or not isinstance(count, int):
            continue
        owner_source = owner_of(source, components)
        owner_target = owner_of(target, components)
        if owner_source is None or owner_target is None or owner_source == owner_target:
            continue
        totals[(owner_source, owner_target)] += count
    return totals


def _module_pair_rules(observation: Observation) -> dict[tuple[str, str], tuple[str, ...]]:
    """Map each violated module pair to its rule ids.

    Every violation that names two modules carries them as `source_module` and
    `target_module`, whatever its kind, so one lookup serves sibling isolation and the
    dependency rules alike instead of a branch per kind.
    """
    found: dict[tuple[str, str], set[str]] = defaultdict(set)
    for violation in observation.records("violations") or ():
        source = text_value(violation.data.get("source_module"))
        target = text_value(violation.data.get("target_module"))
        if source and target:
            found[(source, target)].update(violation.rule_ids)
    return {pair: tuple(sorted(ids)) for pair, ids in found.items()}


def _inner_edges(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[str, list[FlowInnerEdge]]:
    """Group the module edges that stay inside one component (AD-24), by that component."""
    grouped: dict[str, list[FlowInnerEdge]] = defaultdict(list)
    pair_rules = _module_pair_rules(observation)
    opted = inner_opt_ins(observation)
    decided = decided_module_pairs(observation)
    for edge in observation.records("dependency_edges") or ():
        if edge.data.get("level") != "module":
            continue
        source, target, count = (edge.data.get(key) for key in ("source", "target", "count"))
        if not isinstance(source, str) or not isinstance(target, str) or not isinstance(count, int):
            continue
        owner = owner_of(source, components)
        if owner is None or owner != owner_of(target, components):
            continue
        rule_ids = pair_rules.get((source, target), ())
        # AD-31: inside a component that opted in a decision is owed again, so an undecided
        # pair there is `undecided`, not the neutral `observed` of AD-24b.
        if rule_ids:
            state: EdgeState = "violation"
        elif (source, target) in decided or owner not in opted:
            state = "observed"
        else:
            state = "undecided"
        grouped[owner].append(FlowInnerEdge(source, target, count, rule_ids, state))
    return {
        owner: sorted(edges, key=lambda item: (item.source, item.target))
        for owner, edges in grouped.items()
    }


def _module_symbols(
    observation: Observation,
) -> tuple[dict[str, list[FlowSymbol]], dict[str, str]]:
    """Return each module's top-level symbols, and the card every symbol belongs to.

    A method is a line inside the card of the class that owns it, never a card of its own,
    so the second return value folds any qualified name onto the card that shows it.
    """
    cards: dict[str, list[FlowSymbol]] = defaultdict(list)
    members: dict[str, list[str]] = defaultdict(list)
    owner_card: dict[str, str] = {}
    for record in observation.records("symbols") or ():
        qualified = text_value(record.data.get("qualified_name"))
        module = text_value(record.data.get("module"))
        if not qualified or not module:
            continue
        parent = text_value(record.data.get("parent"))
        if parent:
            members[parent].append(text_value(record.data.get("name")))
            owner_card[qualified] = parent
            continue
        owner_card[qualified] = qualified
        cards[module].append(
            FlowSymbol(
                name=qualified,
                kind=text_value(record.data.get("symbol_category")),
                visibility=text_value(record.data.get("visibility")),
            )
        )
    return {
        module: sorted(
            (
                replace(symbol, members=tuple(sorted(members.get(symbol.name, ()))))
                for symbol in symbols
            ),
            key=lambda item: item.name,
        )
        for module, symbols in cards.items()
    }, owner_card


def _symbol_edges(
    observation: Observation, owner_card: dict[str, str], module_of: dict[str, str]
) -> dict[str, list[FlowSymbolEdge]]:
    """Group every call and reference that stays inside one module, by that module."""
    found: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for section in ("calls", "references"):
        for record in observation.records(section) or ():
            source = owner_card.get(text_value(record.data.get("source_scope")))
            targets = record.data.get("targets")
            if source is None or not isinstance(targets, tuple | list):
                continue
            module = module_of.get(source)
            for value in targets:
                target = owner_card.get(text_value(value))
                if target is not None and target != source and module_of.get(target) == module:
                    found[module or ""].add((source, target))
    return {
        module: [FlowSymbolEdge(source, target) for source, target in sorted(pairs)]
        for module, pairs in found.items()
    }


def _crossing_names(observation: Observation) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Name what each module publishes outward and what it reaches for, from imports alone."""
    exports: dict[str, set[str]] = defaultdict(set)
    imports: dict[str, set[str]] = defaultdict(set)
    for record in observation.records("imports") or ():
        source = text_value(record.data.get("source_module"))
        target = text_value(record.data.get("target_module"))
        symbol = text_value(record.data.get("symbol"))
        if not source or not target or source == target:
            continue
        crossing = f"{target}:{symbol}" if symbol else target
        imports[source].add(crossing)
        exports[target].add(symbol or target)
    return exports, imports


def _modules_inside(observation: Observation) -> dict[str, FlowModule]:
    """Build the third level: what each module holds and what crosses its edge (AD-24a)."""
    symbols, owner_card = _module_symbols(observation)
    module_of = {
        card: module for module, items in symbols.items() for card in (s.name for s in items)
    }
    edges = _symbol_edges(observation, owner_card, module_of)
    exports, imports = _crossing_names(observation)
    return {
        module: FlowModule(
            symbols=tuple(items),
            edges=tuple(edges.get(module, ())),
            exports=tuple(sorted(exports.get(module, ()))),
            imports=tuple(sorted(imports.get(module, ()))),
        )
        for module, items in symbols.items()
    }


def _violated_pairs(
    violation: Record, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[tuple[str, str], ...]:
    """Return the component pair(s) one violation implicates, or none for a single-subject rule."""
    if violation.kind == "no_component_cycles":
        # Members are already component labels; the cycle indicts every ordered pair among them.
        members = violation.subjects
        return tuple(
            (source, target) for source in members for target in members if source != target
        )
    source = violation.data.get("source_component")
    target = violation.data.get("target_component")
    if not isinstance(source, str) or not isinstance(target, str):
        source_module = violation.data.get("source_module")
        target_module = violation.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            return ()
        source = owner_of(source_module, components)
        target = owner_of(target_module, components)
    if source is None or target is None or source == target:
        return ()
    return ((source, target),)


def build_flow(observation: Observation) -> FlowData:
    """Return the component flow view derived from one observation alone (AD-10)."""
    declared = [
        record
        for record in observation.records("declarations") or ()
        if record.kind == "component_responsibility"
    ]
    components = component_owners(observation)
    modules_by_owner = _modules_by_owner(observation, components)
    inner_by_owner = _inner_edges(observation, components)
    flow_components = tuple(
        sorted(
            (
                FlowComponent(
                    label=record.title,
                    modules=tuple(sorted(modules_by_owner.get(record.title, ()))),
                    public=_public_interface(record),
                    inner_edges=tuple(inner_by_owner.get(record.title, ())),
                )
                for record in declared
            ),
            key=lambda item: item.label,
        )
    )

    edge_totals = _component_edges(observation, components)
    edge_rules: dict[tuple[str, str], set[str]] = defaultdict(set)
    for violation in observation.records("violations") or ():
        for pair in _violated_pairs(violation, components):
            if pair in edge_totals:
                edge_rules[pair].update(violation.rule_ids)
    undecided_pairs = {
        (item.source, item.target) for item in open_decisions(observation, components)
    }

    flow_edges = []
    for (source, target), count in sorted(edge_totals.items()):
        rule_ids = tuple(sorted(edge_rules.get((source, target), ())))
        state: EdgeState
        if rule_ids:
            state = "violation"
        elif (source, target) in undecided_pairs:
            state = "undecided"
        else:
            state = "conforms"
        flow_edges.append(FlowEdge(source, target, count, rule_ids, state))
    return FlowData(flow_components, tuple(flow_edges), _modules_inside(observation))
