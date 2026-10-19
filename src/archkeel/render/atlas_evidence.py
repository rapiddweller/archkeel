# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project rule, finding and permission evidence from authenticated Core values."""

from collections import defaultdict

from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport, Entity
from archkeel.ir.architecture_graph import EntityKind as _EntityKind
from archkeel.ir.architecture_graph import OriginKind as _OriginKind
from archkeel.ir.architecture_graph import RuleAssessmentStatus as _RuleAssessmentStatus
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.codec import decode_json, value_bytes
from archkeel.ir.decisions import rule_assessment_applies_to_component, rule_uncertainty_evidence
from archkeel.ir.model import (
    Evidence,
    EvidenceClass,
    Observation,
    RecordData,
    RunResult,
    module_in_ownership,
    text_value,
)


def _finding_payload(
    model: Observation,
    projection: ArchitectureProjection,
    references: dict[str, int],
) -> tuple[list[dict[str, object]], dict[str | None, set[str]]]:
    violations = model.records("violations") or ()
    evidence = {item.id: item for item in model.evidence}
    entries: list[dict[str, object]] = []
    for item in violations:
        locations = sorted(
            [
                (evidence[identity].file, evidence[identity].line)
                for identity in item.evidence_ids
                if identity in evidence and evidence[identity].file is not None
            ],
            key=lambda location: (location[0] or "", location[1] or -1),
        )
        path, line = locations[0] if locations else (None, None)
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
