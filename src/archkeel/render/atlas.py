# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small presentation payloads from authenticated Core values."""

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    Coverage,
    GraphComparison,
)
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.model import Observation, stable_id
from archkeel.ir.module_explore import ModuleExploreLevel, ModuleStatistic, module_exploration


def detail_name(architecture_href: str, component_id: str | None) -> str:
    stem = PurePosixPath(architecture_href).stem
    suffix = stable_id("component", component_id) if component_id is not None else "unknown"
    return f"{stem}.detail-{suffix}.html"


def _reference_fields(item: dict[str, object], references: dict[str, int]) -> dict[str, object]:
    for field in ("evidence_ids", "relationship_ids", "finding_ids", "assessment_ids"):
        values = item.get(field)
        if isinstance(values, (tuple, list)):
            item[field] = [references.setdefault(value, len(references)) for value in values]
    reason = item.get("permission_reason")
    if isinstance(reason, str):
        item["permission_reason"] = references.setdefault(reason, len(references))
    return item


def _component_edges(level: ModuleExploreLevel) -> list[dict[str, object]]:
    owners = {item.id: item.component_id for item in level.modules}
    pairs: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, cell in enumerate(level.cells):
        source, target = owners.get(cell.source_id), owners.get(cell.target_id)
        if source is not None and target is not None and source != target:
            pairs[source, target].append(index)
    return [
        {
            "source_id": source,
            "target_id": target,
            "import_sites": sum(level.cells[index].import_sites or 0 for index in indices)
            if all(level.cells[index].import_sites is not None for index in indices)
            else None,
            "status": "FAIL"
            if any(level.cells[index].status == "FAIL" for index in indices)
            else "UNKNOWN",
        }
        for (source, target), indices in sorted(pairs.items())
    ]


def _level_payload(
    level: ModuleExploreLevel,
    references: dict[str, int],
    cells: dict[tuple[str, str], int],
    questions: list[dict[str, object]],
    assignments: dict[tuple[str, str | None, tuple[str, ...], str, str], int],
) -> dict[str, object]:
    question_ids = []
    for hint in level.hint_candidates:
        question_ids.append(len(questions))
        questions.append(_reference_fields(asdict(hint), references))
    return {
        "parent_id": level.parent_id,
        "component_ids": level.component_ids,
        "modules": [
            assignments.setdefault(
                (
                    item.id,
                    item.component_id,
                    item.candidate_ids,
                    item.ownership_status,
                    item.ownership_reason,
                ),
                len(assignments),
            )
            for item in level.modules
        ],
        "cells": [cells[item.source_id, item.target_id] for item in level.cells],
        "edges": _component_edges(level),
        "import_status": level.import_status,
        "import_reason": level.import_reason,
        "questions": question_ids,
    }


def _leaf_levels(
    report: ArchitectureReport, levels: tuple[ModuleExploreLevel, ...]
) -> tuple[ModuleExploreLevel, ...]:
    if report.target is None:
        return levels
    native = {level.parent_id: level for level in levels}
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    leaves = []
    for intent in report.target.component_intents:
        if intent.component_id in native:
            continue
        parent = native.get(intent.parent_id)
        if parent is None:
            continue
        selected = memberships.get(intent.component_id, set())
        leaves.append(
            replace(
                parent,
                parent_id=intent.component_id,
                component_ids=(),
                modules=tuple(item for item in parent.modules if item.id in selected),
                cells=tuple(
                    item
                    for item in parent.cells
                    if item.source_id in selected and item.target_id in selected
                ),
                hint_candidates=(),
            )
        )
    return (*levels, *leaves)


def _components_payload(
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    modules: tuple[ModuleStatistic, ...],
    architecture_href: str,
) -> list[dict[str, object]]:
    components = []
    for component in projection.components:
        item = asdict(component)
        for field in (
            "modules",
            "permissions",
            "finding_ids",
            "namespace",
            "packages",
            "exact_modules",
            "selector_prefix",
            "scope",
        ):
            item.pop(field)
        members = next(
            (
                entry.module_ids
                for entry in report.memberships
                if entry.component_id == component.id
            ),
            (),
        )
        statistics = [entry for entry in modules if entry.id in members]
        item.update(
            detail_href=detail_name(architecture_href, component.id),
            observed_modules=len(statistics),
            observed_symbols=sum(entry.symbols or 0 for entry in statistics)
            if all(entry.symbols is not None for entry in statistics)
            else None,
            symbols_known=sum(entry.symbols is not None for entry in statistics),
            symbols_complete=bool(statistics)
            and all(
                entry.symbols is not None
                and entry.symbol_coverage
                and all(coverage.status == "complete" for coverage in entry.symbol_coverage)
                for entry in statistics
            ),
        )
        components.append(item)
    return components


def atlas_payload(
    model: Observation,
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    *,
    repository: str,
    architecture_href: str,
) -> dict[str, object]:
    exploration = _leaf_levels(report, module_exploration(model))
    root = exploration[0]
    references: dict[str, int] = {}
    module_indices = {module.id: index for index, module in enumerate(root.modules)}
    cells = []
    for cell in root.cells:
        cells.append(
            [
                module_indices[cell.source_id],
                module_indices[cell.target_id],
                cell.import_sites,
                cell.status,
                cell.permission,
                references.setdefault(cell.permission_reason, len(references)),
                [
                    references.setdefault(identity, len(references))
                    for identity in cell.evidence_ids
                ],
                [references.setdefault(identity, len(references)) for identity in cell.finding_ids],
                cell.reasons,
            ]
        )
    indices = {(item.source_id, item.target_id): index for index, item in enumerate(root.cells)}
    questions: list[dict[str, object]] = []
    assignments: dict[tuple[str, str | None, tuple[str, ...], str, str], int] = {}
    levels = [
        _level_payload(level, references, indices, questions, assignments) for level in exploration
    ]
    coverages: dict[tuple[Coverage, ...], int] = {}
    modules = []
    for module in root.modules:
        item = asdict(module)
        coverage = tuple(replace(entry, scope_id="") for entry in module.symbol_coverage)
        item["symbol_coverage"] = coverages.setdefault(coverage, len(coverages))
        for field in ("component_id", "candidate_ids", "ownership_status", "ownership_reason"):
            item.pop(field)
        modules.append(_reference_fields(item, references))
    components = _components_payload(report, projection, root.modules, architecture_href)
    return {
        "repository": repository,
        "source": asdict(projection.source),
        "contract_digest": projection.contract_digest,
        "analyzer_digest": projection.analyzer_digest,
        "coverage": asdict(model.coverage),
        "status": projection.status,
        "reason": projection.reason,
        "components": components,
        "modules": modules,
        "symbol_coverages": [[asdict(entry) for entry in coverage] for coverage in coverages],
        "assignments": [
            [
                module_indices[identity],
                owner,
                candidates,
                status,
                references.setdefault(reason, len(references)),
            ]
            for identity, owner, candidates, status, reason in assignments
        ],
        "cells": cells,
        "levels": levels,
        "questions": questions,
        "reference_ids": list(references),
        "unknowns": [
            {"reason": reason, "count": count}
            for reason, count in Counter(item.reason for item in projection.unknowns).most_common(5)
        ],
        "unknown_count": len(projection.unknowns),
        "required_relationships": [asdict(item) for item in projection.required_relationships],
        "unassigned_detail_href": detail_name(architecture_href, None),
        "architecture_href": architecture_href,
    }


def _detail_graph(graph: ArchitectureGraph, selected: set[str]) -> ArchitectureGraph:
    retained = set(selected)
    relationships = tuple(
        item
        for item in graph.relationships
        if item.source_id in selected
        or item.target_id in selected
        or any(identity in selected for identity in item.candidate_ids)
    )
    retained.update(item.source_id for item in relationships)
    retained.update(item.target_id for item in relationships if item.target_id is not None)
    retained.update(identity for item in relationships for identity in item.candidate_ids)
    parents = {item.id: item.parent_id for item in graph.entities}
    parents.update({item.component_id: item.parent_id for item in graph.component_intents})
    for identity in tuple(retained):
        parent = parents.get(identity)
        while parent:
            retained.add(parent)
            parent = parents[parent]
    entities = tuple(item for item in graph.entities if item.id in retained)
    entities = tuple(
        replace(item, parent_id=item.parent_id if item.parent_id in retained else None)
        for item in entities
    )
    evidence_ids = {identity for item in entities for identity in item.evidence_ids}
    evidence_ids.update(identity for item in relationships for identity in item.evidence_ids)
    evidence_ids.update(
        identity
        for item in entities
        for context in item.definition_contexts
        for identity in context.evidence_ids
    )
    return replace(
        graph,
        entities=entities,
        relationships=relationships,
        evidence=tuple(item for item in graph.evidence if item.id in evidence_ids),
        coverage=tuple(
            item for item in graph.coverage if item.scope_id is None or item.scope_id in retained
        ),
        component_intents=tuple(
            item for item in graph.component_intents if item.component_id in retained
        ),
        target_scopes=tuple(
            item
            for item in graph.target_scopes
            if item.scope_id is None or item.scope_id in retained
        ),
        module_inventories=tuple(
            item for item in graph.module_inventories if item.component_id in retained
        ),
    )


def detail_report(
    report: ArchitectureReport,
    component_id: str | None,
    *,
    unknown_module_ids: frozenset[str] = frozenset(),
) -> ArchitectureReport:
    """Choose recorded membership and lexical descendants, retaining incident sites."""
    members = set(
        next(
            (item.module_ids for item in report.memberships if item.component_id == component_id),
            (),
        )
    )
    if component_id is None:
        members = set(unknown_module_ids)
    selected = members | ({component_id} if component_id else set())
    for graph in (report.target, report.observed):
        if graph:
            changed = True
            while changed:
                before = len(selected)
                selected.update(item.id for item in graph.entities if item.parent_id in selected)
                changed = len(selected) != before
    observed = _detail_graph(report.observed, selected) if report.observed else None
    target = _detail_graph(report.target, selected) if report.target else None
    subjects = {item.id for graph in (observed, target) if graph for item in graph.entities}
    subjects.update(
        item.id for graph in (observed, target) if graph for item in graph.relationships
    )
    evidence = {item.id for item in observed.evidence} if observed else set()
    findings = tuple(
        replace(
            item,
            graph_subject_ids=tuple(
                identity for identity in item.graph_subject_ids if identity in subjects
            ),
        )
        for item in report.findings
        if any(identity in subjects for identity in item.graph_subject_ids)
    )
    comparison = _detail_comparison(report.comparison, subjects)
    if observed and report.observed:
        proof = evidence | {identity for item in findings for identity in item.evidence_ids}
        if comparison:
            proof.update(
                identity for item in comparison.assessments for identity in item.evidence_ids
            )
        observed = replace(
            observed, evidence=tuple(item for item in report.observed.evidence if item.id in proof)
        )
    return replace(
        report,
        observed=observed,
        target=target,
        comparison=comparison,
        findings=findings,
        memberships=tuple(
            replace(
                item,
                module_ids=tuple(identity for identity in item.module_ids if identity in subjects),
            )
            for item in report.memberships
            if item.component_id in subjects
        ),
        decision_gaps=tuple(
            item
            for item in report.decision_gaps
            if item.source_id in subjects
            and item.target_id in subjects
            and all(identity in subjects for identity in item.relationship_ids)
        ),
    )


def _detail_comparison(
    comparison: GraphComparison | None, subjects: set[str]
) -> GraphComparison | None:
    if comparison:
        comparison = GraphComparison.from_assessments(
            tuple(
                item
                for item in comparison.assessments
                if item.subject_id in subjects
                and all(identity in subjects for identity in item.observed_ids)
            ),
            correspondences=tuple(
                item
                for item in comparison.correspondences
                if item.target_id in subjects
                and all(identity in subjects for identity in item.observed_ids)
            ),
        )
    return comparison
