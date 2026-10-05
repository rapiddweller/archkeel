# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compact views of authenticated architecture facts; no policy evaluation."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from .architecture_graph import AssessmentStatus, ComponentRole, RelationshipKind, RuleAssessment
from .facts import Record, SourceInfo

PermissionStatus: TypeAlias = Literal["allowed", "forbidden", "undecided"]


@dataclass(frozen=True, slots=True)
class ModuleProjection:
    name: str
    path: str | None


@dataclass(frozen=True, slots=True)
class OwnershipGap:
    module: str
    path: str | None
    candidate_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PermissionProjection:
    """Declared component-pair permission; governing rules still constrain each import."""

    target_id: str
    status: PermissionStatus
    rule_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PermissionRuleProjection:
    declaration: Record
    assessment: RuleAssessment | None
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class RequiresProjection:
    id: str
    target_id: str
    through: tuple[str, ...]
    rationale: str
    decided_by: Literal["architect", "agent"] | None
    observed_imports: int | None


@dataclass(frozen=True, slots=True)
class UsageProjection:
    component_id: str
    import_sites: int


@dataclass(frozen=True, slots=True)
class ComponentProjection:
    id: str
    scope: str
    label: str
    parent_id: str | None
    role: ComponentRole
    path: str | None
    provenance: tuple[str, ...]
    namespace: str | None
    packages: tuple[str, ...]
    exact_modules: tuple[str, ...]
    responsibilities: tuple[str, ...]
    not_responsible_for: tuple[str, ...]
    public: tuple[str, ...] | None
    planned: tuple[str, ...] | None
    modules: tuple[ModuleProjection, ...]
    requires: tuple[RequiresProjection, ...]
    permissions: tuple[PermissionProjection, ...]
    used_by: tuple[UsageProjection, ...]
    finding_ids: tuple[str, ...]
    status: AssessmentStatus
    reason: str
    decided_by: Literal["architect", "agent"] | None
    selector_prefix: str | None = None


@dataclass(frozen=True, slots=True)
class LevelProjection:
    parent_id: str | None
    component_ids: tuple[str, ...]
    declared: int
    used: int | None
    unused: int | None
    undeclared: int | None
    undecided: int
    unowned_modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequiredRelationshipProjection:
    id: str
    kind: RelationshipKind
    source_id: str
    source: str
    target_id: str | None
    target: str | None
    status: AssessmentStatus
    reasons: tuple[str, ...]
    component_ids: tuple[str, ...] = ()
    internal_scope: str | None = None


@dataclass(frozen=True, slots=True)
class UnknownProjection:
    id: str
    reason: str
    rule_ids: tuple[str, ...] = ()
    kind: str = "projection_uncertainty"
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArchitectureProjection:
    source: SourceInfo
    contract_digest: str
    analyzer_digest: str
    components: tuple[ComponentProjection, ...]
    levels: tuple[LevelProjection, ...]
    permission_rules: tuple[PermissionRuleProjection, ...]
    required_relationships: tuple[RequiredRelationshipProjection, ...]
    ownership_gaps: tuple[OwnershipGap, ...]
    unknowns: tuple[UnknownProjection, ...]
    status: AssessmentStatus
    reason: str
    violation_remedy: str
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_context: tuple[ComponentProjection, ...] = ()
