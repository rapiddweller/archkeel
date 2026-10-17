# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Prepare compact command views from authenticated architecture projections."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from archkeel.ir.architecture_graph import (
    AssessmentStatus,
    ComponentRole,
    DecisionMaker,
    RelationshipKind,
)
from archkeel.ir.architecture_projection import (
    ComponentProjection,
    LevelProjection,
    OwnershipGap,
    PermissionRuleProjection,
    PermissionStatus,
    RequiredRelationshipProjection,
    RequiresProjection,
    UnknownProjection,
)
from archkeel.ir.facts import Record, SourceInfo
from archkeel.ir.model import (
    BaselineViolationComparison,
    Coverage,
    Diagnostic,
    FilteredViolation,
    ReportFilter,
    RunResult,
)
from archkeel.ir.model import (
    Command as _Command,
)
from archkeel.ir.model import (
    ExpectationOutcome as _ExpectationOutcome,
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
    decided_by: DecisionMaker | None
    parent_id: str | None = None
    role: ComponentRole = ComponentRole.COMPONENT
    namespace: str | None = None
    selector_prefix: str | None = None
    layer: str | None = None
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
    public: tuple[str, ...] | None
    planned: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class RequiredRelationshipSummary:
    scope: str
    kind: RelationshipKind
    status: AssessmentStatus
    reasons: tuple[str, ...]
    count: int


@dataclass(frozen=True, slots=True)
class ArchitectureCommandView:
    source: SourceInfo
    contract_digest: str
    analyzer_digest: str
    components: tuple[ArchitectureComponentView, ...]
    policy_context: tuple[PermissionContextView, ...]
    levels: tuple[LevelProjection, ...]
    permission_rules: tuple[PermissionRuleProjection, ...]
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
    observation_complete: Literal[AssessmentStatus.PASS, AssessmentStatus.UNKNOWN]
    declared_rules: AssessmentStatus
    coverage: Coverage | None
    diagnostics: tuple[Diagnostic, ...]
    report_filter: ReportFilter | None
    architecture_projection: ArchitectureCommandView
    filtered_violations: tuple[FilteredViolation, ...]
    command: Literal[_Command.REPORT] = _Command.REPORT
    expectation_fulfilled: Literal[_ExpectationOutcome.NOT_APPLICABLE] = (
        _ExpectationOutcome.NOT_APPLICABLE
    )
    schema_version: Literal["1.0.0", "2.0.0"] = "1.0.0"
    baseline_path: str | None = None
    baseline_comparisons: tuple[BaselineViolationComparison, ...] | None = None
    baseline_new: int | None = None
    baseline_resolved: int | None = None
    recorded_unknowns: tuple[Record, ...] | None = None


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
        value: str = selector
        module, separator, symbol = value.partition(":")
        symbols: list[str] = modules.setdefault(short_selector(module, prefix), [])
        symbols.append(symbol if separator else "")
    return {module: tuple(symbols) for module, symbols in modules.items()}


def unknown_groups(unknowns: tuple[UnknownProjection, ...]) -> UnknownGroups:
    groups: dict[tuple[str, str], Counter[tuple[str, ...]]] = {}
    for unknown in unknowns:
        groups.setdefault((unknown.kind, unknown.reason), Counter())[unknown.scopes] += 1
    result: UnknownGroups = {}
    for (kind, reason), counts in sorted(groups.items()):
        result.setdefault(kind, {})[reason] = tuple(sorted(counts.items()))
    return result


def _reason_index(reasons: list[str], reason: str) -> int:
    if reason not in reasons:
        reasons.append(reason)
    return reasons.index(reason)


def _permission_groups(
    component: ComponentProjection,
    reasons: list[str],
) -> tuple[PermissionGroup, ...]:
    groups: dict[tuple[PermissionStatus, tuple[str, ...], str], list[str]] = {}
    requires_ids = {item.id for item in component.requires}
    for permission in component.permissions:
        rule_ids = tuple(
            identity
            for identity in permission.rule_ids
            if permission.status is not PermissionStatus.ALLOWED or identity not in requires_ids
        )
        targets: list[str] = groups.setdefault((permission.status, rule_ids, permission.reason), [])
        targets.append(permission.target_id)
    return tuple(
        PermissionGroup(status, _reason_index(reasons, reason), tuple(targets), rule_ids)
        for (status, rule_ids, reason), targets in sorted(groups.items())
    )


def _command_component(
    component: ComponentProjection,
    violation_ids: set[str],
    reasons: list[str],
) -> ArchitectureComponentView:
    prefix = component.selector_prefix
    modules = {}
    for module in component.modules:
        path: str | None = module.path
        if path is not None and component.path is not None:
            if path == component.path:
                path = ""
            elif path.startswith(f"{component.path}/"):
                path = path[len(component.path) + 1 :]
        modules[short_selector(module.name, prefix)] = path
    return ArchitectureComponentView(
        id=component.id,
        scope=component.scope,
        parent_id=component.parent_id,
        role=component.role,
        path=component.path,
        provenance=component.provenance,
        namespace=component.namespace,
        selector_prefix=prefix if prefix != component.namespace else None,
        layer=component.layer,
        packages=tuple(short_selector(item, prefix) for item in component.packages),
        exact_modules=tuple(short_selector(item, prefix) for item in component.exact_modules),
        responsibilities=component.responsibilities,
        not_responsible_for=component.not_responsible_for,
        public=grouped_selectors(component.public, prefix),
        planned=grouped_selectors(component.planned, prefix),
        modules=modules,
        requires=component.requires,
        permissions=_permission_groups(component, reasons),
        used_by={item.component_id: item.import_sites for item in component.used_by},
        finding_ids=tuple(
            identity for identity in component.finding_ids if identity in violation_ids
        ),
        status=component.status,
        reason=_reason_index(reasons, component.reason),
        decided_by=component.decided_by,
    )


def architecture_command_envelope(result: RunResult) -> ArchitectureCommandEnvelope:
    projection = result.architecture_projection
    if projection is None:
        raise ValueError("architecture command requires its authenticated projection")
    reasons: list[str] = []

    violations = result.filtered_violations or ()
    violation_ids = {item.record.id for item in violations}

    components = tuple(
        _command_component(item, violation_ids, reasons) for item in projection.components
    )
    relationships = projection.required_relationships
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
                _permission_groups(item, reasons),
                item.public,
                item.planned,
            )
            for item in projection.policy_context
        ),
        projection.levels,
        projection.permission_rules,
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
        schema_version="2.0.0"
        if result.report_filter and result.report_filter.full_architecture
        else "1.0.0",
        recorded_unknowns=result.observation.records("unknowns")
        if result.observation is not None
        else None,
        baseline_path=result.baseline_path,
        baseline_comparisons=result.baseline_comparisons,
        baseline_new=result.baseline_new,
        baseline_resolved=result.baseline_resolved,
    )
