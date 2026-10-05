# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read one standard report boundary from authenticated Core evidence."""

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    ComponentMembership,
    DependencyDecisionGap,
    Entity,
    Relationship,
    ReportFinding,
)
from archkeel.ir.codec import decode_json, value_bytes
from archkeel.ir.decisions import open_decisions
from archkeel.ir.graph_codec import parse_comparison
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import TARGET_GRAPH_RECORD_KINDS, UML_TARGET_KIND, Observation, stable_id
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_records import recorded_target_graph


def architecture_report(model: Observation) -> ArchitectureReport:
    target = next(
        (
            item
            for item in model.records("declarations") or ()
            if item.kind in TARGET_GRAPH_RECORD_KINDS
            and item.id
            == stable_id(
                "UML-TARGET" if item.kind == UML_TARGET_KIND else "ARCHITECTURE-TARGET",
                model.contract.path,
            )
        ),
        None,
    )
    declared = recorded_target_graph(model, target) if target is not None else None
    try:
        observed = observed_graph(model)
    except ValueError as error:
        report = ArchitectureReport(
            None,
            declared,
            unavailable=str(error),
            findings=_findings(model, None, declared),
            schema_version="1.2.0"
            if declared is not None and declared.schema_version == "1.2.0"
            else "1.0.0",
        )
        report.validate()
        return report
    receipt = next(
        (
            item
            for item in model.records("scope_observations") or ()
            if target is not None
            and item.kind == "rule_evaluation"
            and item.id == stable_id("UML-EVALUATION", target.id)
            and item.rule_ids == (target.id,)
            and item.data.get("comparison") is not None
        ),
        None,
    )
    comparison = (
        parse_comparison(decode_json(value_bytes(receipt.data.get("comparison"))))
        if receipt is not None
        else None
    )
    report = ArchitectureReport(
        observed,
        declared,
        comparison,
        schema_version="1.2.0"
        if declared is not None and declared.schema_version == "1.2.0"
        else "1.0.0",
        findings=_findings(model, observed, declared),
        memberships=_memberships(model, observed, declared),
        decision_gaps=_decision_gaps(model, observed, declared),
    )
    report.validate()
    return report


def _decision_gaps(
    model: Observation, observed: ArchitectureGraph, target: ArchitectureGraph | None
) -> tuple[DependencyDecisionGap, ...]:
    if target is None:
        return ()
    owners = component_owners(model)
    labels = {
        item.label: item.component_id for item in target.component_intents if item.parent_id is None
    }
    entities = {item.id: item for item in observed.entities}
    sites: dict[tuple[str | None, str | None], list[str]] = {}
    for relationship in observed.relationships:
        if relationship.kind != "imports" or relationship.target_id is None:
            continue
        pair = (
            owner_of(entities[relationship.source_id].qualified_name, owners),
            owner_of(entities[relationship.target_id].qualified_name, owners),
        )
        pair_sites: list[str] = sites.setdefault(pair, [])
        pair_sites.append(relationship.id)
    return tuple(
        DependencyDecisionGap(
            labels[item.source],
            labels[item.target],
            tuple(sites.get((item.source, item.target), ())),
        )
        for item in open_decisions(model)
        if item.source in labels and item.target in labels
    )


def _memberships(
    model: Observation, observed: ArchitectureGraph, target: ArchitectureGraph | None
) -> tuple[ComponentMembership, ...]:
    if target is None:
        return ()
    intents = {item.component_id: item for item in target.component_intents}
    entities = {item.id: item for item in target.entities}
    keys: dict[str, str] = {}

    def scope_key(identity: str) -> str:
        if identity not in keys:
            intent = intents[identity]
            label = intent.label or entities[identity].qualified_name
            keys[identity] = f"{scope_key(intent.parent_id)}:{label}" if intent.parent_id else label
        return keys[identity]

    components = {scope_key(identity): identity for identity in intents}
    modules = {
        item.qualified_name: item.id
        for item in observed.entities
        if item.kind == "module" and item.presence == "defined"
    }
    assigned: dict[str, set[str]] = {identity: set() for identity in intents}
    owners = component_owners(model)
    for name, identity in modules.items():
        owner = owner_of(name, owners)
        if owner is not None and owner in components:
            owned: set[str] = assigned[components[owner]]
            owned.add(identity)
    for level in inside_levels(model):
        for component in level.components:
            component_id = components.get(f"{level.parent}:{component.label}")
            if component_id is not None:
                inner_modules: set[str] = assigned[component_id]
                inner_modules.update(modules[name] for name in component.modules if name in modules)
    return tuple(
        ComponentMembership(identity, tuple(sorted(module_ids)))
        for identity, module_ids in sorted(assigned.items())
    )


def _findings(
    model: Observation, observed: ArchitectureGraph | None, target: ArchitectureGraph | None
) -> tuple[ReportFinding, ...]:
    subjects: dict[str, set[str]] = {}
    for graph in (observed, target):
        if graph is None:
            continue
        graph_items: tuple[Entity | Relationship, ...] = (*graph.entities, *graph.relationships)
        for graph_item in graph_items:
            references = (graph_item.id, *graph_item.record_ids)
            if isinstance(graph_item, Entity):
                references = (*references, graph_item.qualified_name)
                if graph_item.file_path is not None:
                    references = (*references, graph_item.file_path)
            for record_id in references:
                identities: set[str] = subjects.setdefault(record_id, set())
                identities.add(graph_item.id)
    findings = []
    for section, status in (("violations", "FAIL"), ("unknowns", "UNKNOWN")):
        for item in model.records(section) or ():
            findings.append(
                ReportFinding(
                    item.id,
                    item.kind,
                    item.title,
                    "FAIL" if status == "FAIL" else "UNKNOWN",
                    item.rule_ids,
                    item.subjects,
                    tuple(
                        sorted(
                            {
                                identity
                                for subject in (*item.subjects, *item.fact_ids)
                                for identity in subjects.get(subject, ())
                            }
                        )
                    ),
                    item.evidence_ids,
                    item.provenance,
                )
            )
    return tuple(findings)
