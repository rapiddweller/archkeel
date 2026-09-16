# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive the component flow view from one observation alone (AD-10)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from archkeel.ir.decisions import open_decisions
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.model import Observation, Record

EdgeState = Literal["conforms", "violation", "undecided"]


@dataclass(frozen=True, slots=True)
class FlowInnerEdge:
    """One import between two modules of the same component: observed, never decided."""

    source: str
    target: str
    import_sites: int


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


def _inner_edges(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[str, list[FlowInnerEdge]]:
    """Group the module edges that stay inside one component (AD-24), by that component."""
    grouped: dict[str, list[FlowInnerEdge]] = defaultdict(list)
    for edge in observation.records("dependency_edges") or ():
        if edge.data.get("level") != "module":
            continue
        source, target, count = (edge.data.get(key) for key in ("source", "target", "count"))
        if not isinstance(source, str) or not isinstance(target, str) or not isinstance(count, int):
            continue
        owner = owner_of(source, components)
        if owner is None or owner != owner_of(target, components):
            continue
        grouped[owner].append(FlowInnerEdge(source, target, count))
    return {
        owner: sorted(edges, key=lambda item: (item.source, item.target))
        for owner, edges in grouped.items()
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
    return FlowData(flow_components, tuple(flow_edges))
