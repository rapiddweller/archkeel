# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read one standard report boundary from authenticated Core evidence."""

import json
from collections.abc import Iterable
from dataclasses import asdict

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    AssessmentStatus,
    ComponentMembership,
    DependencyDecisionGap,
    Entity,
    GraphAssessment,
    GraphComparison,
    GraphSchemaVersion,
    Relationship,
    ReportFinding,
    ReportSchemaVersion,
)
from archkeel.ir.architecture_graph import AssessmentAspect as _AssessmentAspect
from archkeel.ir.architecture_graph import CompletenessMode as _CompletenessMode
from archkeel.ir.architecture_graph import EntityKind as _EntityKind
from archkeel.ir.architecture_graph import PresenceKind as _PresenceKind
from archkeel.ir.architecture_graph import RelationshipKind as _RelationshipKind
from archkeel.ir.codec import decode_json, value_bytes
from archkeel.ir.coverage import observation_complete
from archkeel.ir.decisions import open_decisions
from archkeel.ir.graph_codec import parse_comparison
from archkeel.ir.interfaces import component_owners
from archkeel.ir.model import (
    TARGET_GRAPH_RECORD_KINDS,
    UML_TARGET_KIND,
    Observation,
    Record,
    stable_id,
)
from archkeel.ir.ownership import containing, owner_of
from archkeel.ir.source_graph import observed_graph, validated_member_inventory_proof
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
            schema_version=(
                ReportSchemaVersion.V1_3_0
                if declared is not None and declared.schema_version == GraphSchemaVersion.V1_3_0
                else ReportSchemaVersion.V1_2_0
                if declared is not None and declared.schema_version == GraphSchemaVersion.V1_2_0
                else ReportSchemaVersion.V1_0_0
            ),
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
    if (
        receipt is not None
        and comparison is not None
        and not _inventory_comparison_is_bound(model, target, declared, receipt, comparison)
    ):
        comparison = None
    report = ArchitectureReport(
        observed,
        declared,
        comparison,
        schema_version=(
            ReportSchemaVersion.V1_3_0
            if declared is not None and declared.schema_version == GraphSchemaVersion.V1_3_0
            else ReportSchemaVersion.V1_2_0
            if declared is not None and declared.schema_version == GraphSchemaVersion.V1_2_0
            else ReportSchemaVersion.V1_0_0
        ),
        findings=_findings(model, observed, declared),
        memberships=_memberships(observed, declared),
        decision_gaps=_decision_gaps(model, observed, declared),
    )
    report.validate()
    return report


def _inventory_comparison_is_bound(
    model: Observation,
    target: Record | None,
    declared: ArchitectureGraph | None,
    receipt: Record,
    comparison: GraphComparison,
) -> bool:
    closed = (
        tuple(
            scope
            for scope in declared.target_scopes
            if scope.mode == _CompletenessMode.CLOSED
            and set(scope.entity_kinds)
            & {_EntityKind.ATTRIBUTE, _EntityKind.METHOD, _EntityKind.ENUM_LITERAL}
        )
        if declared is not None
        else ()
    )
    inventory_pass = not observation_complete(model.coverage) and any(
        a.aspect == _AssessmentAspect.COMPLETENESS
        and a.status == AssessmentStatus.PASS
        and a.id
        == stable_id(
            "UML-ASSESSMENT",
            scope.scope_id,
            "completeness",
            "matched",
            *scope.entity_kinds,
            *scope.relationship_kinds,
            *a.observed_ids,
        )
        for a in comparison.assessments
        for scope in closed
    )
    if (
        not inventory_pass
        and receipt.data.get("member_inventory_binding") is None
        and receipt.data.get("member_inventory_target") is None
    ):
        return True
    proof = validated_member_inventory_proof(model)
    return (
        proof is not None
        and receipt.data.get("member_inventory_binding") == proof.data.get("binding")
        and target is not None
        and receipt.data.get("member_inventory_target")
        == stable_id("MEMBER-INVENTORY-TARGET", json.dumps(asdict(target), sort_keys=True))
    )


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
        if relationship.kind != _RelationshipKind.IMPORTS or relationship.target_id is None:
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
    observed: ArchitectureGraph, target: ArchitectureGraph | None
) -> tuple[ComponentMembership, ...]:
    if target is None:
        return ()
    intents = target.component_intents
    modules = {
        item.qualified_name: item.id
        for item in observed.entities
        if item.kind == _EntityKind.MODULE and item.presence == _PresenceKind.DEFINED
    }
    assigned: dict[str, set[str]] = {item.component_id: set() for item in intents}
    for name, identity in modules.items():
        for component_id in containing(intents, name):
            assigned[component_id].add(identity)
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
    for section, status in (
        ("violations", AssessmentStatus.FAIL),
        ("unknowns", AssessmentStatus.UNKNOWN),
    ):
        for item in model.records(section) or ():
            findings.append(
                ReportFinding(
                    item.id,
                    item.kind,
                    item.title,
                    AssessmentStatus.FAIL
                    if status == AssessmentStatus.FAIL
                    else AssessmentStatus.UNKNOWN,
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


def _by_subject(subject_ids: Iterable[Iterable[str]]) -> dict[str, list[int]]:
    """Return, for each subject id, the position of each item that names it, in order."""
    positions: dict[str, list[int]] = {}
    for position, subjects in enumerate(subject_ids):
        for subject in set(subjects):
            named: list[int] = positions.setdefault(subject, [])
            named.append(position)
    return positions


class CellFindings:
    """Index a report once; each cell then costs its own references, not the whole report."""

    def __init__(self, report: ArchitectureReport) -> None:
        self._findings = report.findings
        self._assessments = report.comparison.assessments if report.comparison else ()
        self._finding_at = _by_subject(item.graph_subject_ids for item in self._findings)
        self._assessment_at = _by_subject(item.observed_ids for item in self._assessments)

    def of(
        self, references: set[str]
    ) -> tuple[tuple[ReportFinding, ...], tuple[GraphAssessment, ...]]:
        """Return the findings and graph assessments that name a reference, in report order."""
        chosen = sorted({at for name in references for at in self._finding_at.get(name, ())})
        named = sorted({at for name in references for at in self._assessment_at.get(name, ())})
        return (
            tuple(self._findings[at] for at in chosen),
            tuple(self._assessments[at] for at in named),
        )
