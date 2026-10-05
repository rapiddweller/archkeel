# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project the authenticated shared report for focused architecture consumers."""

from posixpath import commonpath

from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport, AssessmentStatus
from archkeel.ir.architecture_projection import (
    ArchitectureProjection,
    ComponentProjection,
    LevelProjection,
    ModuleProjection,
    OwnershipGap,
    PermissionProjection,
    PermissionRuleKind,
    PermissionRuleProjection,
    PermissionStatus,
    RequiredRelationshipProjection,
    RequiresProjection,
    UnknownProjection,
    UsageProjection,
)
from archkeel.ir.model import (
    Diagnostic,
    DiagnosticError,
    Observation,
    RuleAssessment,
    declared_package_pair,
    module_in_ownership,
    text_value,
)


def _scope_names(target: ArchitectureGraph) -> dict[str, str]:
    intents = {item.component_id: item for item in target.component_intents}
    names: dict[str, str] = {}

    def name(identity: str) -> str:
        if identity not in names:
            intent = intents[identity]
            label = intent.label or identity
            names[identity] = f"{name(intent.parent_id)}:{label}" if intent.parent_id else label
        return names[identity]

    for identity in intents:
        name(identity)
    return names


def _scope_owners(target: ArchitectureGraph, module: str, parent_id: str | None) -> tuple[str, ...]:
    if parent_id is not None:
        parent = next(item for item in target.component_intents if item.component_id == parent_id)
        if _scope_owners(target, module, parent.parent_id) != (parent_id,):
            return ()
    return tuple(
        sorted(
            item.component_id
            for item in target.component_intents
            if item.parent_id == parent_id
            and module_in_ownership(module, item.packages, item.exact_modules)
        )
    )


def _deepest_owners(target: ArchitectureGraph, module: str) -> tuple[str, ...]:
    parent_id = None
    while True:
        matches = _scope_owners(target, module, parent_id)
        if len(matches) != 1:
            return matches or ((parent_id,) if parent_id is not None else ())
        parent_id = matches[0]


def _scope_subjects(report: ArchitectureReport, module_ids: set[str]) -> set[str]:
    if report.observed is None:
        return set()
    entities = {item.id: item for item in report.observed.entities}
    subjects = set(module_ids)
    for entity in entities.values():
        parent = entity
        while parent.parent_id is not None and parent.id not in subjects:
            parent = entities[parent.parent_id]
        if parent.id in subjects:
            subjects.add(entity.id)
    if report.comparison is not None:
        subjects.update(
            item.target_id
            for item in report.comparison.correspondences
            if set(item.observed_ids) & subjects
        )
    for graph in (report.observed, report.target):
        if graph is not None:
            subjects.update(
                edge.id
                for edge in graph.relationships
                if edge.source_id in subjects or edge.target_id in subjects
            )
    return subjects


def _permission_rules(
    model: Observation, target: ArchitectureGraph
) -> tuple[PermissionRuleProjection, ...]:
    rows = []
    scope_ids = {scope: identity for identity, scope in _scope_names(target).items()}
    for item in model.records("declarations") or ():
        if item.kind not in {"allowed_dependency", "forbidden_dependency", "complete_requires"}:
            continue
        kind: PermissionRuleKind = (
            "allowed_dependency"
            if item.kind == "allowed_dependency"
            else "forbidden_dependency"
            if item.kind == "forbidden_dependency"
            else "complete_requires"
        )
        allowed = item.data.get("allowed_sources", ())
        if not isinstance(allowed, tuple) or any(not isinstance(value, str) for value in allowed):
            raise ValueError("dependency rule selectors are malformed")
        type_checking = item.data.get("include_type_checking")
        if type_checking is not None and not isinstance(type_checking, bool):
            raise ValueError("dependency rule type-checking selector is malformed")
        rows.append(
            PermissionRuleProjection(
                item.id,
                kind,
                scope_ids.get(text_value(item.data.get("parent_id"))),
                text_value(item.data.get("source")) or None,
                text_value(item.data.get("target")) or None,
                text_value(item.data.get("target_symbol")) or None,
                tuple(value for value in allowed if isinstance(value, str)),
                type_checking,
                text_value(item.data.get("rationale")) or "",
                text_value(item.data.get("decided_by")) or None,
            )
        )
    return tuple(sorted(rows, key=lambda item: item.id))


def _permissions(
    target: ArchitectureGraph, rules: tuple[PermissionRuleProjection, ...]
) -> dict[str, tuple[PermissionProjection, ...]]:
    rows = {}
    for source in target.component_intents:
        siblings = tuple(
            item for item in target.component_intents if item.parent_id == source.parent_id
        )
        owners = tuple((item.component_id, item.packages, item.exact_modules) for item in siblings)
        level_rules = tuple(item for item in rules if item.parent_id == source.parent_id)
        complete = tuple(item.id for item in level_rules if item.kind == "complete_requires")
        permissions = []
        for sibling in siblings:
            if sibling.component_id == source.component_id:
                continue
            pair = (source.component_id, sibling.component_id)
            requires = tuple(
                edge
                for edge in target.relationships
                if edge.kind == "requires" and (edge.source_id, edge.target_id) == pair
            )
            deciding = tuple(
                rule
                for rule in level_rules
                if rule.source is not None
                and rule.target is not None
                and declared_package_pair(rule.source, rule.target, rule.target_symbol, owners)
                == pair
            )
            forbidden = tuple(
                rule.id
                for rule in deciding
                if rule.kind == "forbidden_dependency" and not rule.allowed_sources
            )
            allowed = tuple(rule.id for rule in deciding if rule.kind == "allowed_dependency")
            status: PermissionStatus
            if forbidden:
                status, identifiers, reason = (
                    "forbidden",
                    forbidden,
                    "A declared dependency rule forbids this component pair.",
                )
            elif requires or allowed:
                status, identifiers, reason = (
                    "allowed",
                    tuple(edge.id for edge in requires) + allowed,
                    "Declared permission; requires.through and permission_rules "
                    "retain narrower selectors.",
                )
            elif complete:
                status, identifiers, reason = (
                    "forbidden",
                    complete,
                    "complete_requires forbids this absent permission.",
                )
            else:
                status, identifiers, reason = (
                    "undecided",
                    (),
                    "No whole-component decision is declared; permission_rules "
                    "retain partial selectors.",
                )
            permissions.append(
                PermissionProjection(
                    sibling.component_id, status, tuple(sorted(identifiers)), reason
                )
            )
        rows[source.component_id] = tuple(sorted(permissions, key=lambda item: item.target_id))
    return rows


def architecture_projection(
    model: Observation,
    report: ArchitectureReport,
    assessments: tuple[RuleAssessment, ...],
    *,
    violation_remedy: str,
    component: str | None = None,
) -> ArchitectureProjection:
    """Project one authenticated report; filters retain global uncertainty and source identity."""
    report.validate()
    target, observed = report.target, report.observed
    unknowns = [
        UnknownProjection(item.id, item.title, item.rule_ids)
        for item in report.findings
        if item.status == "UNKNOWN"
    ]
    if target is None:
        unknowns.append(
            UnknownProjection("target.unavailable", "Authenticated Target intent is unavailable.")
        )
    if observed is None:
        unknowns.append(
            UnknownProjection(
                "source.unavailable", report.unavailable or "Observed source facts are unavailable."
            )
        )
    if target is None or observed is None:
        if component is not None:
            raise DiagnosticError(
                Diagnostic(
                    "filter_unknown",
                    f"--component {component}",
                    "Selecting a component requires authenticated Target and source facts.",
                    "Restore the missing evidence and retry.",
                )
            )
        return ArchitectureProjection(
            model.source,
            model.contract.digest,
            model.analyzer.code_digest,
            (),
            (),
            (),
            (),
            (),
            tuple(unknowns),
            "UNKNOWN",
            "Target or observed evidence is unavailable.",
            violation_remedy,
        )
    names = _scope_names(target)
    selected = None
    if component is not None:
        selected = next(
            (
                item.component_id
                for item in target.component_intents
                if item.component_id == component or names[item.component_id] == component
            ),
            None,
        )
        if selected is None:
            matches = tuple(
                item.component_id for item in target.component_intents if item.label == component
            )
            selected = matches[0] if len(matches) == 1 else None
        if selected is None:
            raise DiagnosticError(
                Diagnostic(
                    "filter_unknown",
                    f"--component {component}",
                    "The component selector is absent or ambiguous in the authenticated Target.",
                    "Use a component id or its complete scope-qualified label.",
                )
            )
    entities = {item.id: item for item in observed.entities}
    modules = tuple(
        item for item in observed.entities if item.kind == "module" and item.presence == "defined"
    )
    ownership = {item.id: _deepest_owners(target, item.qualified_name) for item in modules}
    gaps = tuple(
        OwnershipGap(
            item.qualified_name,
            item.file_path,
            ownership[item.id],
            "Several components claim this module at the same level."
            if ownership[item.id]
            else "No declared component owns this module.",
        )
        for item in sorted(modules, key=lambda item: item.qualified_name)
        if len(ownership[item.id]) != 1
    )
    unknowns.extend(UnknownProjection(f"ownership:{item.module}", item.reason) for item in gaps)
    covered_imports = {
        item.scope_id
        for item in observed.coverage
        if "imports" in item.relationship_kinds and item.status == "complete"
    }
    imports_complete = (
        model.coverage.status == "PASS"
        and model.records("imports") is not None
        and bool(modules)
        and all(item.id in covered_imports for item in modules)
    )
    if not imports_complete:
        unknowns.append(
            UnknownProjection(
                "imports.incomplete",
                "Import coverage is incomplete; usage and absence counts are unavailable.",
            )
        )
    for edge in observed.relationships:
        if edge.kind == "imports" and edge.target_id is None:
            unknowns.append(
                UnknownProjection(
                    edge.id, edge.reason or "An observed import has no unique target."
                )
            )
            imports_complete = False
    rules = _permission_rules(model, target)
    permissions = _permissions(target, rules)
    unknowns.extend(
        UnknownProjection(f"decision:{identity}:{item.target_id}", item.reason, item.rule_ids)
        for identity in sorted(permissions)
        for item in permissions[identity]
        if item.status == "undecided"
    )
    unknowns.extend(
        UnknownProjection(item.id, item.reason, (item.id,))
        for item in assessments
        if item.status == "UNKNOWN"
    )
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    counts: dict[tuple[str, str], int] = {}
    level_counts: dict[tuple[str | None, str, str], int] = {}
    for edge in observed.relationships:
        if edge.kind != "imports" or edge.target_id is None:
            continue
        source, endpoint = entities[edge.source_id], entities[edge.target_id]
        source_ids, target_ids = (
            _deepest_owners(target, source.qualified_name),
            _deepest_owners(target, endpoint.qualified_name),
        )
        pairs = set()
        if len(source_ids) == len(target_ids) == 1 and source_ids != target_ids:
            pairs.add((source_ids[0], target_ids[0]))
        for parent in {item.parent_id for item in target.component_intents}:
            a, b = (
                _scope_owners(target, source.qualified_name, parent),
                _scope_owners(target, endpoint.qualified_name, parent),
            )
            if len(a) == len(b) == 1 and a != b:
                key = (parent, a[0], b[0])
                level_counts[key] = level_counts.get(key, 0) + 1
                pairs.add((a[0], b[0]))
        for pair in pairs:
            counts[pair] = counts.get(pair, 0) + 1
    target_entities = {item.id: item for item in target.entities}
    relationships = []
    for edge in target.relationships:
        if edge.kind == "requires":
            continue
        evaluations = (
            tuple(item for item in report.comparison.assessments if item.subject_id == edge.id)
            if report.comparison
            else ()
        )
        status: AssessmentStatus = (
            "FAIL"
            if any(item.status == "FAIL" for item in evaluations)
            else "UNKNOWN"
            if not evaluations or any(item.status == "UNKNOWN" for item in evaluations)
            else "PASS"
        )
        reasons = tuple(item.reason for item in evaluations) or (
            "No authenticated Core assessment exists for this required relationship.",
        )
        relationships.append(
            RequiredRelationshipProjection(
                edge.id,
                edge.kind,
                edge.source_id,
                target_entities[edge.source_id].qualified_name,
                edge.target_id,
                target_entities[edge.target_id].qualified_name if edge.target_id else None,
                status,
                reasons,
            )
        )
        if status == "UNKNOWN":
            unknowns.append(UnknownProjection(edge.id, " ".join(reasons)))
    components = []
    declarations = {item.id: item for item in model.records("declarations") or ()}
    for intent in sorted(target.component_intents, key=lambda item: item.component_id):
        owned = tuple(
            sorted(
                (item for item in modules if ownership[item.id] == (intent.component_id,)),
                key=lambda item: item.qualified_name,
            )
        )
        scoped_modules = memberships.get(intent.component_id, set())
        subject_ids = _scope_subjects(report, scoped_modules)
        findings = tuple(
            item
            for item in report.findings
            if set(item.graph_subject_ids) & subject_ids
            or intent.component_id in item.graph_subject_ids
        )
        scoped = tuple(
            item
            for item in assessments
            if declarations.get(item.id) is not None
            and (text_value(declarations[item.id].data.get("parent_id")) or None)
            == (names[intent.parent_id] if intent.parent_id else None)
            and (not item.components or intent.label in item.components)
        )
        undecided = any(item.status == "undecided" for item in permissions[intent.component_id])
        if not imports_complete or not scoped_modules:
            status, reason = "UNKNOWN", "Complete owned module and import evidence is unavailable."
        elif (
            undecided
            or any(item.status == "UNKNOWN" for item in scoped)
            or any(item.status == "UNKNOWN" for item in findings)
        ):
            status, reason = (
                "UNKNOWN",
                "Dependency decisions or applicable Core assessments remain unknown.",
            )
        elif any(item.status == "FAIL" for item in findings):
            status, reason = "FAIL", "Core recorded a finding in this component's source facts."
        elif not any(item.evaluation_proven and item.status != "DECLARATION" for item in scoped):
            status, reason = "UNKNOWN", "No completed applicable Core evaluator scope is proven."
        else:
            status, reason = (
                "PASS",
                "Core completed the applicable scopes without a finding in this component.",
            )
        requires = tuple(
            RequiresProjection(
                edge.id,
                edge.target_id,
                edge.through,
                edge.reason or "",
                edge.decided_by,
                level_counts.get((intent.parent_id, intent.component_id, edge.target_id), 0)
                if imports_complete
                else None,
            )
            for edge in target.relationships
            if edge.kind == "requires"
            and edge.source_id == intent.component_id
            and edge.target_id is not None
        )
        source_paths = tuple(
            item.file_path
            for item in modules
            if item.id in scoped_modules and item.file_path is not None
        )
        components.append(
            ComponentProjection(
                id=intent.component_id,
                scope=names[intent.component_id],
                label=intent.label or intent.component_id,
                parent_id=intent.parent_id,
                role=intent.role,
                path=commonpath(source_paths) if source_paths else None,
                provenance=target_entities[intent.component_id].provenance,
                namespace=intent.namespace,
                packages=intent.packages,
                exact_modules=intent.exact_modules,
                responsibilities=target_entities[intent.component_id].responsibilities,
                not_responsible_for=intent.forbidden_responsibilities,
                public=intent.public,
                planned=intent.planned,
                modules=tuple(
                    ModuleProjection(item.qualified_name, item.file_path) for item in owned
                ),
                requires=requires,
                permissions=permissions[intent.component_id],
                used_by=tuple(
                    UsageProjection(a, count)
                    for (a, b), count in sorted(counts.items())
                    if b == intent.component_id
                ),
                finding_ids=tuple(sorted(item.id for item in findings)),
                status=status,
                reason=reason,
                decided_by=intent.decided_by,
            )
        )
    levels = []
    for parent in sorted(
        {item.parent_id for item in target.component_intents}, key=lambda item: item or ""
    ):
        ids = tuple(
            sorted(
                item.component_id for item in target.component_intents if item.parent_id == parent
            )
        )
        declared = {
            (edge.source_id, edge.target_id)
            for edge in target.relationships
            if edge.kind == "requires" and edge.source_id in ids and edge.target_id is not None
        }
        declared.update(
            (identity, permission.target_id)
            for identity in ids
            for permission in permissions[identity]
            if permission.status == "allowed"
        )
        used = {
            (a, b) for (scope, a, b), count in level_counts.items() if scope == parent and count > 0
        }
        eligible = (
            modules
            if parent is None
            else tuple(item for item in modules if item.id in memberships.get(parent, set()))
        )
        unowned = tuple(
            sorted(
                item.qualified_name
                for item in eligible
                if len(_scope_owners(target, item.qualified_name, parent)) != 1
            )
        )
        levels.append(
            LevelProjection(
                parent,
                ids,
                len(declared),
                len(used) if imports_complete else None,
                len(declared - used) if imports_complete else None,
                len(used - declared) if imports_complete else None,
                sum(
                    item.status == "undecided" for identity in ids for item in permissions[identity]
                ),
                unowned,
            )
        )
    projection_status: AssessmentStatus = (
        "UNKNOWN"
        if unknowns
        else "FAIL"
        if any(item.status == "FAIL" for item in report.findings)
        or any(item.status == "FAIL" for item in relationships)
        else "PASS"
    )
    return ArchitectureProjection(
        model.source,
        model.contract.digest,
        model.analyzer.code_digest,
        tuple(item for item in components if selected is None or item.id == selected),
        tuple(levels),
        rules,
        tuple(relationships),
        gaps,
        tuple(sorted(unknowns, key=lambda item: item.id)),
        projection_status,
        "Recorded Core findings remain."
        if projection_status == "FAIL"
        else "Missing ownership, decisions or Core evidence remain."
        if projection_status == "UNKNOWN"
        else "Authenticated architecture evidence is complete.",
        violation_remedy,
    )
