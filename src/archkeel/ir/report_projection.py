# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project the authenticated shared report for focused architecture consumers."""

from dataclasses import replace
from posixpath import commonpath

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    ArchitectureRuleKind,
    AssessmentStatus,
    ComponentIntent,
    ComponentRole,
    CoverageStatus,
    Entity,
    EntityKind,
    PresenceKind,
    RelationshipKind,
    ReportFinding,
    RuleAssessment,
    RuleAssessmentStatus,
    parse_architecture_rule_kind,
)
from archkeel.ir.architecture_projection import (
    ArchitectureProjection,
    ComponentProjection,
    LevelProjection,
    ModuleProjection,
    OwnershipGap,
    PermissionProjection,
    PermissionRuleProjection,
    PermissionStatus,
    RequiredRelationshipProjection,
    RequiresProjection,
    UnknownProjection,
    UsageProjection,
)
from archkeel.ir.codec_contract import parse_dependency_selector

# Preserve the established command-view imports while their implementation has one owner.
from archkeel.ir.command_view import (
    ArchitectureCommandEnvelope as ArchitectureCommandEnvelope,
)
from archkeel.ir.command_view import (
    ArchitectureCommandView as ArchitectureCommandView,
)
from archkeel.ir.command_view import (
    ArchitectureComponentView as ArchitectureComponentView,
)
from archkeel.ir.command_view import (
    PermissionContextView as PermissionContextView,
)
from archkeel.ir.command_view import (
    PermissionGroup as PermissionGroup,
)
from archkeel.ir.command_view import (
    RequiredRelationshipSummary as RequiredRelationshipSummary,
)
from archkeel.ir.command_view import (
    ScopeCount as ScopeCount,
)
from archkeel.ir.command_view import (
    UnknownGroups as UnknownGroups,
)
from archkeel.ir.command_view import (
    architecture_command_envelope as architecture_command_envelope,
)
from archkeel.ir.command_view import (
    grouped_selectors as grouped_selectors,
)
from archkeel.ir.command_view import (
    short_selector as short_selector,
)
from archkeel.ir.command_view import (
    unknown_groups as unknown_groups,
)
from archkeel.ir.decisions import rule_assessment_applies_to_component
from archkeel.ir.dependency import DependencyOwner, DependencySelector
from archkeel.ir.facts import EvidenceClass as _EvidenceClass
from archkeel.ir.facts import Record
from archkeel.ir.model import (
    RULE_KINDS,
    Diagnostic,
    DiagnosticError,
    Observation,
    RequiredComponent,
    Verdict,
    dependency_owners,
    module_in_ownership,
    requires_covers,
    text_value,
)
from archkeel.ir.model import DiagnosticKind as _DiagnosticKind


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
    model: Observation, target: ArchitectureGraph, assessments: tuple[RuleAssessment, ...]
) -> tuple[PermissionRuleProjection, ...]:
    names: dict[str, str] = _scope_names(target)
    scope_ids = {scope: identity for identity, scope in names.items()}
    core = {item.id: item for item in assessments}
    return tuple(
        PermissionRuleProjection(
            item,
            core.get(item.id),
            scope_ids.get(text_value(item.data.get("parent_id"))),
        )
        for item in sorted(model.records("declarations") or (), key=lambda item: item.id)
        if parse_architecture_rule_kind(item.kind) in RULE_KINDS
        and item.evidence_class == _EvidenceClass.DECLARED_RULE
    )


def _pair_permission_rules(
    level_rules: tuple[Record, ...],
    owners: tuple[DependencyOwner, ...],
    pair: tuple[str, str],
    selectors: dict[str, DependencySelector],
) -> tuple[Record, ...]:
    deciding = []
    for rule in level_rules:
        selector = selectors.get(rule.id)
        if selector is not None and selector.component_pair(owners) == pair:
            deciding.append(rule)
    return tuple(deciding)


def _permissions(
    target: ArchitectureGraph, rules: tuple[PermissionRuleProjection, ...]
) -> dict[str, tuple[PermissionProjection, ...]]:
    selectors = {
        item.declaration.id: parse_dependency_selector(item.declaration)
        for item in rules
        if parse_architecture_rule_kind(item.declaration.kind)
        in {ArchitectureRuleKind.ALLOWED_DEPENDENCY, ArchitectureRuleKind.FORBIDDEN_DEPENDENCY}
    }
    rows = {}
    for source in target.component_intents:
        siblings = tuple(
            item for item in target.component_intents if item.parent_id == source.parent_id
        )
        owners = dependency_owners(
            tuple((item.component_id, item.packages, item.exact_modules) for item in siblings)
        )
        level_rules = tuple(
            item.declaration for item in rules if item.parent_id == source.parent_id
        )
        complete = tuple(
            item.id
            for item in level_rules
            if parse_architecture_rule_kind(item.kind) is ArchitectureRuleKind.COMPLETE_REQUIRES
        )
        permissions = []
        for sibling in siblings:
            if sibling.component_id == source.component_id:
                continue
            pair = (source.component_id, sibling.component_id)
            requires = tuple(
                edge
                for edge in target.relationships
                if edge.kind == RelationshipKind.REQUIRES
                and (edge.source_id, edge.target_id) == pair
            )
            deciding = _pair_permission_rules(level_rules, owners, pair, selectors)
            forbidden = tuple(
                rule.id
                for rule in deciding
                if parse_architecture_rule_kind(rule.kind)
                is ArchitectureRuleKind.FORBIDDEN_DEPENDENCY
                and not rule.data.get("allowed_sources")
            )
            allowed = tuple(
                rule.id
                for rule in deciding
                if parse_architecture_rule_kind(rule.kind)
                is ArchitectureRuleKind.ALLOWED_DEPENDENCY
            )
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
                    PermissionStatus.FORBIDDEN,
                    "A declared dependency rule forbids this component pair.",
                )
            elif complete and not has_requires:
                status, reason = (
                    PermissionStatus.FORBIDDEN,
                    "complete_requires forbids this absent requires permission; "
                    "allowed_dependency does not override the constraint.",
                )
            elif has_requires or allowed:
                status, reason = (
                    PermissionStatus.ALLOWED,
                    "Declared component permission; each import must satisfy requires.through "
                    "and all governing rules. Core assessments describe observed compliance.",
                )
            else:
                status, reason = (
                    PermissionStatus.UNDECIDED,
                    "No whole-component decision is declared; permission_rules "
                    "retain partial selectors.",
                )
            permissions.append(
                PermissionProjection(sibling.component_id, status, identifiers, reason)
            )
        rows[source.component_id] = tuple(sorted(permissions, key=lambda item: item.target_id))
    return rows


def _projection_unknowns(model: Observation, report: ArchitectureReport) -> list[UnknownProjection]:
    original_unknowns = {item.id: item for item in model.records("unknowns") or ()}
    unknowns: list[UnknownProjection] = []
    target, observed = report.target, report.observed
    for item in report.findings:
        if item.status == AssessmentStatus.UNKNOWN:
            original_unknown: Record = original_unknowns[item.id]
            unknowns.append(
                UnknownProjection(
                    item.id,
                    text_value(original_unknown.data.get("reason")) or item.title,
                    item.rule_ids,
                    original_unknown.kind,
                )
            )
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
    return unknowns


def _unavailable_projection(
    model: Observation,
    unknowns: list[UnknownProjection],
    remedy: str,
    component: str | None,
) -> ArchitectureProjection:
    if component is not None:
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.FILTER_UNKNOWN,
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
        AssessmentStatus.UNKNOWN,
        "Target or observed evidence is unavailable.",
        remedy,
    )


def _selected_component(
    target: ArchitectureGraph,
    component: str | None,
    names: dict[str, str],
    *,
    prefer_top_label: bool = False,
) -> str | None:
    selected = None
    if component is not None:
        if prefer_top_label:
            top = {
                item.component_id
                for item in target.component_intents
                if item.parent_id is None and item.label == component
            }
            if len(top) == 1:
                return next(iter(top))
        matches = {
            item.component_id
            for item in target.component_intents
            if component in {item.component_id, names[item.component_id], item.label}
        }
        selected = next(iter(matches)) if len(matches) == 1 else None
        if selected is None:
            raise DiagnosticError(
                Diagnostic(
                    _DiagnosticKind.FILTER_UNKNOWN,
                    f"--component {component}",
                    "The component selector is absent or ambiguous across authenticated "
                    "IDs, scopes and labels.",
                    "Use an unambiguous component id or complete scope-qualified label.",
                )
            )
    return selected


def _ownership_gaps(
    modules: tuple[Entity, ...],
    ownership: dict[str, tuple[str, ...]],
) -> tuple[OwnershipGap, ...]:
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
    return gaps


def _import_coverage(
    model: Observation,
    observed: ArchitectureGraph,
    modules: tuple[Entity, ...],
) -> tuple[bool, list[UnknownProjection]]:
    unknowns: list[UnknownProjection] = []
    covered_imports = {
        item.scope_id
        for item in observed.coverage
        if RelationshipKind.IMPORTS in item.relationship_kinds
        and item.status == CoverageStatus.COMPLETE
    }
    imports_complete = (
        model.coverage.status == Verdict.PASS
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
        if edge.kind == RelationshipKind.IMPORTS and edge.target_id is None:
            unknowns.append(
                UnknownProjection(
                    edge.id, edge.reason or "An observed import has no unique target."
                )
            )
            imports_complete = False
    return imports_complete, unknowns


def _usage_counts(
    target: ArchitectureGraph,
    observed: ArchitectureGraph,
) -> tuple[dict[tuple[str, str], int], dict[tuple[str | None, str, str], int]]:
    entities = {item.id: item for item in observed.entities}
    counts: dict[tuple[str, str], int] = {}
    level_counts: dict[tuple[str | None, str, str], int] = {}
    for edge in observed.relationships:
        if edge.kind != RelationshipKind.IMPORTS or edge.target_id is None:
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
    return counts, level_counts


def _entity_component(
    identity: str,
    target_entities: dict[str, Entity],
    intents: dict[str, ComponentIntent],
) -> str | None:
    entity = target_entities[identity]
    while entity.id not in intents and entity.parent_id is not None:
        entity = target_entities[entity.parent_id]
    return entity.id if entity.id in intents else None


def _internal_relationship_scope(
    source_id: str,
    target_id: str | None,
    kind: RelationshipKind,
    target_entities: dict[str, Entity],
    intents: dict[str, ComponentIntent],
    names: dict[str, str],
) -> str | None:
    if target_id is None or kind in {RelationshipKind.REALIZES, RelationshipKind.PUBLISHES}:
        return None
    owner = _entity_component(source_id, target_entities, intents)
    if owner is None or _entity_component(target_id, target_entities, intents) != owner:
        return None
    if intents[owner].role in {ComponentRole.INTERFACE, ComponentRole.CONTRACT}:
        return None
    detail_kinds = {
        EntityKind.CLASS,
        EntityKind.METHOD,
        EntityKind.ATTRIBUTE,
        EntityKind.TYPE_ALIAS,
        EntityKind.ENUM,
        EntityKind.MIXIN,
    }
    for identity in (source_id, target_id):
        entity = target_entities[identity]
        if entity.kind not in detail_kinds:
            return None
        while entity.parent_id is not None:
            if entity.kind == EntityKind.INTERFACE:
                return None
            entity = target_entities[entity.parent_id]
    return names[owner]


def _required_relationships(
    report: ArchitectureReport,
    target: ArchitectureGraph,
    names: dict[str, str],
) -> tuple[RequiredRelationshipProjection, ...]:
    target_entities = {item.id: item for item in target.entities}
    intents = {item.component_id: item for item in target.component_intents}
    relationships = []
    for edge in target.relationships:
        if edge.kind == RelationshipKind.REQUIRES:
            continue
        evaluations = (
            tuple(item for item in report.comparison.assessments if item.subject_id == edge.id)
            if report.comparison
            else ()
        )
        status: AssessmentStatus = (
            AssessmentStatus.FAIL
            if any(item.status == AssessmentStatus.FAIL for item in evaluations)
            else AssessmentStatus.UNKNOWN
            if not evaluations
            or any(item.status == AssessmentStatus.UNKNOWN for item in evaluations)
            else AssessmentStatus.PASS
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
                            and (owner := _entity_component(identity, target_entities, intents))
                            is not None
                        }
                    )
                ),
                _internal_relationship_scope(
                    edge.source_id, edge.target_id, edge.kind, target_entities, intents, names
                ),
            )
        )
    return tuple(relationships)


def _component_status(
    imports_complete: bool,
    scoped_modules: set[str],
    scoped: tuple[RuleAssessment, ...],
    findings: tuple[ReportFinding, ...],
    permissions: tuple[PermissionProjection, ...],
) -> tuple[AssessmentStatus, str]:
    status: AssessmentStatus
    undecided = any(item.status is PermissionStatus.UNDECIDED for item in permissions)
    if not imports_complete or not scoped_modules:
        status, reason = (
            AssessmentStatus.UNKNOWN,
            "Complete owned module and import evidence is unavailable.",
        )
    elif (
        undecided
        or any(item.status == RuleAssessmentStatus.UNKNOWN for item in scoped)
        or any(item.status == AssessmentStatus.UNKNOWN for item in findings)
    ):
        status, reason = (
            AssessmentStatus.UNKNOWN,
            "Dependency decisions or applicable Core assessments remain unknown.",
        )
    elif any(item.status == AssessmentStatus.FAIL for item in findings):
        status, reason = (
            AssessmentStatus.FAIL,
            "Core recorded a finding in this component's source facts.",
        )
    elif not any(
        item.evaluation_proven and item.status != RuleAssessmentStatus.DECLARATION
        for item in scoped
    ):
        status, reason = (
            AssessmentStatus.UNKNOWN,
            "No completed applicable Core evaluator scope is proven.",
        )
    else:
        status, reason = (
            AssessmentStatus.PASS,
            "Core completed the applicable scopes without a finding in this component.",
        )
    return status, reason


def _component_requires(
    target: ArchitectureGraph,
    intent: ComponentIntent,
    level_counts: dict[tuple[str | None, str, str], int],
    imports_complete: bool,
) -> tuple[RequiresProjection, ...]:
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
        if edge.kind == RelationshipKind.REQUIRES
        and edge.source_id == intent.component_id
        and edge.target_id is not None
    )
    return requires


def _component_view(
    intent: ComponentIntent,
    entity: Entity,
    names: dict[str, str],
    modules: tuple[Entity, ...],
    owned: tuple[Entity, ...],
    scoped_modules: set[str],
    requires: tuple[RequiresProjection, ...],
    permissions: dict[str, tuple[PermissionProjection, ...]],
    counts: dict[tuple[str, str], int],
    findings: tuple[ReportFinding, ...],
    status_reason: tuple[AssessmentStatus, str],
    selector_prefix: str | None,
) -> ComponentProjection:
    source_paths = tuple(
        item.file_path
        for item in modules
        if item.id in scoped_modules and item.file_path is not None
    )
    return ComponentProjection(
        id=intent.component_id,
        scope=names[intent.component_id],
        label=intent.label or intent.component_id,
        parent_id=intent.parent_id,
        role=intent.role,
        path=commonpath(source_paths) if source_paths else None,
        provenance=entity.provenance,
        namespace=intent.namespace,
        packages=intent.packages,
        exact_modules=intent.exact_modules,
        responsibilities=entity.responsibilities,
        not_responsible_for=intent.forbidden_responsibilities,
        public=intent.public,
        planned=intent.planned,
        modules=tuple(ModuleProjection(item.qualified_name, item.file_path) for item in owned),
        requires=requires,
        permissions=permissions[intent.component_id],
        used_by=tuple(
            UsageProjection(a, count)
            for (a, b), count in sorted(counts.items())
            if b == intent.component_id
        ),
        finding_ids=tuple(sorted(item.id for item in findings)),
        status=status_reason[0],
        reason=status_reason[1],
        decided_by=intent.decided_by,
        selector_prefix=selector_prefix,
        layer=intent.layer,
    )


def _component_projections(
    model: Observation,
    report: ArchitectureReport,
    target: ArchitectureGraph,
    assessments: tuple[RuleAssessment, ...],
    names: dict[str, str],
    modules: tuple[Entity, ...],
    ownership: dict[str, tuple[str, ...]],
    permissions: dict[str, tuple[PermissionProjection, ...]],
    counts: dict[tuple[str, str], int],
    level_counts: dict[tuple[str | None, str, str], int],
    imports_complete: bool,
) -> tuple[tuple[ComponentProjection, ...], dict[str, set[str]]]:
    target_entities = {item.id: item for item in target.entities}
    intents = {item.component_id: item for item in target.component_intents}
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    components = []
    assessment_scopes: dict[str, set[str]] = {}
    declarations = {item.id: item for item in model.records("declarations") or ()}
    scope_ids = {scope: identity for identity, scope in names.items()}
    for intent in sorted(target.component_intents, key=lambda item: item.component_id):
        owned = tuple(
            sorted(
                (item for item in modules if ownership[item.id] == (intent.component_id,)),
                key=lambda item: item.qualified_name,
            )
        )
        scoped_modules = memberships.get(intent.component_id, set())
        subject_ids = _scope_subjects(report, scoped_modules)
        claimed_modules = {
            identity for identity, owners in ownership.items() if intent.component_id in owners
        }
        findings = tuple(
            item
            for item in report.findings
            if set(item.graph_subject_ids) & subject_ids
            or intent.component_id in item.graph_subject_ids
            or parse_architecture_rule_kind(item.kind) is ArchitectureRuleKind.COMPLETE_ASSIGNMENT
            and bool(set(item.graph_subject_ids) & claimed_modules)
        )
        scoped_rows: list[RuleAssessment] = []
        for assessment in assessments:
            if _assessment_applies_to_intent(assessment, declarations, scope_ids, intent):
                scoped_rows.append(assessment)
        scoped = tuple(scoped_rows)
        for assessment in scoped:
            if assessment.status == RuleAssessmentStatus.UNKNOWN:
                scopes: set[str] = assessment_scopes.setdefault(assessment.id, set())
                scopes.add(intent.component_id)
        selector_prefix = intent.namespace
        ancestor = intent.parent_id
        while selector_prefix is None and ancestor is not None:
            selector_prefix = intents[ancestor].namespace
            ancestor = intents[ancestor].parent_id
        components.append(
            _component_view(
                intent,
                target_entities[intent.component_id],
                names,
                modules,
                owned,
                scoped_modules,
                _component_requires(target, intent, level_counts, imports_complete),
                permissions,
                counts,
                findings,
                _component_status(
                    imports_complete,
                    scoped_modules,
                    scoped,
                    findings,
                    permissions[intent.component_id],
                ),
                selector_prefix,
            )
        )
    return tuple(components), assessment_scopes


def _assessment_applies_to_intent(
    assessment: RuleAssessment,
    declarations: dict[str, Record],
    scope_ids: dict[str, str],
    intent: ComponentIntent,
) -> bool:
    declaration = declarations.get(assessment.id)
    if declaration is None:
        return False
    parent_scope = text_value(declaration.data.get("parent_id")) or None
    if parent_scope is not None and parent_scope not in scope_ids:
        return False
    return rule_assessment_applies_to_component(
        assessment,
        scope_ids.get(parent_scope) if parent_scope is not None else None,
        intent.parent_id,
        intent.label,
    )


def _level_projections(
    target: ArchitectureGraph,
    modules: tuple[Entity, ...],
    memberships: dict[str, set[str]],
    permissions: dict[str, tuple[PermissionProjection, ...]],
    level_counts: dict[tuple[str | None, str, str], int],
    imports_complete: bool,
) -> tuple[LevelProjection, ...]:
    levels = []
    for parent in sorted(
        {item.parent_id for item in target.component_intents}, key=lambda item: item or ""
    ):
        ids = tuple(
            sorted(
                item.component_id for item in target.component_intents if item.parent_id == parent
            )
        )
        declared: set[tuple[str, str]] = {
            (edge.source_id, edge.target_id)
            for edge in target.relationships
            if edge.kind == RelationshipKind.REQUIRES
            and edge.source_id in ids
            and edge.target_id is not None
        }
        declared.update(
            (identity, permission.target_id)
            for identity in ids
            for permission in permissions[identity]
            if permission.status is PermissionStatus.ALLOWED
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
                    item.status is PermissionStatus.UNDECIDED
                    for identity in ids
                    for item in permissions[identity]
                ),
                unowned,
            )
        )
    return tuple(levels)


def _scoped_unknowns(
    model: Observation,
    target: ArchitectureGraph,
    unknowns: list[UnknownProjection],
    names: dict[str, str],
    modules: tuple[Entity, ...],
    ownership: dict[str, tuple[str, ...]],
    components: tuple[ComponentProjection, ...],
    assessment_scopes: dict[str, set[str]],
) -> tuple[UnknownProjection, ...]:
    original_unknowns = {item.id: item for item in model.records("unknowns") or ()}
    declarations = {item.id: item for item in model.records("declarations") or ()}
    intents = {item.component_id: item for item in target.component_intents}
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
    return tuple(scoped_unknowns)


def _selected_projection(
    model: Observation,
    report: ArchitectureReport,
    target: ArchitectureGraph,
    components: tuple[ComponentProjection, ...],
    levels: tuple[LevelProjection, ...],
    rules: tuple[PermissionRuleProjection, ...],
    relationships: tuple[RequiredRelationshipProjection, ...],
    gaps: tuple[OwnershipGap, ...],
    unknowns: tuple[UnknownProjection, ...],
    selected: str | None,
    violation_remedy: str,
) -> ArchitectureProjection:
    intents = {item.component_id: item for item in target.component_intents}
    projection_status: AssessmentStatus = (
        AssessmentStatus.UNKNOWN
        if unknowns
        else AssessmentStatus.FAIL
        if any(item.status == AssessmentStatus.FAIL for item in report.findings)
        or any(item.status == AssessmentStatus.FAIL for item in relationships)
        else AssessmentStatus.PASS
    )
    subtree_ids: set[str] = set()
    context_parents: set[str | None] = set()
    parent: str | None
    if selected is not None:
        for intent in target.component_intents:
            parent = intent.component_id
            while parent is not None and parent != selected:
                parent = intents[parent].parent_id
            if parent == selected:
                subtree_ids.add(intent.component_id)
        context_parents.update(subtree_ids)
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
        tuple(level for level in levels if selected is None or level.parent_id in context_parents),
        tuple(rule for rule in rules if selected is None or rule.parent_id in context_parents),
        tuple(
            item
            for item in relationships
            if selected is None or not subtree_ids.isdisjoint(item.component_ids)
        ),
        gaps,
        tuple(sorted(unknowns, key=lambda item: item.id)),
        projection_status,
        "Recorded Core findings remain."
        if projection_status == AssessmentStatus.FAIL
        else "Missing ownership, decisions or Core evidence remain."
        if projection_status == AssessmentStatus.UNKNOWN
        else "Authenticated architecture evidence is complete.",
        violation_remedy,
        policy_context=tuple(
            item for item in components if item.id != selected and item.parent_id in context_parents
        ),
    )


def _projection_uncertainties(
    gaps: tuple[OwnershipGap, ...],
    permissions: dict[str, tuple[PermissionProjection, ...]],
    assessments: tuple[RuleAssessment, ...],
    relationships: tuple[RequiredRelationshipProjection, ...],
    names: dict[str, str],
) -> list[UnknownProjection]:
    unknowns: list[UnknownProjection] = []
    unknowns.extend(
        UnknownProjection(
            f"ownership:{item.module}",
            item.reason,
            kind="module_ownership",
            scopes=tuple(names[identity] for identity in item.candidate_ids),
        )
        for item in gaps
    )
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
        if item.status is PermissionStatus.UNDECIDED
    )
    unknowns.extend(
        UnknownProjection(item.id, item.reason, (item.id,))
        for item in assessments
        if item.status == RuleAssessmentStatus.UNKNOWN
    )
    unknowns.extend(
        UnknownProjection(
            item.id,
            " ".join(item.reasons),
            kind=item.kind,
            scopes=tuple(names[identity] for identity in item.component_ids),
        )
        for item in relationships
        if item.status == AssessmentStatus.UNKNOWN
    )
    return unknowns


def architecture_projection(
    model: Observation,
    report: ArchitectureReport,
    assessments: tuple[RuleAssessment, ...],
    *,
    violation_remedy: str,
    component: str | None = None,
    prefer_top_label: bool = False,
) -> ArchitectureProjection:
    """Project one authenticated report; filters retain global uncertainty and source identity."""
    report.validate()
    target, observed = report.target, report.observed
    unknowns = _projection_unknowns(model, report)
    if target is None or observed is None:
        return _unavailable_projection(model, unknowns, violation_remedy, component)
    names = _scope_names(target)
    selected = _selected_component(target, component, names, prefer_top_label=prefer_top_label)
    modules = tuple(
        item
        for item in observed.entities
        if item.kind == EntityKind.MODULE and item.presence == PresenceKind.DEFINED
    )
    ownership = {item.id: _deepest_owners(target, item.qualified_name) for item in modules}
    gaps = _ownership_gaps(modules, ownership)
    imports_complete, import_unknowns = _import_coverage(model, observed, modules)
    unknowns.extend(import_unknowns)
    rules = _permission_rules(model, target, assessments)
    permissions = _permissions(target, rules)
    counts, level_counts = _usage_counts(target, observed)
    relationships = _required_relationships(report, target, names)
    unknowns.extend(_projection_uncertainties(gaps, permissions, assessments, relationships, names))
    components, assessment_scopes = _component_projections(
        model,
        report,
        target,
        assessments,
        names,
        modules,
        ownership,
        permissions,
        counts,
        level_counts,
        imports_complete,
    )
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    levels = _level_projections(
        target, modules, memberships, permissions, level_counts, imports_complete
    )
    scoped_unknowns = _scoped_unknowns(
        model,
        target,
        unknowns,
        names,
        modules,
        ownership,
        components,
        assessment_scopes,
    )
    return _selected_projection(
        model,
        report,
        target,
        components,
        levels,
        rules,
        relationships,
        gaps,
        scoped_unknowns,
        selected,
        violation_remedy,
    )
