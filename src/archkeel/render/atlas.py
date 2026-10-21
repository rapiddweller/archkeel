# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small presentation payloads from authenticated Core values."""

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport, Coverage, Entity
from archkeel.ir.architecture_graph import AssessmentStatus as _AssessmentStatus
from archkeel.ir.architecture_graph import CoverageStatus as _CoverageStatus
from archkeel.ir.architecture_graph import EntityKind as _EntityKind
from archkeel.ir.architecture_graph import OriginKind as _OriginKind
from archkeel.ir.architecture_graph import RelationshipKind as _RelationshipKind
from archkeel.ir.architecture_graph import RuleAssessmentStatus as _RuleAssessmentStatus
from archkeel.ir.architecture_projection import ArchitectureProjection, PermissionStatus
from archkeel.ir.codec import decode_json, finding_payload, value_bytes
from archkeel.ir.decisions import rule_assessment_applies_to_component, rule_uncertainty_evidence
from archkeel.ir.findings import evidence_locations
from archkeel.ir.model import (
    Evidence,
    EvidenceClass,
    Observation,
    RawJson,
    RecordData,
    RunResult,
    module_in_ownership,
    text_value,
)
from archkeel.ir.module_explore import ModuleExploreLevel, ModuleStatistic, module_exploration

from .atlas_deviations import AtlasDeviation, level_deviations


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
            if any(level.cells[index].status == _AssessmentStatus.FAIL for index in indices)
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
    references: dict[str, int],
) -> list[dict[str, object]]:
    components = []
    indices = {item.id: index for index, item in enumerate(projection.components)}
    for component in projection.components:
        item = asdict(component)
        for field in (
            "modules",
            "role",
            "permissions",
            "finding_ids",
            "namespace",
            "selector_prefix",
            "packages",
            "exact_modules",
        ):
            del item[field]
        del item["reason"]
        item["reason_ref"] = references.setdefault(component.reason, len(references))
        item["provenance"] = [
            references.setdefault(identity, len(references)) for identity in component.provenance
        ]
        item["public"] = (
            [references.setdefault(selector, len(references)) for selector in component.public]
            if component.public is not None
            else None
        )
        item["used_by"] = [
            [indices[entry.component_id], entry.import_sites] for entry in component.used_by
        ]
        item["requires"] = [
            {
                **{field: value for field, value in asdict(entry).items() if field != "rationale"},
                "rationale_ref": references.setdefault(entry.rationale, len(references)),
                "target_id": indices[entry.target_id],
            }
            for entry in component.requires
        ]
        members = next(
            (
                entry.module_ids
                for entry in report.memberships
                if entry.component_id == component.id
            ),
            (),
        )
        statistics = [entry for entry in modules if entry.id in members]
        item |= {
            "observed_modules": len(statistics),
            "observed_symbols": sum(entry.symbols or 0 for entry in statistics)
            if all(entry.symbols is not None for entry in statistics)
            else None,
            "symbols_complete": bool(statistics)
            and all(
                entry.symbols is not None
                and entry.symbol_coverage
                and all(
                    coverage.status == _CoverageStatus.COMPLETE
                    for coverage in entry.symbol_coverage
                )
                for entry in statistics
            ),
        }
        components.append(item)
    return components


def _declared_modules(report: ArchitectureReport) -> list[dict[str, object]]:
    if report.target is None:
        return []
    entities = {item.id: item for item in report.target.entities}
    children = Counter(item.parent_id for item in report.target.entities)
    module_ids = {item.id for item in report.target.entities if item.kind == _EntityKind.MODULE}
    modules: list[dict[str, object]] = []
    for entity in report.target.entities:
        if entity.kind != _EntityKind.MODULE:
            continue
        parent = entities.get(entity.parent_id or "")
        while parent is not None and parent.kind != _EntityKind.COMPONENT:
            parent = entities.get(parent.parent_id or "")
        if parent is not None:
            modules.append(
                dict(
                    id=entity.id,
                    name=entity.qualified_name,
                    path=entity.file_path,
                    component_id=parent.id,
                    declarations=children[entity.id],
                    responsibilities=entity.responsibilities,
                    provenance=entity.provenance,
                    relationships=[
                        asdict(item)
                        for item in report.target.relationships
                        if item.source_id == entity.id and item.target_id in module_ids
                    ],
                )
            )
    return modules


def _module_correspondences(report: ArchitectureReport) -> list[dict[str, object]]:
    if report.observed is None or report.target is None or report.comparison is None:
        return []
    target_modules = {item.id for item in report.target.entities if item.kind == _EntityKind.MODULE}
    observed_modules = {
        item.id for item in report.observed.entities if item.kind == _EntityKind.MODULE
    }
    return [
        {"target_id": item.target_id, "observed_ids": list(item.observed_ids)}
        for item in report.comparison.correspondences
        if item.target_id in target_modules
        and any(identity in observed_modules for identity in item.observed_ids)
    ]


def _finding_payload(
    model: Observation,
    projection: ArchitectureProjection,
    references: dict[str, int],
) -> tuple[list[dict[str, object]], dict[str | None, set[str]]]:
    violations = model.records("violations") or ()
    evidence = {item.id: item for item in model.evidence}
    entries: list[dict[str, object]] = []
    for item in violations:
        locations = evidence_locations(evidence, item.evidence_ids)
        path, line = (locations[0].path, locations[0].line) if locations else (None, None)
        entry: dict[str, object] = {
            "id": item.id,
            "rule_ids": item.rule_ids,
            "kind": item.kind,
            "title": item.title,
            "path": path,
            "line": line,
            "remedy_ref": references.setdefault(projection.violation_remedy, len(references)),
        }
        nested_annotation = item.data.get("nested_annotation")
        if isinstance(nested_annotation, str) and nested_annotation != item.data.get("annotation"):
            entry["nested_annotation"] = nested_annotation
        entries.append(entry)

    violation_ids = {item.id for item in violations}
    selected_by_component = {
        component.id: violation_ids & set(component.finding_ids)
        for component in projection.components
    }
    children: dict[str, set[str]] = defaultdict(set)
    for component in projection.components:
        if component.parent_id is not None:
            children[component.parent_id] |= {component.id}

    def descendants(identity: str) -> set[str]:
        result = {identity}
        pending = [identity]
        while pending:
            child = pending.pop()
            for nested in children[child] - result:
                result |= {nested}
                pending.append(nested)
        return result

    level_findings: dict[str | None, set[str]] = {}
    for component in projection.components:
        level_findings[component.id] = {
            identity
            for nested in descendants(component.id)
            for identity in selected_by_component.get(nested, set())
        }
    level_findings[None] = {item.id for item in violations}
    return entries, level_findings


def _system_balance(
    balances: dict[str | None, dict[str, int | None]],
) -> dict[str, int | None]:
    fields = ("declared", "used", "allowed_unused", "undeclared")
    return {
        field: None
        if any(balance[field] is None for balance in balances.values())
        else sum(balance[field] or 0 for balance in balances.values())
        for field in fields
    }


def _level_balance(
    level: ModuleExploreLevel,
    report: ArchitectureReport,
    projection: ArchitectureProjection,
) -> tuple[dict[str, int | None], tuple[AtlasDeviation, ...]]:
    balance = next((item for item in projection.levels if item.parent_id == level.parent_id), None)
    if balance is None:
        if not projection.levels:
            return {
                "declared": None,
                "used": None,
                "allowed_unused": None,
                "undeclared": None,
            }, ()
        return {"declared": 0, "used": 0, "allowed_unused": 0, "undeclared": 0}, ()
    counts: dict[str, int | None] = {
        "declared": balance.declared,
        "used": balance.used,
        "allowed_unused": balance.unused,
        "undeclared": balance.undeclared,
    }
    if balance.unused is None or balance.undeclared is None:
        return counts, ()
    if report.target is None:
        return counts, ()
    component_ids = set(level.component_ids)
    declared = {
        (edge.source_id, edge.target_id)
        for edge in report.target.relationships
        if edge.kind == _RelationshipKind.REQUIRES
        and edge.source_id in component_ids
        and edge.target_id is not None
    }
    declared |= {
        (component.id, permission.target_id)
        for component in projection.components
        if component.id in component_ids
        for permission in component.permissions
        if permission.status is PermissionStatus.ALLOWED
    }
    owners = {item.id: item.component_id for item in level.modules}
    used: set[tuple[str, str]] = set()
    for cell in level.cells:
        source_owner = owners.get(cell.source_id)
        target_owner = owners.get(cell.target_id)
        if source_owner is not None and target_owner is not None and source_owner != target_owner:
            used |= {(source_owner, target_owner)}
    return counts, level_deviations(level.parent_id, declared, used)


def _cell_payload(
    root: ModuleExploreLevel,
    references: dict[str, int],
) -> tuple[list[list[object]], dict[tuple[str, str], int], dict[str, int]]:
    module_indices = {module.id: index for index, module in enumerate(root.modules)}
    cells: list[list[object]] = []
    for cell in root.cells:
        cells.append(
            [
                module_indices[cell.source_id],
                module_indices[cell.target_id],
                cell.import_sites,
                cell.status,
                [
                    references.setdefault(identity, len(references))
                    for identity in cell.evidence_ids
                ],
                [references.setdefault(identity, len(references)) for identity in cell.finding_ids],
                [references.setdefault(reason, len(references)) for reason in cell.reasons],
            ]
        )
    indices = {(item.source_id, item.target_id): index for index, item in enumerate(root.cells)}
    return cells, indices, module_indices


def _atlas_levels(
    exploration: tuple[ModuleExploreLevel, ...],
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    model: Observation,
    references: dict[str, int],
    cell_indices: dict[tuple[str, str], int],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str | None, dict[str, int | None]],
    list[AtlasDeviation],
    list[dict[str, object]],
    dict[tuple[str, str | None, tuple[str, ...], str, str], int],
]:
    questions: list[dict[str, object]] = []
    assignments: dict[tuple[str, str | None, tuple[str, ...], str, str], int] = {}
    levels = [
        _level_payload(level, references, cell_indices, questions, assignments)
        for level in exploration
    ]
    findings, level_findings = _finding_payload(model, projection, references)
    finding_indices = {item["id"]: index for index, item in enumerate(findings)}
    balances: dict[str | None, dict[str, int | None]] = {}
    deviations: list[AtlasDeviation] = []
    level_deviations: dict[str | None, list[str]] = defaultdict(list)
    for level, payload in zip(exploration, levels, strict=True):
        payload["finding_ids"] = sorted(
            finding_indices[identity]
            for identity in level_findings.get(level.parent_id, set())
            if identity in finding_indices
        )
        balance, items = _level_balance(level, report, projection)
        payload["balance"] = balance
        balances[level.parent_id] = balance
        for item in items:
            level_deviations[level.parent_id] += [item.id]
            deviations.append(item)
        payload["deviation_ids"] = level_deviations[level.parent_id]
    return levels, findings, balances, deviations, questions, assignments


def _modules_payload(
    root: ModuleExploreLevel,
    references: dict[str, int],
) -> tuple[list[dict[str, object]], list[list[dict[str, object]]]]:
    coverages: dict[tuple[Coverage, ...], int] = {}
    modules = []
    for module in root.modules:
        module_data = asdict(module)
        coverage = tuple(replace(entry, scope_id="") for entry in module.symbol_coverage)
        module_data["symbol_coverage"] = coverages.setdefault(coverage, len(coverages))
        for field in ("component_id", "candidate_ids", "ownership_status", "ownership_reason"):
            del module_data[field]
        modules.append(_reference_fields(module_data, references))
    symbol_coverages = [[asdict(entry) for entry in coverage] for coverage in coverages]
    return modules, symbol_coverages


def _rule_assessments_payload(
    result: RunResult,
    model: Observation,
    projection: ArchitectureProjection,
    references: dict[str, int],
) -> list[dict[str, object]]:
    evidence = rule_uncertainty_evidence(model)
    scopes = {item.declaration.id: item.parent_id for item in projection.permission_rules}
    components = {item.id: item for item in projection.components}
    rows: list[dict[str, object]] = []
    for item in result.rule_assessments or ():
        scope_id = scopes.get(item.id)
        scope = components[scope_id].scope if scope_id in components else item.scope
        uncertainty = (
            evidence.get(item.id)
            if item.status == _RuleAssessmentStatus.UNKNOWN or item.undecided
            else None
        )
        records = uncertainty.evidence if uncertainty is not None else ()
        rows.append(
            {
                "id": references.setdefault(item.id, len(references)),
                "kind": references.setdefault(item.kind, len(references)),
                "status": item.status,
                "count": item.count,
                "undecided": item.undecided,
                "reason": references.setdefault(item.reason, len(references)),
                "scope": references.setdefault(scope, len(references)),
                "scope_id": scope_id,
                "components": [
                    references.setdefault(value, len(references)) for value in item.components
                ],
                "component_ids": [
                    component.id
                    for component in projection.components
                    if item.components
                    and rule_assessment_applies_to_component(
                        item, scope_id, component.parent_id, component.label
                    )
                ],
                "evaluation_proven": item.evaluation_proven,
                "uncertainty_actions": [
                    {
                        "cause": action.cause.value,
                        "architect_actionable": action.architect_actionable,
                        "next_action": references.setdefault(action.next_action, len(references)),
                    }
                    for action in uncertainty.actions
                ]
                if uncertainty is not None
                else [],
                "evidence_count": len(records),
                "evidence": [
                    {
                        "id": references.setdefault(record.id, len(references)),
                        "kind": record.kind,
                        "title": record.title,
                        "subjects": record.subjects[:3],
                        "subject_count": len(record.subjects),
                        "evidence_class": record.evidence_class.value,
                        "reason": record.data.get("reason"),
                    }
                    for record in records[:5]
                ],
            }
        )
    return rows


def _ranked_findings_payload(result: RunResult) -> list[dict[str, RawJson]] | None:
    return None if result.findings is None else [finding_payload(item) for item in result.findings]


def atlas_payload(
    model: Observation,
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    result: RunResult,
    *,
    repository: str,
    architecture_href: str,
    exploration_levels: tuple[ModuleExploreLevel, ...] | None = None,
) -> dict[str, object]:
    exploration = _leaf_levels(
        report,
        module_exploration(model, report=report)
        if exploration_levels is None
        else exploration_levels,
    )
    root = exploration[0]
    references: dict[str, int] = {}
    cells, indices, module_indices = _cell_payload(root, references)
    levels, findings, balances, deviations, questions, assignments = _atlas_levels(
        exploration, report, projection, model, references, indices
    )
    modules, symbol_coverages = _modules_payload(root, references)
    return {
        "repository": repository,
        "source": {
            "git_head": projection.source.git_head,
            "source_digest": projection.source.source_digest,
        },
        "declared_rules": result.declared_rules,
        "observation_complete": result.observation_complete,
        "rule_assessments": _rule_assessments_payload(result, model, projection, references),
        "status": projection.status,
        "reason": projection.reason,
        "components": _components_payload(report, projection, root.modules, references),
        "modules": modules,
        "symbols_complete": bool(root.modules)
        and all(
            module.symbols is not None
            and module.symbol_coverage
            and all(entry.status == _CoverageStatus.COMPLETE for entry in module.symbol_coverage)
            for module in root.modules
        ),
        "declared_modules": _declared_modules(report),
        "module_inventories": [asdict(item) for item in report.target.module_inventories]
        if report.target
        else [],
        "module_correspondences": _module_correspondences(report),
        "symbol_coverages": symbol_coverages,
        "assignments": [
            [
                module_indices[identity],
                references.setdefault(owner, len(references)) if owner is not None else None,
                [references.setdefault(candidate, len(references)) for candidate in candidates],
                status,
                references.setdefault(reason, len(references)),
            ]
            for identity, owner, candidates, status, reason in assignments
        ],
        "cells": cells,
        "cell_permission_reason_ref": references.setdefault(
            root.cells[0].permission_reason if root.cells else "", len(references)
        ),
        "levels": levels,
        "findings": findings,
        "ranked_findings": _ranked_findings_payload(result),
        "balance": _system_balance(balances),
        "deviations": [item.to_wire() for item in deviations],
        "questions": questions,
        "reference_ids": list(references),
        "unknowns": [
            {"reason": reason, "count": count}
            for reason, count in Counter(item.reason for item in projection.unknowns).most_common(5)
        ],
        "unknown_count": len(projection.unknowns),
        "detail_page": f"{PurePosixPath(architecture_href).stem}.detail.html",
        "unassigned_detail_href": "?component=unassigned",
        "architecture_href": architecture_href,
    }


def _permission_locations(
    evidence: dict[str, Evidence], ids: tuple[str, ...]
) -> list[dict[str, object]]:
    return [
        {
            "id": identity,
            "file": evidence[identity].file,
            "line": evidence[identity].line,
            "end_line": evidence[identity].end_line,
            "column": evidence[identity].column,
        }
        for identity in ids
        if identity in evidence
    ]


def _permission_navigation(
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    graph: ArchitectureGraph | None,
    identities: tuple[str, ...],
) -> dict[str, object]:
    if graph is None:
        return {"entity_ids": [], "component_ids": [], "routes": []}
    entities = {item.id: item for item in graph.entities}
    matches_by_id = {}
    for identity in identities:
        candidates = [
            item
            for item in entities.values()
            if identity in (item.id, item.qualified_name, *item.record_ids)
        ]
        if len(candidates) == 1:
            matches_by_id[candidates[0].id] = candidates[0]
    matches = list(matches_by_id.values())
    routes = []
    component_ids = set()
    for entity in matches:
        current: Entity | None = entity
        module_id = None
        component_id = None
        ancestors = []
        while current is not None and current.id not in ancestors:
            ancestors.append(current.id)
            if current.kind == _EntityKind.MODULE:
                module_id = current.id
            if current.kind == _EntityKind.COMPONENT:
                component_id = current.id
                component_ids.add(current.id)
            current = entities.get(current.parent_id or "")
        if graph and graph.origin == _OriginKind.OBSERVED and module_id:
            owners = [
                membership.component_id
                for membership in report.memberships
                if module_id in membership.module_ids
            ]
            component_ids.update(owners)
            parents = {item.parent_id for item in projection.components if item.id in owners}
            leaves = [identity for identity in owners if identity not in parents]
            if len(leaves) == 1:
                component_id = leaves[0]
        routes.append(
            {
                "entity_id": entity.id,
                "module_id": module_id,
                "component_id": component_id,
                "origin": graph.origin,
                "scope_id": entity.parent_id
                if entity.kind
                not in (_EntityKind.MODULE, _EntityKind.COMPONENT, _EntityKind.PACKAGE)
                else entity.id,
                "label": entity.qualified_name,
            }
        )
    return {
        "entity_ids": sorted(item.id for item in matches),
        "component_ids": sorted(component_ids),
        "routes": routes,
    }


def _declared_permissions(
    report: ArchitectureReport, projection: ArchitectureProjection, evidence: dict[str, Evidence]
) -> list[dict[str, object]]:
    declared: list[dict[str, object]] = []
    for permission in projection.permission_rules:
        rule = permission.declaration
        if rule.kind != "boundary_types":
            continue
        positions = rule.data.get("allowed_positions")
        if not isinstance(positions, tuple):
            continue
        for index, position in enumerate(positions):
            if not isinstance(position, RecordData):
                continue
            selector = {key: decode_json(value_bytes(value)) for key, value in position.entries}
            selector.setdefault("field_path", "")
            name = selector.get("qualified_name")
            source = rule.data.get("source")
            links = _permission_navigation(
                report, projection, report.target, (name,) if isinstance(name, str) else ()
            )
            if not links["routes"] and report.target is not None:
                modules = [
                    item
                    for item in report.target.entities
                    if item.kind == _EntityKind.MODULE and item.qualified_name == source
                ]
                if len(modules) == 1:
                    links = _permission_navigation(
                        report, projection, report.target, (modules[0].id,)
                    )
            owners = [
                item
                for item in projection.components
                if item.parent_id == permission.parent_id
                and (
                    (
                        isinstance(source, str)
                        and module_in_ownership(source, item.packages, item.exact_modules)
                    )
                    or (
                        isinstance(name, str)
                        and module_in_ownership(name, item.packages, item.exact_modules)
                    )
                )
            ]
            if len(owners) == 1:
                links["component_ids"] = [owners[0].id]
            declared.append(
                {
                    "id": f"{rule.id}:allowed-position:{index}",
                    "rule_id": rule.id,
                    "contract_scope_id": permission.parent_id,
                    "source": source,
                    **selector,
                    "rationale": rule.data.get("rationale"),
                    "decided_by": rule.data.get("decided_by"),
                    "provenance": rule.provenance,
                    "evidence_ids": rule.evidence_ids,
                    "locations": _permission_locations(evidence, rule.evidence_ids),
                    **links,
                }
            )
    return declared


def _valid_alias_body(selector: dict[str, object], name: str) -> bool:
    if name not in selector:
        return True
    binding = selector[name]
    if not isinstance(binding, dict) or set(binding) != {"origin", "shape"}:
        return False
    for key in ("origin", "shape"):
        value: str = text_value(binding[key])
        if not value.strip():
            return False
    return True


def boundary_permissions_payload(
    model: Observation, report: ArchitectureReport, projection: ArchitectureProjection
) -> dict[str, object]:
    """Resolve presentation links while canonical source identities are still available."""
    evidence = {item.id: item for item in model.evidence}
    declared = _declared_permissions(report, projection, evidence)
    applied: list[dict[str, object]] = []
    coordinates = (
        "qualified_name",
        "position",
        "field_path",
        "annotation",
        "container_depth",
        "mapping_depth",
        "literal_mapping_arm",
        "native_mapping",
        "alias_body",
        "key_alias_body",
    )

    for fact in model.records("typing_signals") or ():
        if fact.kind != "boundary_type_allowance" or fact.evidence_class != EvidenceClass.FACT:
            continue
        selector: dict[str, object] = {
            key: decode_json(value_bytes(value))
            for key, value in fact.data.entries
            if key
            in (*coordinates, "nested_annotation", "accepted_opacity", "observed_container_depth")
        }
        selector.setdefault("field_path", "")
        candidates = [
            row
            for row in declared
            if row["rule_id"] in fact.rule_ids
            and all(
                _valid_alias_body(item, name)
                for item in (row, selector)
                for name in ("alias_body", "key_alias_body")
            )
            and all(
                (key in row) == (key in selector) and row.get(key) == selector.get(key)
                for key in coordinates
            )
        ]
        declaration = candidates[0] if len(candidates) == 1 else None
        links = _permission_navigation(
            report, projection, report.observed, (*fact.subjects, *fact.fact_ids)
        )
        applied.append(
            {
                "id": fact.id,
                "title": fact.title,
                "data": selector,
                "declaration_id": declaration["id"] if declaration else None,
                "rationale": declaration["rationale"] if declaration else None,
                "decided_by": declaration["decided_by"] if declaration else None,
                "rule_ids": fact.rule_ids,
                "fact_ids": fact.fact_ids,
                "evidence_ids": fact.evidence_ids,
                "provenance": fact.provenance,
                "locations": _permission_locations(evidence, fact.evidence_ids),
                **links,
            }
        )
    return {"declared": declared, "applied": applied}
