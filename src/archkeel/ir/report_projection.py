# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project the authenticated shared report for focused architecture consumers."""

from collections import Counter
from dataclasses import dataclass, field, replace
from posixpath import commonpath
from typing import Literal, TypeAlias

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    AssessmentStatus,
    ComponentRole,
    RelationshipKind,
)
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
from archkeel.ir.facts import SourceInfo
from archkeel.ir.model import (
    Coverage,
    Diagnostic,
    DiagnosticError,
    FilteredViolation,
    Observation,
    ReportFilter,
    RequiredComponent,
    RuleAssessment,
    RuleVerdict,
    RunResult,
    declared_package_pair,
    module_in_ownership,
    requires_covers,
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
            required_entries = tuple(
                RequiredComponent(edge.target_id, edge.reason or "", edge.through)
                for edge in requires
                if edge.target_id is not None
            )
            has_requires = requires_covers(required_entries, sibling.component_id)
            identifiers = tuple(
                sorted({*forbidden, *allowed, *complete, *(edge.id for edge in requires)})
            )
            status: PermissionStatus
            if forbidden:
                status, reason = (
                    "forbidden",
                    "A declared dependency rule forbids this component pair.",
                )
            elif complete and not has_requires:
                status, reason = (
                    "forbidden",
                    "complete_requires forbids this absent requires permission; "
                    "allowed_dependency does not override the constraint.",
                )
            elif has_requires or allowed:
                status, reason = (
                    "allowed",
                    "Declared permission subject to requires.through "
                    "and applicable permission_rules.",
                )
            else:
                status, reason = (
                    "undecided",
                    "No whole-component decision is declared; permission_rules "
                    "retain partial selectors.",
                )
            permissions.append(
                PermissionProjection(sibling.component_id, status, identifiers, reason)
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
    original_unknowns = {item.id: item for item in model.records("unknowns") or ()}
    unknowns = [
        UnknownProjection(
            item.id,
            text_value(original_unknowns[item.id].data.get("reason")) or item.title,
            item.rule_ids,
            original_unknowns[item.id].kind,
        )
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
        matches = {
            item.component_id
            for item in target.component_intents
            if component in {item.component_id, names[item.component_id], item.label}
        }
        selected = next(iter(matches)) if len(matches) == 1 else None
        if selected is None:
            raise DiagnosticError(
                Diagnostic(
                    "filter_unknown",
                    f"--component {component}",
                    "The component selector is absent or ambiguous across authenticated "
                    "IDs, scopes and labels.",
                    "Use an unambiguous component id or complete scope-qualified label.",
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
    unknowns.extend(
        UnknownProjection(
            f"ownership:{item.module}",
            item.reason,
            kind="module_ownership",
            scopes=tuple(names[identity] for identity in item.candidate_ids),
        )
        for item in gaps
    )
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
        UnknownProjection(
            f"decision:{identity}:{item.target_id}",
            item.reason,
            item.rule_ids,
            "dependency_permission",
            (names[identity], names[item.target_id]),
        )
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
    intents = {item.component_id: item for item in target.component_intents}

    def entity_component(identity: str) -> str | None:
        entity = target_entities[identity]
        while entity.id not in intents and entity.parent_id is not None:
            entity = target_entities[entity.parent_id]
        return entity.id if entity.id in intents else None

    def internal_scope(source_id: str, target_id: str | None, kind: RelationshipKind) -> str | None:
        if target_id is None or kind in {"realizes", "publishes"}:
            return None
        owner = entity_component(source_id)
        if owner is None or entity_component(target_id) != owner:
            return None
        if intents[owner].role in {ComponentRole.INTERFACE, ComponentRole.CONTRACT}:
            return None
        detail_kinds = {"class", "method", "attribute", "type_alias", "enum"}
        for identity in (source_id, target_id):
            entity = target_entities[identity]
            if entity.kind not in detail_kinds:
                return None
            while entity.parent_id is not None:
                if entity.kind == "interface":
                    return None
                entity = target_entities[entity.parent_id]
        return names[owner]

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
                tuple(
                    sorted(
                        {
                            owner
                            for identity in (edge.source_id, edge.target_id)
                            if identity is not None
                            and (owner := entity_component(identity)) is not None
                        }
                    )
                ),
                internal_scope(edge.source_id, edge.target_id, edge.kind),
            )
        )
        if status == "UNKNOWN":
            unknowns.append(
                UnknownProjection(
                    edge.id,
                    " ".join(reasons),
                    kind=edge.kind,
                    scopes=tuple(names[identity] for identity in relationships[-1].component_ids),
                )
            )
    components = []
    assessment_scopes: dict[str, set[str]] = {}
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
        for assessment in scoped:
            if assessment.status == "UNKNOWN":
                assessment_scopes.setdefault(assessment.id, set()).add(intent.component_id)
        selector_prefix = intent.namespace
        ancestor = intent.parent_id
        while selector_prefix is None and ancestor is not None:
            selector_prefix = intents[ancestor].namespace
            ancestor = intents[ancestor].parent_id
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
                selector_prefix=selector_prefix,
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
    scoped_unknowns = []
    for unknown in unknowns:
        original = original_unknowns.get(unknown.id)
        source_module = text_value(original.data.get("module")) if original else ""
        source_scope = text_value(original.data.get("source")) if original else ""
        module_identity = next(
            (item.id for item in modules if item.qualified_name == source_module), None
        )
        scoped_ids = (
            set(ownership[module_identity])
            if module_identity is not None
            else {
                intent.component_id
                for intent in target.component_intents
                if source_scope and source_scope in intent.packages
            }
            if source_scope
            else {owner.id for owner in components if unknown.id in owner.finding_ids}
            | assessment_scopes.get(unknown.id, set())
        )
        inherited = set()
        for identity in scoped_ids:
            ancestor = intents[identity].parent_id
            while ancestor is not None:
                inherited.add(ancestor)
                ancestor = intents[ancestor].parent_id
        scoped_ids -= inherited
        scoped_unknowns.append(
            replace(
                unknown,
                kind=declarations[unknown.id].kind if unknown.id in declarations else unknown.kind,
                scopes=unknown.scopes or tuple(sorted(names[identity] for identity in scoped_ids)),
            )
        )
    unknowns = scoped_unknowns
    projection_status: AssessmentStatus = (
        "UNKNOWN"
        if unknowns
        else "FAIL"
        if any(item.status == "FAIL" for item in report.findings)
        or any(item.status == "FAIL" for item in relationships)
        else "PASS"
    )
    context_parents: set[str | None] = set()
    if selected is not None:
        parent = intents[selected].parent_id
        context_parents.add(parent)
        while parent is not None:
            parent = intents[parent].parent_id
            context_parents.add(parent)
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
        policy_context=tuple(
            item for item in components if item.id != selected and item.parent_id in context_parents
        ),
    )


@dataclass(frozen=True, slots=True)
class PermissionGroup:
    status: PermissionStatus
    reason: int
    target_ids: tuple[str, ...]
    rule_ids: tuple[str, ...] = ()


ScopeCount: TypeAlias = tuple[tuple[str, ...], int]
UnknownGroups: TypeAlias = dict[str, dict[str, tuple[ScopeCount, ...]]]


@dataclass(frozen=True, slots=True)
class ArchitectureComponentView:
    id: str
    scope: str
    path: str | None
    provenance: tuple[str, ...]
    packages: tuple[str, ...]
    responsibilities: tuple[str, ...]
    not_responsible_for: tuple[str, ...]
    status: AssessmentStatus
    reason: int
    decided_by: Literal["architect", "agent"] | None
    parent_id: str | None = None
    role: ComponentRole = ComponentRole.COMPONENT
    namespace: str | None = None
    selector_prefix: str | None = None
    exact_modules: tuple[str, ...] = ()
    public: dict[str, tuple[str, ...]] | None = None
    planned: dict[str, tuple[str, ...]] | None = None
    modules: dict[str, str | None] = field(default_factory=dict)
    requires: tuple[RequiresProjection, ...] = ()
    permissions: tuple[PermissionGroup, ...] = ()
    used_by: dict[str, int] = field(default_factory=dict)
    finding_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PermissionContextView:
    id: str
    scope: str
    parent_id: str | None
    packages: tuple[str, ...]
    exact_modules: tuple[str, ...]
    requires: tuple[RequiresProjection, ...]
    permissions: tuple[PermissionGroup, ...]


@dataclass(frozen=True, slots=True)
class RequiredRelationshipSummary:
    scope: str
    kind: RelationshipKind
    status: AssessmentStatus
    reasons: tuple[str, ...]
    count: int


@dataclass(frozen=True, slots=True)
class DependencyPermissionView:
    id: str
    kind: PermissionRuleKind
    rationale: str
    decided_by: str | None
    parent_id: str | None = None
    source: str | None = None
    target: str | None = None
    target_symbol: str | None = None
    allowed_sources: tuple[str, ...] = ()
    include_type_checking: bool | None = None


@dataclass(frozen=True, slots=True)
class ArchitectureCommandView:
    source: SourceInfo
    contract_digest: str
    analyzer_digest: str
    components: tuple[ArchitectureComponentView, ...]
    policy_context: tuple[PermissionContextView, ...]
    levels: tuple[LevelProjection, ...]
    permission_rules: tuple[DependencyPermissionView, ...]
    required_relationships: tuple[RequiredRelationshipProjection, ...]
    required_summaries: tuple[RequiredRelationshipSummary, ...]
    ownership_gaps: tuple[OwnershipGap, ...]
    unknowns: UnknownGroups
    status: AssessmentStatus
    reason: str
    reasons: tuple[str, ...]
    violation_remedy: str


@dataclass(frozen=True, slots=True)
class ArchitectureCommandEnvelope:
    exit_code: Literal[0, 1, 2]
    observation_complete: Literal["PASS", "UNKNOWN"]
    declared_rules: RuleVerdict
    coverage: Coverage | None
    diagnostics: tuple[Diagnostic, ...]
    report_filter: ReportFilter | None
    architecture_projection: ArchitectureCommandView
    filtered_violations: tuple[FilteredViolation, ...]
    command: Literal["report"] = "report"
    expectation_fulfilled: Literal["n/a"] = "n/a"
    schema_version: Literal["1.0.0"] = "1.0.0"


def short_selector(value: str, prefix: str | None) -> str:
    """Only authenticated namespaces may abbreviate a fully reconstructible selector."""
    if prefix is not None and (
        value == prefix or value.startswith(f"{prefix}.") or value.startswith(f"{prefix}:")
    ):
        return value[len(prefix) :]
    return value


def grouped_selectors(
    selectors: tuple[str, ...] | None, prefix: str | None
) -> dict[str, tuple[str, ...]] | None:
    if selectors is None:
        return None
    modules: dict[str, list[str]] = {}
    for selector in selectors:
        module, separator, symbol = selector.partition(":")
        modules.setdefault(short_selector(module, prefix), []).append(symbol if separator else "")
    return {module: tuple(symbols) for module, symbols in modules.items()}


def unknown_groups(unknowns: tuple[UnknownProjection, ...]) -> UnknownGroups:
    groups: dict[tuple[str, str], Counter[tuple[str, ...]]] = {}
    for unknown in unknowns:
        groups.setdefault((unknown.kind, unknown.reason), Counter())[unknown.scopes] += 1
    result: UnknownGroups = {}
    for (kind, reason), counts in sorted(groups.items()):
        result.setdefault(kind, {})[reason] = tuple(sorted(counts.items()))
    return result


def architecture_command_envelope(result: RunResult) -> ArchitectureCommandEnvelope:
    projection = result.architecture_projection
    if projection is None:
        raise ValueError("architecture command requires its authenticated projection")
    reasons: list[str] = []

    def reason_ref(reason: str) -> int:
        if reason not in reasons:
            reasons.append(reason)
        return reasons.index(reason)

    violations = result.filtered_violations or ()
    violation_ids = {item.record.id for item in violations}

    def permission_groups(component: ComponentProjection) -> tuple[PermissionGroup, ...]:
        groups: dict[tuple[PermissionStatus, tuple[str, ...], str], list[str]] = {}
        requires_ids = {item.id for item in component.requires}
        for permission in component.permissions:
            rule_ids = tuple(
                identity
                for identity in permission.rule_ids
                if permission.status != "allowed" or identity not in requires_ids
            )
            groups.setdefault((permission.status, rule_ids, permission.reason), []).append(
                permission.target_id
            )
        return tuple(
            PermissionGroup(status, reason_ref(reason), tuple(targets), rule_ids)
            for (status, rule_ids, reason), targets in sorted(groups.items())
        )

    components = []
    for component in projection.components:
        prefix = component.selector_prefix
        modules = {}
        for module in component.modules:
            path = module.path
            if path is not None and component.path is not None:
                if path == component.path:
                    path = ""
                elif path.startswith(f"{component.path}/"):
                    path = path[len(component.path) + 1 :]
            modules[short_selector(module.name, prefix)] = path
        components.append(
            ArchitectureComponentView(
                id=component.id,
                scope=component.scope,
                parent_id=component.parent_id,
                role=component.role,
                path=component.path,
                provenance=component.provenance,
                namespace=component.namespace,
                selector_prefix=prefix if prefix != component.namespace else None,
                packages=tuple(short_selector(item, prefix) for item in component.packages),
                exact_modules=tuple(
                    short_selector(item, prefix) for item in component.exact_modules
                ),
                responsibilities=component.responsibilities,
                not_responsible_for=component.not_responsible_for,
                public=grouped_selectors(component.public, prefix),
                planned=grouped_selectors(component.planned, prefix),
                modules=modules,
                requires=component.requires,
                permissions=permission_groups(component),
                used_by={item.component_id: item.import_sites for item in component.used_by},
                finding_ids=tuple(
                    identity for identity in component.finding_ids if identity in violation_ids
                ),
                status=component.status,
                reason=reason_ref(component.reason),
                decided_by=component.decided_by,
            )
        )
    selected = (
        projection.components[0]
        if result.report_filter is not None
        and result.report_filter.component is not None
        and projection.components
        else None
    )
    context_parents = {item.parent_id for item in projection.policy_context}
    if selected is not None:
        context_parents.add(selected.parent_id)
    relationships = tuple(
        relationship
        for relationship in projection.required_relationships
        if selected is None or selected.id in relationship.component_ids
    )
    detail_relationships = tuple(item for item in relationships if item.internal_scope is None)
    summary_counts = Counter(
        (item.internal_scope, item.kind, item.status, item.reasons)
        for item in relationships
        if item.internal_scope is not None
    )
    summaries = tuple(
        RequiredRelationshipSummary(scope, kind, status, original_reasons, count)
        for (scope, kind, status, original_reasons), count in sorted(summary_counts.items())
        if scope is not None
    )
    view = ArchitectureCommandView(
        projection.source,
        projection.contract_digest,
        projection.analyzer_digest,
        tuple(components),
        tuple(
            PermissionContextView(
                item.id,
                item.scope,
                item.parent_id,
                item.packages,
                item.exact_modules,
                item.requires,
                permission_groups(item),
            )
            for item in projection.policy_context
        ),
        tuple(
            level
            for level in projection.levels
            if selected is None or level.parent_id in context_parents
        ),
        tuple(
            DependencyPermissionView(
                rule.id,
                rule.kind,
                rule.rationale,
                rule.decided_by,
                rule.parent_id,
                rule.source,
                rule.target,
                rule.target_symbol,
                rule.allowed_sources,
                rule.include_type_checking,
            )
            for rule in projection.permission_rules
            if selected is None or rule.parent_id in context_parents
        ),
        detail_relationships,
        summaries,
        projection.ownership_gaps,
        unknown_groups(projection.unknowns),
        projection.status,
        projection.reason,
        tuple(reasons),
        projection.violation_remedy,
    )
    return ArchitectureCommandEnvelope(
        result.exit_code,
        result.observation_complete,
        result.declared_rules,
        result.coverage,
        result.diagnostics,
        result.report_filter,
        view,
        violations,
    )
