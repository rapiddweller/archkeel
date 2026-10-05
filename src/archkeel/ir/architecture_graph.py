# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared source and Target graph types; no parsing, policy or layout."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, TypeAlias, get_args

from archkeel.ir.facts import Evidence

EntityKind: TypeAlias = Literal[
    "component",
    "package",
    "module",
    "class",
    "interface",
    "enum",
    "enum_literal",
    "method",
    "function",
    "attribute",
    "type_alias",
    "constant",
    "binding",
    "symbol",
]
GraphSchemaVersion: TypeAlias = Literal["1.2.0", "1.1.0", "1.0.0"]
RelationshipKind: TypeAlias = Literal[
    "imports",
    "calls",
    "references",
    "inherits",
    "realizes",
    "creates",
    "instance_of",
    "owns",
    "requires",
    "publishes",
]
VisibilityKind: TypeAlias = Literal["public", "private", "protected", "package", "unknown"]
VisibilityBasis: TypeAlias = Literal["language", "convention", "declared", "unknown"]
ParameterKind: TypeAlias = Literal[
    "positional_only", "positional", "keyword_only", "varargs", "kwargs", "unknown"
]
ModifierKind: TypeAlias = Literal["abstract", "static", "class", "async", "frozen"]
DefinitionContextKind: TypeAlias = Literal[
    "if", "for", "async_for", "while", "try", "try_star", "with", "async_with", "match"
]
DefinitionBranchKind: TypeAlias = Literal["body", "else", "handler", "finally", "case"]
CoverageStatus: TypeAlias = Literal["complete", "partial", "unavailable"]
OriginKind: TypeAlias = Literal["observed", "declared"]
PresenceKind: TypeAlias = Literal["defined", "referenced", "planned", "unspecified"]
ResolutionKind: TypeAlias = Literal["resolved", "partial", "unresolved", "not_applicable"]
CompletenessMode: TypeAlias = Literal["open", "closed"]
AssessmentStatus: TypeAlias = Literal["PASS", "FAIL", "UNKNOWN"]
AssessmentAspect: TypeAlias = Literal[
    "existence",
    "kind",
    "containment",
    "signature",
    "visibility",
    "annotation",
    "modifiers",
    "initializer",
    "relationship",
    "completeness",
]
AssessmentChange: TypeAlias = Literal[
    "matched",
    "missing",
    "unexpected",
    "changed",
    "ambiguous",
    "unavailable",
]


class ComponentRole(StrEnum):
    COMPONENT = "component"
    INTERFACE = "interface"
    CONTRACT = "contract"
    PROJECTION = "projection"
    FOUNDATION = "foundation"


@dataclass(frozen=True, slots=True)
class ComponentIntent:
    """Declared ownership and API selectors, independent of language visibility."""

    component_id: str
    role: ComponentRole
    packages: tuple[str, ...] = ()
    exact_modules: tuple[str, ...] = ()
    namespace: str | None = None
    public: tuple[str, ...] | None = None
    planned: tuple[str, ...] | None = None
    forbidden_responsibilities: tuple[str, ...] = ()
    decided_by: Literal["architect", "agent"] | None = None
    inside: str | None = None
    parent_id: str | None = None
    label: str | None = None
    layout_rule_ids: tuple[str, ...] = ()
    layer: str | None = None


@dataclass(frozen=True, slots=True)
class ContractModuleTarget:
    """One exact Python file and its intended responsibility."""

    path: str
    responsibility: str


@dataclass(frozen=True, slots=True)
class ModuleInventory:
    """An explicitly declared file inventory; an empty inventory is still declared."""

    id: str
    modules: tuple[ContractModuleTarget, ...]
    provenance: tuple[str, ...]
    component_id: str | None = None


@dataclass(frozen=True, slots=True)
class PublicAPIEntry:
    """A global contract selector; it asserts no symbol kind or language visibility."""

    id: str
    selector: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RootLayoutRule:
    """The immediate packages or modules below a root are an exact allow-list."""

    id: str
    kind: Literal["root_layout"]
    root: str
    allowed_children: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


def contract_relative_path(value: str) -> PurePosixPath | None:
    """Check a declared repository path without filesystem access."""
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        return None
    return relative


def validate_module_target(target: ContractModuleTarget) -> None:
    path: str = target.path
    relative = contract_relative_path(path)
    if (
        not path
        or relative is None
        or str(relative) != path
        or re.match(r"^[A-Za-z]:", path) is not None
        or "\x00" in path
        or relative.suffix
        not in {".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    ):
        raise ValueError("path must be a repository-relative source path")
    responsibility: str = target.responsibility
    if not responsibility.strip() or "\n" in responsibility or "\r" in responsibility:
        raise ValueError("responsibility must be one sentence on one line")


def validate_layout_rule(rule: RootLayoutRule) -> None:
    root: str = rule.root
    rationale: str = rule.rationale
    if not root.strip() or not rationale.strip():
        raise ValueError("layout needs a root and rationale")
    for index, child in enumerate(rule.allowed_children):
        if (
            len(child) <= len(root) + 1
            or child[: len(root)] != root
            or child[len(root)] != "."
            or "." in child[len(root) + 1 :]
        ):
            raise ValueError(
                f"allowed_children[{index}] must be exactly one immediate child of root"
            )


@dataclass(frozen=True, slots=True)
class Visibility:
    kind: VisibilityKind = "unknown"
    basis: VisibilityBasis = "unknown"
    spelling: str | None = None


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    annotation: str | None = None
    kind: ParameterKind = "unknown"
    default: str | None = None
    default_known: bool = False


@dataclass(frozen=True, slots=True)
class Signature:
    parameters: tuple[Parameter, ...] = ()
    returns: str | None = None


@dataclass(frozen=True, slots=True)
class DefinitionContext:
    """Recorded control flow surrounding a declaration; not runtime binding proof."""

    kind: DefinitionContextKind
    branch: DefinitionBranchKind
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        branches = {
            "if": {"body", "else"},
            "for": {"body", "else"},
            "async_for": {"body", "else"},
            "while": {"body", "else"},
            "try": {"body", "else", "handler", "finally"},
            "try_star": {"body", "else", "handler", "finally"},
            "with": {"body"},
            "async_with": {"body"},
            "match": {"case"},
        }
        if self.branch not in branches.get(self.kind, set()):
            raise ValueError("invalid definition context branch")


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    kind: EntityKind
    qualified_name: str
    language: str
    parent_id: str | None = None
    visibility: Visibility = Visibility()
    signature: Signature | None = None
    annotation: str | None = None
    modifiers: tuple[ModifierKind, ...] = ()
    presence: PresenceKind = "unspecified"
    responsibilities: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    definition_contexts: tuple[DefinitionContext, ...] = ()
    initializer: str | None = None
    file_path: str | None = None


@dataclass(frozen=True, slots=True)
class Relationship:
    id: str
    kind: RelationshipKind
    source_id: str
    target_id: str | None = None
    resolution: ResolutionKind = "not_applicable"
    candidate_ids: tuple[str, ...] = ()
    expression: str | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    candidate_count: int | None = None
    candidates_truncated: bool = False
    reason: str | None = None

    through: tuple[str, ...] = ()
    decided_by: Literal["architect", "agent"] | None = None


@dataclass(frozen=True, slots=True)
class Coverage:
    scope_id: str
    entity_kinds: tuple[EntityKind, ...] = ()
    relationship_kinds: tuple[RelationshipKind, ...] = ()
    status: CoverageStatus = "unavailable"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TargetScope:
    scope_id: str
    mode: CompletenessMode
    rationale: str
    provenance: tuple[str, ...]
    entity_kinds: tuple[EntityKind, ...] = ()
    relationship_kinds: tuple[RelationshipKind, ...] = ()


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    """Inner intent; existing component declarations remain its only component owners."""

    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    scopes: tuple[TargetScope, ...] = ()
    schema_version: GraphSchemaVersion = "1.1.0"

    def __post_init__(self) -> None:
        _validate_graph_version(self.schema_version, self.entities, self.scopes)


def _validate_graph_version(
    version: GraphSchemaVersion,
    entities: tuple[Entity, ...],
    scopes: tuple[TargetScope, ...] = (),
    coverage: tuple[Coverage, ...] = (),
) -> None:
    if version not in get_args(GraphSchemaVersion):
        raise ValueError("unsupported graph schema_version")
    if version == "1.0.0" and (
        any(entity.kind == "enum_literal" for entity in entities)
        or any("enum_literal" in item.entity_kinds for item in scopes)
        or any("enum_literal" in item.entity_kinds for item in coverage)
    ):
        raise ValueError("enum literal needs graph schema_version 1.1.0")


@dataclass(frozen=True, slots=True)
class GraphAssessment:
    id: str
    subject_id: str
    aspect: AssessmentAspect
    status: AssessmentStatus
    change: AssessmentChange
    reason: str
    observed_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EntityCorrespondence:
    target_id: str
    observed_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphComparison:
    status: AssessmentStatus
    assessments: tuple[GraphAssessment, ...] = ()
    schema_version: Literal["1.0.0"] = "1.0.0"
    correspondences: tuple[EntityCorrespondence, ...] = ()

    @staticmethod
    def from_assessments(
        assessments: tuple[GraphAssessment, ...],
        *,
        correspondences: tuple[EntityCorrespondence, ...] = (),
    ) -> GraphComparison:
        status: AssessmentStatus = (
            "FAIL"
            if any(item.status == "FAIL" for item in assessments)
            else "UNKNOWN"
            if not assessments or any(item.status == "UNKNOWN" for item in assessments)
            else "PASS"
        )
        return GraphComparison(status, assessments, correspondences=correspondences)

    def validate(self) -> None:
        identifiers = {item.id for item in self.assessments}
        if len(identifiers) != len(self.assessments):
            raise ValueError("duplicate assessment identity")
        if any(not item.id or not item.subject_id or not item.reason for item in self.assessments):
            raise ValueError("assessment needs identity, subject and reason")
        if self.status != GraphComparison.from_assessments(self.assessments).status:
            raise ValueError("comparison status differs from its assessments")
        targets = {item.target_id for item in self.correspondences}
        if len(targets) != len(self.correspondences):
            raise ValueError("duplicate correspondence target")
        for item in self.correspondences:
            if (
                not item.target_id
                or not item.observed_ids
                or any(not id for id in item.observed_ids)
            ):
                raise ValueError("correspondence needs target and observed identities")
            if len(set(item.observed_ids)) != len(item.observed_ids):
                raise ValueError("duplicate correspondence observation")


@dataclass(frozen=True, slots=True)
class ExternalDependencyScopeRule:
    """`allowed_sources` match by module prefix, `exact_sources` only the module named (AD-49)."""

    id: str
    kind: Literal["external_dependency_scope"]
    dependency: str
    allowed_sources: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    exact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArchitectureGraph:
    origin: OriginKind
    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    coverage: tuple[Coverage, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    schema_version: GraphSchemaVersion = "1.1.0"
    target_scopes: tuple[TargetScope, ...] = ()
    component_intents: tuple[ComponentIntent, ...] = ()
    module_inventories: tuple[ModuleInventory, ...] = ()
    layout_rules: tuple[RootLayoutRule, ...] = ()
    public_api: tuple[PublicAPIEntry, ...] = ()
    external_scopes: tuple[ExternalDependencyScopeRule, ...] = ()

    def validate(self) -> None:
        _validate_graph_version(
            self.schema_version, self.entities, self.target_scopes, self.coverage
        )
        if self.origin == "declared" and self.evidence:
            raise ValueError("Target does not carry observed source evidence")
        entities = {entity.id: entity for entity in self.entities}
        record_ids = [entity.id for entity in self.entities] + [
            edge.id for edge in self.relationships
        ]
        evidence_ids = {item.id for item in self.evidence}
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("duplicate graph identity")
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("duplicate evidence identity")
        self._validate_entities(entities, evidence_ids)
        component_ids = [item.component_id for item in self.component_intents]
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("duplicate component intent")
        intents = {item.component_id: item for item in self.component_intents}
        layouts = {rule.id for rule in self.layout_rules}
        assigned_layouts: set[str] = set()
        for intent in self.component_intents:
            if intent.layer is not None:
                if not isinstance(intent.layer, str) or not intent.layer.strip():
                    raise ValueError("component layer must be non-empty text")
                if self.schema_version != "1.2.0":
                    raise ValueError("component layer requires graph schema_version 1.2.0")
            owner = entities.get(intent.component_id)
            if self.origin != "declared" or owner is None or owner.kind != "component":
                raise ValueError("component intent needs a declared component")
            if set(intent.public or ()) & set(intent.planned or ()):
                raise ValueError("a component API entry cannot be public and planned")
            parent = intent.parent_id
            ancestors: set[str] = {intent.component_id}
            while parent is not None:
                if parent not in intents or parent in ancestors:
                    raise ValueError("invalid component containment")
                ancestors.add(parent)
                parent = intents[parent].parent_id
            for identity in intent.layout_rule_ids:
                if identity not in layouts or identity in assigned_layouts:
                    raise ValueError("invalid component layout reference")
                assigned_layouts.add(identity)
        self._validate_relationships(entities, evidence_ids)
        for item in self.coverage:
            if self.origin != "observed" or item.scope_id not in entities:
                raise ValueError("coverage describes an observed scope")
            if item.status != "complete" and not item.reason:
                raise ValueError("limited coverage needs a reason")
        self._validate_scopes(entities)
        self._validate_physical_intent(entities)
        self._validate_public_api()

    def _validate_public_api(self) -> None:
        if self.public_api and self.origin != "declared":
            raise ValueError("public API intent needs a declared graph")
        ids: set[str] = {entity.id for entity in self.entities} | {
            edge.id for edge in self.relationships
        }
        declarations: tuple[ModuleInventory | RootLayoutRule | ExternalDependencyScopeRule, ...] = (
            *self.module_inventories,
            *self.layout_rules,
            *self.external_scopes,
        )
        ids.update(item.id for item in declarations)
        selectors: set[str] = set()
        for entry in self.public_api:
            if not entry.id or entry.id in ids:
                raise ValueError("duplicate or empty public API identity")
            ids.add(entry.id)
            if not entry.selector.strip() or entry.selector in selectors:
                raise ValueError("duplicate or empty public API selector")
            selectors.add(entry.selector)
            self._validate_evidence((), entry.provenance, set())

    def _validate_physical_intent(self, entities: dict[str, Entity]) -> None:
        declarations: tuple[ModuleInventory | RootLayoutRule | ExternalDependencyScopeRule, ...] = (
            *self.module_inventories,
            *self.layout_rules,
            *self.external_scopes,
        )
        if declarations and self.origin != "declared":
            raise ValueError("physical intent needs a declared graph")
        ids: set[str] = {entity.id for entity in self.entities} | {
            edge.id for edge in self.relationships
        }
        for item in declarations:
            if not item.id or item.id in ids:
                raise ValueError("duplicate or empty physical intent identity")
            ids.add(item.id)
            self._validate_evidence((), item.provenance, set())
        scopes: set[str | None] = set()
        for inventory in self.module_inventories:
            if inventory.component_id in scopes:
                raise ValueError("duplicate module inventory scope")
            scopes.add(inventory.component_id)
            if inventory.component_id is not None:
                owner = entities.get(inventory.component_id)
                if owner is None or owner.kind != "component":
                    raise ValueError("module inventory needs a declared component")
            paths = [module.path for module in inventory.modules]
            if len(set(paths)) != len(paths):
                raise ValueError("duplicate module inventory path")
            for module in inventory.modules:
                validate_module_target(module)
        for rule in self.layout_rules:
            if len(set(rule.allowed_children)) != len(rule.allowed_children):
                raise ValueError("duplicate layout permission")
            validate_layout_rule(rule)

        for permission in self.external_scopes:
            dependency: str = permission.dependency
            rationale: str = permission.rationale
            if (
                permission.kind != "external_dependency_scope"
                or not dependency.strip()
                or not rationale.strip()
            ):
                raise ValueError("external permission needs a dependency and rationale")
            for sources in (permission.allowed_sources, permission.exact_sources):
                if len(set(sources)) != len(sources):
                    raise ValueError("invalid external permission scopes")
                for source in sources:
                    selector: str = source
                    if not selector.strip():
                        raise ValueError("invalid external permission scopes")
            if permission.decided_by not in {"architect", "agent"}:
                raise ValueError("invalid external permission decider")

    def _validate_entities(self, entities: dict[str, Entity], evidence_ids: set[str]) -> None:
        for entity in self.entities:
            if not entity.id or not entity.qualified_name or not entity.language:
                raise ValueError("empty entity identity")
            if entity.file_path is not None:
                relative = contract_relative_path(entity.file_path)
                if entity.kind != "module" or relative is None or str(relative) != entity.file_path:
                    raise ValueError("invalid module file path")
            if entity.kind == "component" and entity.parent_id is not None:
                raise ValueError("component containment belongs in component intent")
            if entity.parent_id is not None and entity.parent_id not in entities:
                raise ValueError("unknown lexical parent")
        for entity in self.entities:
            parent = entity.parent_id
            ancestors: set[str] = {entity.id}
            while parent is not None:
                if parent in ancestors:
                    raise ValueError("lexical containment cycle")
                ancestors.add(parent)
                parent = entities[parent].parent_id
            if entity.signature is not None and entity.kind not in {"method", "function"}:
                raise ValueError("signature on a non-operation")
            if entity.initializer is not None:
                initializer: str = entity.initializer
                if entity.kind != "binding" or not initializer.strip():
                    raise ValueError("initializer needs a binding and non-empty source syntax")
            if entity.kind == "method" and (
                entity.parent_id is None
                or entities[entity.parent_id].kind not in {"class", "interface", "enum"}
            ):
                raise ValueError("method without a classifier")
            if entity.kind == "enum_literal" and (
                entity.parent_id is None
                or entities[entity.parent_id].kind != "enum"
                or entity.modifiers
            ):
                raise ValueError("enum literal needs an enumeration parent and no modifiers")
            self._validate_evidence(entity.evidence_ids, entity.provenance, evidence_ids)
            for context in entity.definition_contexts:
                if self.origin != "observed" or entity.kind in {"package", "module", "component"}:
                    raise ValueError("definition contexts describe observed source declarations")
                self._validate_evidence(context.evidence_ids, (), evidence_ids)

    def _validate_relationships(self, entities: dict[str, Entity], evidence_ids: set[str]) -> None:
        for edge in self.relationships:
            if not edge.id or edge.source_id not in entities:
                raise ValueError("unknown relationship source")
            if edge.target_id is not None and edge.target_id not in entities:
                raise ValueError("unknown relationship target")
            if edge.kind == "requires":
                rationale: str = edge.reason or ""
                if (
                    self.origin != "declared"
                    or entities[edge.source_id].kind != "component"
                    or edge.target_id is None
                    or entities[edge.target_id].kind != "component"
                    or not rationale.strip()
                    or edge.expression is not None
                ):
                    raise ValueError(
                        "dependency permission needs declared component endpoints and rationale"
                    )
                if len(set(edge.through)) != len(edge.through):
                    raise ValueError("duplicate dependency permission selector")
                for value in edge.through:
                    selector: str = value
                    if not selector.strip():
                        raise ValueError("empty dependency permission selector")
                if edge.decided_by not in {None, "architect", "agent"}:
                    raise ValueError("invalid dependency permission decider")
            elif edge.through or edge.decided_by is not None:
                raise ValueError("permission metadata belongs on requires relationships")
            if len(set(edge.candidate_ids)) != len(edge.candidate_ids) or any(
                candidate not in entities for candidate in edge.candidate_ids
            ):
                raise ValueError("invalid relationship candidates")
            if self.origin == "declared" and (
                edge.resolution != "not_applicable"
                or edge.candidate_ids
                or edge.candidate_count is not None
                or edge.candidates_truncated
            ):
                raise ValueError("Target does not assert observed resolution")
            if edge.resolution == "resolved" and (edge.target_id is None or edge.candidate_ids):
                raise ValueError("resolved relationship needs one target")
            if edge.resolution in {"partial", "unresolved"} and edge.target_id is not None:
                raise ValueError("uncertain relationship has no confirmed target")
            if edge.resolution == "unresolved" and edge.candidate_ids:
                raise ValueError("unresolved relationship has no resolved candidates")
            if edge.candidate_count is not None and (
                isinstance(edge.candidate_count, bool)
                or edge.candidate_count < len(edge.candidate_ids)
                or edge.candidate_count < 0
            ):
                raise ValueError("invalid candidate count")
            if edge.candidates_truncated and (
                (
                    edge.candidate_count is not None
                    and edge.candidate_count <= len(edge.candidate_ids)
                )
                or edge.resolution != "partial"
            ):
                raise ValueError(
                    "truncated candidates need a partial relationship and a valid count"
                )
            if edge.target_id is None and not edge.expression:
                raise ValueError("relationship without target or expression")
            if self.origin == "declared" and edge.target_id is None:
                raise ValueError("Target relationship needs a declared endpoint")
            self._validate_evidence(edge.evidence_ids, edge.provenance, evidence_ids)

    def _validate_scopes(self, entities: dict[str, Entity]) -> None:
        seen: set[tuple[str, str]] = set()
        for scope in self.target_scopes:
            if "requires" in scope.relationship_kinds:
                raise ValueError(
                    "dependency permissions use existing Core rules, not UML completeness"
                )
            if self.origin != "declared" or scope.scope_id not in entities:
                raise ValueError("Target completeness needs a declared scope")
            rationale: str = scope.rationale
            if not rationale.strip() or not scope.provenance:
                raise ValueError("Target completeness needs rationale and provenance")
            if not scope.entity_kinds and not scope.relationship_kinds:
                raise ValueError("Target completeness needs an element or relationship kind")
            for kind in (*scope.entity_kinds, *scope.relationship_kinds):
                key = (scope.scope_id, kind)
                if key in seen:
                    raise ValueError("duplicate Target completeness kind in a scope")
                seen.add(key)
            self._validate_evidence((), scope.provenance, set())

    def _validate_evidence(
        self, references: tuple[str, ...], provenance: tuple[str, ...], known: set[str]
    ) -> None:
        if any(reference not in known for reference in references):
            raise ValueError("unknown evidence reference")
        if self.origin == "observed" and not references:
            raise ValueError("source fact needs evidence")
        if self.origin == "declared":
            if references or not provenance:
                raise ValueError("Target needs independent provenance")
            path: str
            for path in provenance:
                if not path.strip():
                    raise ValueError("Target needs independent provenance")


@dataclass(frozen=True, slots=True)
class ComponentMembership:
    """Core ownership references for navigation; not lexical containment."""

    component_id: str
    module_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportFinding:
    """A recorded Core failure or UNKNOWN; never a rendering judgement."""

    id: str
    kind: str
    title: str
    status: Literal["FAIL", "UNKNOWN"]
    rule_ids: tuple[str, ...]
    subjects: tuple[str, ...]
    graph_subject_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependencyDecisionGap:
    """An existing undecided component pair; not a Core UNKNOWN verdict."""

    source_id: str
    target_id: str
    relationship_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitectureReport:
    observed: ArchitectureGraph | None
    target: ArchitectureGraph | None
    comparison: GraphComparison | None = None
    unavailable: str | None = None
    schema_version: Literal["1.2.0", "1.0.0"] = "1.0.0"
    findings: tuple[ReportFinding, ...] = ()
    memberships: tuple[ComponentMembership, ...] = ()
    decision_gaps: tuple[DependencyDecisionGap, ...] = ()

    def validate(self) -> None:
        if self.observed is None and not self.unavailable:
            raise ValueError("missing observed graph needs an unavailable reason")
        if self.schema_version == "1.0.0" and any(
            graph is not None and graph.schema_version == "1.2.0"
            for graph in (self.observed, self.target)
        ):
            raise ValueError("graph layer vocabulary requires report schema_version 1.2.0")
        for graph, origin in ((self.observed, "observed"), (self.target, "declared")):
            if graph is not None:
                if graph.origin != origin:
                    raise ValueError(f"report needs {origin} origin")
                graph.validate()
        graphs = tuple(graph for graph in (self.observed, self.target) if graph is not None)
        subjects: set[str] = {entity.id for graph in graphs for entity in graph.entities}
        subjects.update(relationship.id for graph in graphs for relationship in graph.relationships)
        finding_ids = [item.id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("report finding identities must be unique")
        source_evidence = {item.id for item in self.observed.evidence} if self.observed else set()
        for finding in self.findings:
            if (
                not finding.id
                or not finding.kind
                or not finding.title
                or finding.status not in {"FAIL", "UNKNOWN"}
            ):
                raise ValueError("invalid recorded Core finding")
            if not set(finding.graph_subject_ids) <= subjects:
                raise ValueError("finding has an unavailable graph subject")
            if self.observed is not None and not set(finding.evidence_ids) <= source_evidence:
                raise ValueError("finding has unavailable source evidence")
        components = (
            {entity.id for entity in self.target.entities if entity.kind == "component"}
            if self.target
            else set()
        )
        modules = (
            {
                entity.id
                for entity in self.observed.entities
                if entity.kind == "module" and entity.presence == "defined"
            }
            if self.observed
            else set()
        )
        if len({item.component_id for item in self.memberships}) != len(self.memberships):
            raise ValueError("component membership identities must be unique")
        for membership in self.memberships:
            if (
                membership.component_id not in components
                or not set(membership.module_ids) <= modules
                or len(set(membership.module_ids)) != len(membership.module_ids)
            ):
                raise ValueError("membership needs recorded components and observed modules")
        gaps = {(item.source_id, item.target_id) for item in self.decision_gaps}
        if len(gaps) != len(self.decision_gaps):
            raise ValueError("duplicate dependency decision gap")
        imports = (
            {edge.id for edge in self.observed.relationships if edge.kind == "imports"}
            if self.observed
            else set()
        )
        for gap in self.decision_gaps:
            if (
                gap.source_id not in components
                or gap.target_id not in components
                or gap.source_id == gap.target_id
                or not set(gap.relationship_ids) <= imports
                or len(set(gap.relationship_ids)) != len(gap.relationship_ids)
            ):
                raise ValueError(
                    "dependency decision gap needs components and observed import sites"
                )
        self._validate_comparison()

    def _validate_comparison(self) -> None:
        if self.comparison is None:
            return
        if self.observed is None or self.target is None:
            raise ValueError("comparison needs both source and Target graphs")
        self.comparison.validate()
        targets = {entity.id for entity in self.target.entities} | {
            relationship.id for relationship in self.target.relationships
        }
        observed = {entity.id for entity in self.observed.entities} | {
            relationship.id for relationship in self.observed.relationships
        }
        evidence = {item.id for item in self.observed.evidence}
        for item in self.comparison.assessments:
            if item.subject_id not in targets or not set(item.observed_ids) <= observed:
                raise ValueError("comparison has an unavailable graph subject")
            if not set(item.evidence_ids) <= evidence:
                raise ValueError("comparison has unavailable source evidence")
        for correspondence in self.comparison.correspondences:
            if (
                correspondence.target_id not in targets
                or not set(correspondence.observed_ids) <= observed
            ):
                raise ValueError("comparison has an unavailable correspondence")
