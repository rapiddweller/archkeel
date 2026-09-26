# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive the component flow view from one observation alone (AD-10)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Literal

from archkeel.ir.decisions import open_decisions
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.levels import inside_levels
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
class FlowInside:
    """A component's declared inside, drawn as a level of its own (AD-34).

    It keeps the shape `level()` already consumes, cards and edges, because layout, ranking,
    routing and the inspector all read that shape and a level inventing its own would rewrite
    them (AD-24a). `unassigned` names the modules no sub-component owns.
    """

    components: tuple[FlowComponent, ...]
    edges: tuple[FlowEdge, ...]
    unassigned: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FlowComponent:
    label: str
    modules: tuple[str, ...]
    public: tuple[str, ...] | None
    inner_edges: tuple[FlowInnerEdge, ...] = ()
    inside: FlowInside | None = None


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
    unassigned_modules: tuple[str, ...] = ()
    unassigned_edges: tuple[FlowInnerEdge, ...] = ()


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


def _unassigned_module_edges(
    observation: Observation,
    unassigned: set[str],
) -> tuple[FlowInnerEdge, ...]:
    """Keep observed imports between unassigned modules available for physical navigation."""
    edges: list[FlowInnerEdge] = []
    for edge in observation.records("dependency_edges") or ():
        if edge.data.get("level") != "module":
            continue
        source = text_value(edge.data.get("source"))
        target = text_value(edge.data.get("target"))
        count = edge.data.get("count")
        if source in unassigned and target in unassigned and isinstance(count, int):
            # This inventory has no declared component boundary, so it carries no verdict.
            edges.append(FlowInnerEdge(source, target, count))
    return tuple(sorted(edges, key=lambda item: (item.source, item.target)))


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
        state: EdgeState = "violation" if rule_ids else "observed"
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
    modules = {
        name
        for record in observation.records("modules") or ()
        if (name := text_value(record.data.get("qualified_name")))
    }
    module_of = {
        card: module for module, items in symbols.items() for card in (s.name for s in items)
    }
    edges = _symbol_edges(observation, owner_card, module_of)
    exports, imports = _crossing_names(observation)
    return {
        module: FlowModule(
            symbols=tuple(symbols.get(module, ())),
            edges=tuple(edges.get(module, ())),
            exports=tuple(sorted(exports.get(module, ()))),
            imports=tuple(sorted(imports.get(module, ()))),
        )
        for module in sorted(modules | set(symbols))
    }


def _violated_pairs(
    violation: Record,
    components: tuple[tuple[str, tuple[str, ...]], ...],
    imports_by_id: dict[str, Record] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return the component pair(s) one violation implicates, or none for a single-subject rule."""
    if violation.kind == "no_component_cycles":
        # Members are already component labels; the cycle indicts every ordered pair among them.
        members = violation.subjects
        return tuple(
            (source, target) for source in members for target in members if source != target
        )
    if violation.kind == "module_cycle" and imports_by_id is not None:
        pairs = set()
        for fact_id in violation.fact_ids:
            item = imports_by_id.get(fact_id)
            if item is None:
                continue
            source_module = text_value(item.data.get("source_module"))
            target_module = text_value(item.data.get("target_module"))
            if source_module is None or target_module is None:
                continue
            source_component = owner_of(source_module, components)
            target_component = owner_of(target_module, components)
            if (
                source_component is not None
                and target_component is not None
                and source_component != target_component
            ):
                pairs.add((source_component, target_component))
        return tuple(sorted(pairs))
    source = violation.data.get("source_component")
    target = violation.data.get("target_component")
    if not isinstance(source, str) or not isinstance(target, str):
        raw_source_module = violation.data.get("source_module")
        raw_target_module = violation.data.get("target_module")
        if not isinstance(raw_source_module, str) or not isinstance(raw_target_module, str):
            return ()
        source = owner_of(raw_source_module, components)
        target = owner_of(raw_target_module, components)
    if source is None or target is None or source == target:
        return ()
    return ((source, target),)


def _inside_views(observation: Observation) -> dict[str, FlowInside]:
    """Draw each declared inside as its own level, by the parent component that holds it.

    A crossing is green only when the evaluator recorded every displayed import site as checked.
    The view never infers a verdict from a declaration alone (AD-32, AD-34).
    """
    views: dict[str, FlowInside] = {}
    nested_owners: set[tuple[str, str]] = set()
    imports_by_id = {item.id: item for item in observation.records("imports") or ()}
    for level in inside_levels(observation):
        inside_rule_ids = {
            record.id
            for record in observation.records("declarations") or ()
            if record.data.get("parent_id") == level.parent
        }
        components = tuple((item.label, item.packages) for item in level.components)
        checked_sites: set[str] = set()
        for record in observation.records("scope_observations") or ():
            if (
                record.kind == "inside_rule_evaluation"
                and record.data.get("parent_id") == level.parent
                and set(record.rule_ids) & inside_rule_ids
            ):
                checked_sites.update(record.fact_ids)
        sites_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        for record in observation.records("imports") or ():
            source = text_value(record.data.get("source_module"))
            target = text_value(record.data.get("target_module"))
            owner_source = owner_of(source, components) if source else None
            owner_target = owner_of(target, components) if target else None
            if (
                owner_source is not None
                and owner_target is not None
                and owner_source != owner_target
            ):
                sites_by_pair[(owner_source, owner_target)].add(record.id)
        inner_by_owner = _inner_edges(observation, components)
        pair_rules: dict[tuple[str, str], set[str]] = defaultdict(set)
        for violation in observation.records("violations") or ():
            scoped_rule_ids = set(violation.rule_ids) & inside_rule_ids
            if not scoped_rule_ids:
                continue
            for pair in _violated_pairs(violation, components, imports_by_id):
                pair_rules[pair].update(scoped_rule_ids)
        has_relevant_unknown = any(
            record.data.get("parent_id") == level.parent
            or bool(set(record.rule_ids) & inside_rule_ids)
            for record in observation.records("unknowns") or ()
        )
        cards = tuple(
            FlowComponent(
                label=item.label,
                modules=item.modules,
                public=item.public,
                inner_edges=tuple(inner_by_owner.get(item.label, ())),
            )
            for item in level.components
        )
        nested_owners.update(
            (level.parent, item.label) for item in level.components if item.has_inside
        )
        edges = []
        for edge in level.edges:
            edge_rule_ids = tuple(sorted(pair_rules.get((edge.source, edge.target), ())))
            site_ids = sites_by_pair.get((edge.source, edge.target), set())
            state: EdgeState = (
                "violation"
                if edge_rule_ids
                else "undecided"
                if has_relevant_unknown
                else "conforms"
                if site_ids and site_ids.issubset(checked_sites)
                else "observed"
            )
            edges.append(
                FlowEdge(edge.source, edge.target, edge.import_sites, edge_rule_ids, state)
            )
        views[level.parent] = FlowInside(cards, tuple(edges), level.unassigned)

    def attach(parent: str, active: frozenset[str] = frozenset()) -> FlowInside | None:
        if parent in active:
            return None
        view = views.get(parent)
        if view is None:
            return None
        path = active | {parent}
        components = tuple(
            replace(
                card,
                inside=(
                    attach(f"{parent}:{card.label}", path)
                    if (parent, card.label) in nested_owners
                    else None
                ),
            )
            for card in view.components
        )
        return replace(view, components=components)

    return {parent: nested for parent in views if (nested := attach(parent)) is not None}


def build_flow(observation: Observation) -> FlowData:
    """Return the component flow view derived from one observation alone (AD-10)."""
    declared = [
        record
        for record in observation.records("declarations") or ()
        if record.kind == "component_responsibility"
    ]
    components = component_owners(observation)
    root_rule_ids = {
        record.id
        for record in observation.records("declarations") or ()
        if record.data.get("parent_id") is None
    }
    all_modules = {
        name
        for record in observation.records("modules") or ()
        if (name := text_value(record.data.get("qualified_name")))
    }
    modules_by_owner = _modules_by_owner(observation, components)
    assigned = {name for name in all_modules if owner_of(name, components) is not None}
    unassigned = all_modules - assigned
    inner_by_owner = _inner_edges(observation, components)
    inside_by_owner = _inside_views(observation)
    flow_components = tuple(
        sorted(
            (
                FlowComponent(
                    label=record.title,
                    modules=tuple(sorted(modules_by_owner.get(record.title, ()))),
                    public=_public_interface(record),
                    inner_edges=tuple(inner_by_owner.get(record.title, ())),
                    inside=(
                        inside_by_owner.get(record.title)
                        if isinstance(record.data.get("inside"), str)
                        else None
                    ),
                )
                for record in declared
            ),
            key=lambda item: item.label,
        )
    )

    edge_totals = _component_edges(observation, components)
    imports_by_id = {item.id: item for item in observation.records("imports") or ()}
    edge_rules: dict[tuple[str, str], set[str]] = defaultdict(set)
    for violation in observation.records("violations") or ():
        scoped_rule_ids = set(violation.rule_ids) & root_rule_ids
        if not scoped_rule_ids:
            continue
        for pair in _violated_pairs(violation, components, imports_by_id):
            if pair in edge_totals:
                edge_rules[pair].update(scoped_rule_ids)
    undecided_pairs = {
        (item.source, item.target) for item in open_decisions(observation, components)
    }

    flow_edges = []
    for (source, target), count in sorted(edge_totals.items()):
        edge_rule_ids = tuple(sorted(edge_rules.get((source, target), ())))
        state: EdgeState
        if edge_rule_ids:
            state = "violation"
        elif (source, target) in undecided_pairs:
            state = "undecided"
        else:
            state = "conforms"
        flow_edges.append(FlowEdge(source, target, count, edge_rule_ids, state))
    return FlowData(
        flow_components,
        tuple(flow_edges),
        _modules_inside(observation),
        tuple(sorted(unassigned)),
        _unassigned_module_edges(observation, unassigned),
    )
