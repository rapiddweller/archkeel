# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared source and Target graph values, control vocabulary and invariants."""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from archkeel.ir.facts import DefinitionBranchKind as DefinitionBranchKind
from archkeel.ir.facts import DefinitionContextKind as DefinitionContextKind
from archkeel.ir.facts import Evidence, JsonValue, Language, RawJson
from archkeel.ir.facts import ParameterKind as ParameterKind


class EntityKind(StrEnum):
    COMPONENT = "component"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    MIXIN = "mixin"
    ENUM_LITERAL = "enum_literal"
    METHOD = "method"
    FUNCTION = "function"
    ATTRIBUTE = "attribute"
    TYPE_ALIAS = "type_alias"
    CONSTANT = "constant"
    BINDING = "binding"
    SYMBOL = "symbol"


class GraphSchemaVersion(StrEnum):
    V1_2_0 = "1.2.0"
    V1_1_0 = "1.1.0"
    V1_0_0 = "1.0.0"


_CLASSIFIER_KINDS: frozenset[EntityKind] = frozenset(
    {EntityKind.CLASS, EntityKind.INTERFACE, EntityKind.ENUM, EntityKind.MIXIN}
)


class RelationshipKind(StrEnum):
    IMPORTS = "imports"
    CALLS = "calls"
    REFERENCES = "references"
    INHERITS = "inherits"
    REALIZES = "realizes"
    MIXES_IN = "mixes_in"
    CREATES = "creates"
    INSTANCE_OF = "instance_of"
    OWNS = "owns"
    REQUIRES = "requires"
    PUBLISHES = "publishes"


class VisibilityKind(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    PACKAGE = "package"
    UNKNOWN = "unknown"


class VisibilityBasis(StrEnum):
    LANGUAGE = "language"
    CONVENTION = "convention"
    DECLARED = "declared"
    UNKNOWN = "unknown"


class ModifierKind(StrEnum):
    ABSTRACT = "abstract"
    STATIC = "static"
    CLASS = "class"
    ASYNC = "async"
    FROZEN = "frozen"
    MIXIN = "mixin"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class OriginKind(StrEnum):
    OBSERVED = "observed"
    DECLARED = "declared"


class PresenceKind(StrEnum):
    DEFINED = "defined"
    REFERENCED = "referenced"
    PLANNED = "planned"
    UNSPECIFIED = "unspecified"


class ResolutionKind(StrEnum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class CompletenessMode(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class AssessmentStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RuleAssessmentStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DECLARATION = "DECLARATION"


class AssessmentAspect(StrEnum):
    EXISTENCE = "existence"
    KIND = "kind"
    CONTAINMENT = "containment"
    SIGNATURE = "signature"
    VISIBILITY = "visibility"
    ANNOTATION = "annotation"
    MODIFIERS = "modifiers"
    INITIALIZER = "initializer"
    RELATIONSHIP = "relationship"
    COMPLETENESS = "completeness"


class AssessmentChange(StrEnum):
    MATCHED = "matched"
    MISSING = "missing"
    UNEXPECTED = "unexpected"
    CHANGED = "changed"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class ReportSchemaVersion(StrEnum):
    V1_2_0 = "1.2.0"
    V1_0_0 = "1.0.0"


class DecisionMaker(StrEnum):
    ARCHITECT = "architect"
    AGENT = "agent"


class ArchitectureRuleKind(StrEnum):
    FORBIDDEN_DEPENDENCY = "forbidden_dependency"
    ALLOWED_DEPENDENCY = "allowed_dependency"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    EXTERNAL_DEPENDENCY_SCOPE = "external_dependency_scope"
    COMPLETE_ASSIGNMENT = "complete_assignment"
    ROOT_LAYOUT = "root_layout"
    COMPLETE_EXTERNAL_SCOPE = "complete_external_scope"
    COMPLETE_REQUIRES = "complete_requires"
    LAYER_ORDER = "layer_order"
    NO_COMPONENT_CYCLES = "no_component_cycles"
    INTERFACE_BOUNDARY = "interface_boundary"
    SIBLING_ISOLATION = "sibling_isolation"
    SYMBOL_PLACEMENT = "symbol_placement"
    BOUNDARY_TYPES = "boundary_types"


class ArchitectureDeclarationKind(StrEnum):
    COMPONENT_RESPONSIBILITY = "component_responsibility"
    INSIDE_COMPONENT_RESPONSIBILITY = "inside_component_responsibility"
    MODULE_TARGET = "module_target"
    DECLARED_PUBLIC_API = "declared_public_api"
    SPOT_OWNER = "spot_owner"
    COMPATIBILITY_MIGRATION_WORK = "compatibility_migration_work"
    UML_TARGET = "uml_target"
    ARCHITECTURE_TARGET = "architecture_target"


def parse_architecture_rule_kind(value: JsonValue | RawJson) -> ArchitectureRuleKind | None:
    """Recognize known rules without closing raw record extension tags."""
    if not isinstance(value, str):
        return None
    try:
        return ArchitectureRuleKind(value)
    except ValueError:
        return None


def parse_architecture_declaration_kind(
    value: JsonValue | RawJson,
) -> ArchitectureRuleKind | ArchitectureDeclarationKind | None:
    """Recognize authored rules and declarations while preserving unknown data."""
    kind = parse_architecture_rule_kind(value)
    if kind is not None:
        return kind
    if not isinstance(value, str):
        return None
    try:
        return ArchitectureDeclarationKind(value)
    except ValueError:
        return None


class ArchitectureRuleGrammar:
    """Normalize the shared contract rule tags at the public constructor boundary."""

    __slots__ = ()
    kind: ArchitectureRuleKind
    decided_by: DecisionMaker

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", ArchitectureRuleKind(self.kind))
        builtins.object.__setattr__(self, "decided_by", DecisionMaker(self.decided_by))


class ComponentRole(StrEnum):
    COMPONENT = "component"
    INTERFACE = "interface"
    CONTRACT = "contract"
    PROJECTION = "projection"
    FOUNDATION = "foundation"


@dataclass(frozen=True, slots=True)
class RuleAssessment:
    """One rule's evaluator-backed state for the current observation."""

    id: str
    kind: str
    status: RuleAssessmentStatus
    evaluation_proven: bool
    count: int
    undecided: int
    decided_by: str
    rationale: str
    provenance: tuple[str, ...]
    reason: str
    scope: str
    components: tuple[str, ...]

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "status", RuleAssessmentStatus(self.status))


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
    decided_by: DecisionMaker | None = None
    inside: str | None = None
    parent_id: str | None = None
    label: str | None = None
    layout_rule_ids: tuple[str, ...] = ()
    layer: str | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "role", ComponentRole(self.role))
        builtins.object.__setattr__(
            self, "decided_by", None if self.decided_by is None else DecisionMaker(self.decided_by)
        )


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
class RootLayoutRule(ArchitectureRuleGrammar):
    """The immediate packages or modules below a root are an exact allow-list."""

    id: str
    kind: Literal[ArchitectureRuleKind.ROOT_LAYOUT]
    root: str
    allowed_children: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


def contract_relative_path(value: str) -> PurePosixPath | None:
    """Check a declared repository path without filesystem access."""
    relative = PurePosixPath(value)
    if relative.is_absolute() or re.search(r"(?:^|/)\.\.(?:/|$)|\\", value):
        return None
    return relative


def _validate_module_target_path(path: str) -> None:
    relative = contract_relative_path(path)
    if (
        not path
        or relative is None
        or str(relative) != path
        or re.match(r"^[A-Za-z]:", path) is not None
        or re.search(r"\x00", path) is not None
        or re.fullmatch(r"\.(?:py|dart|tsx?|mts|cts|jsx?|mjs|cjs)", relative.suffix) is None
    ):
        raise ValueError("path must be a repository-relative source path")


def validate_module_target(target: ContractModuleTarget) -> None:
    _validate_module_target_path(target.path)
    responsibility: str = target.responsibility
    if not responsibility.strip() or re.search(r"[\r\n]", responsibility):
        raise ValueError("responsibility must be one sentence on one line")


def validate_layout_rule(rule: RootLayoutRule) -> None:
    root: str = rule.root
    rationale: str = rule.rationale
    if not root.strip() or not rationale.strip():
        raise ValueError("layout needs a root and rationale")
    for index, child in enumerate(rule.allowed_children):
        child_path: str = child
        parent, _, name = child_path.rpartition(".")
        if parent != root or not name:
            raise ValueError(
                f"allowed_children[{index}] must be exactly one immediate child of root"
            )


@dataclass(frozen=True, slots=True)
class Visibility:
    kind: VisibilityKind = VisibilityKind.UNKNOWN
    basis: VisibilityBasis = VisibilityBasis.UNKNOWN
    spelling: str | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", VisibilityKind(self.kind))
        builtins.object.__setattr__(self, "basis", VisibilityBasis(self.basis))


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    annotation: str | None = None
    kind: ParameterKind = ParameterKind.UNKNOWN
    default: str | None = None
    default_known: bool = False

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", ParameterKind(self.kind))


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
        builtins.object.__setattr__(self, "kind", DefinitionContextKind(self.kind))
        builtins.object.__setattr__(self, "branch", DefinitionBranchKind(self.branch))
        branches = {
            DefinitionContextKind.IF: {DefinitionBranchKind.BODY, DefinitionBranchKind.ELSE},
            DefinitionContextKind.FOR: {DefinitionBranchKind.BODY, DefinitionBranchKind.ELSE},
            DefinitionContextKind.ASYNC_FOR: {DefinitionBranchKind.BODY, DefinitionBranchKind.ELSE},
            DefinitionContextKind.WHILE: {DefinitionBranchKind.BODY, DefinitionBranchKind.ELSE},
            DefinitionContextKind.TRY: {
                DefinitionBranchKind.BODY,
                DefinitionBranchKind.ELSE,
                DefinitionBranchKind.HANDLER,
                DefinitionBranchKind.FINALLY,
            },
            DefinitionContextKind.TRY_STAR: {
                DefinitionBranchKind.BODY,
                DefinitionBranchKind.ELSE,
                DefinitionBranchKind.HANDLER,
                DefinitionBranchKind.FINALLY,
            },
            DefinitionContextKind.WITH: {DefinitionBranchKind.BODY},
            DefinitionContextKind.ASYNC_WITH: {DefinitionBranchKind.BODY},
            DefinitionContextKind.MATCH: {DefinitionBranchKind.CASE},
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
    presence: PresenceKind = PresenceKind.UNSPECIFIED
    responsibilities: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    definition_contexts: tuple[DefinitionContext, ...] = ()
    initializer: str | None = None
    file_path: str | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", EntityKind(self.kind))
        builtins.object.__setattr__(self, "presence", PresenceKind(self.presence))
        builtins.object.__setattr__(
            self, "modifiers", tuple(ModifierKind(item) for item in self.modifiers)
        )


@dataclass(frozen=True, slots=True)
class Relationship:
    id: str
    kind: RelationshipKind
    source_id: str
    target_id: str | None = None
    resolution: ResolutionKind = ResolutionKind.NOT_APPLICABLE
    candidate_ids: tuple[str, ...] = ()
    expression: str | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    candidate_count: int | None = None
    candidates_truncated: bool = False
    reason: str | None = None

    through: tuple[str, ...] = ()
    decided_by: DecisionMaker | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", RelationshipKind(self.kind))
        builtins.object.__setattr__(self, "resolution", ResolutionKind(self.resolution))
        builtins.object.__setattr__(
            self, "decided_by", None if self.decided_by is None else DecisionMaker(self.decided_by)
        )


@dataclass(frozen=True, slots=True)
class Coverage:
    scope_id: str
    entity_kinds: tuple[EntityKind, ...] = ()
    relationship_kinds: tuple[RelationshipKind, ...] = ()
    status: CoverageStatus = CoverageStatus.UNAVAILABLE
    reason: str | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(
            self, "entity_kinds", tuple(EntityKind(item) for item in self.entity_kinds)
        )
        builtins.object.__setattr__(
            self,
            "relationship_kinds",
            tuple(RelationshipKind(item) for item in self.relationship_kinds),
        )
        builtins.object.__setattr__(self, "status", CoverageStatus(self.status))


@dataclass(frozen=True, slots=True)
class TargetScope:
    scope_id: str
    mode: CompletenessMode
    rationale: str
    provenance: tuple[str, ...]
    entity_kinds: tuple[EntityKind, ...] = ()
    relationship_kinds: tuple[RelationshipKind, ...] = ()

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "mode", CompletenessMode(self.mode))
        builtins.object.__setattr__(
            self, "entity_kinds", tuple(EntityKind(item) for item in self.entity_kinds)
        )
        builtins.object.__setattr__(
            self,
            "relationship_kinds",
            tuple(RelationshipKind(item) for item in self.relationship_kinds),
        )


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    """Inner intent; existing component declarations remain its only component owners."""

    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    scopes: tuple[TargetScope, ...] = ()
    schema_version: GraphSchemaVersion = GraphSchemaVersion.V1_1_0

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "schema_version", GraphSchemaVersion(self.schema_version))
        _validate_graph_version(self.schema_version, self.entities, self.scopes)


def _validate_graph_version(
    version: GraphSchemaVersion,
    entities: tuple[Entity, ...],
    scopes: tuple[TargetScope, ...] = (),
    coverage: tuple[Coverage, ...] = (),
) -> None:
    if not isinstance(version, GraphSchemaVersion):
        raise ValueError("unsupported graph schema_version")
    if version == GraphSchemaVersion.V1_0_0 and (
        any(entity.kind == EntityKind.ENUM_LITERAL for entity in entities)
        or any(EntityKind.ENUM_LITERAL in item.entity_kinds for item in scopes)
        or any(EntityKind.ENUM_LITERAL in item.entity_kinds for item in coverage)
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

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "aspect", AssessmentAspect(self.aspect))
        builtins.object.__setattr__(self, "status", AssessmentStatus(self.status))
        builtins.object.__setattr__(self, "change", AssessmentChange(self.change))


@dataclass(frozen=True, slots=True)
class EntityCorrespondence:
    target_id: str
    observed_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphComparison:
    status: AssessmentStatus
    assessments: tuple[GraphAssessment, ...] = ()
    schema_version: Literal[GraphSchemaVersion.V1_0_0] = GraphSchemaVersion.V1_0_0
    correspondences: tuple[EntityCorrespondence, ...] = ()

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "status", AssessmentStatus(self.status))
        builtins.object.__setattr__(self, "schema_version", GraphSchemaVersion(self.schema_version))

    @staticmethod
    def from_assessments(
        assessments: tuple[GraphAssessment, ...],
        *,
        correspondences: tuple[EntityCorrespondence, ...] = (),
    ) -> GraphComparison:
        status: AssessmentStatus = (
            AssessmentStatus.FAIL
            if any(item.status == AssessmentStatus.FAIL for item in assessments)
            else AssessmentStatus.UNKNOWN
            if not assessments
            or any(item.status == AssessmentStatus.UNKNOWN for item in assessments)
            else AssessmentStatus.PASS
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
class ExternalDependencyScopeRule(ArchitectureRuleGrammar):
    """`allowed_sources` match by module prefix, `exact_sources` only the module named (AD-49)."""

    id: str
    kind: Literal[ArchitectureRuleKind.EXTERNAL_DEPENDENCY_SCOPE]
    dependency: str
    allowed_sources: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    exact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArchitectureGraph:
    origin: OriginKind
    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    coverage: tuple[Coverage, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    schema_version: GraphSchemaVersion = GraphSchemaVersion.V1_1_0
    target_scopes: tuple[TargetScope, ...] = ()
    component_intents: tuple[ComponentIntent, ...] = ()
    module_inventories: tuple[ModuleInventory, ...] = ()
    layout_rules: tuple[RootLayoutRule, ...] = ()
    public_api: tuple[PublicAPIEntry, ...] = ()
    external_scopes: tuple[ExternalDependencyScopeRule, ...] = ()

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "origin", OriginKind(self.origin))
        builtins.object.__setattr__(self, "schema_version", GraphSchemaVersion(self.schema_version))

    def validate(self) -> None:
        _validate_graph_version(
            self.schema_version, self.entities, self.target_scopes, self.coverage
        )
        if self.origin == OriginKind.DECLARED and self.evidence:
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
                layer: str = intent.layer
                if not isinstance(layer, str) or not layer.strip():
                    raise ValueError("component layer must be non-empty text")
                if self.schema_version != GraphSchemaVersion.V1_2_0:
                    raise ValueError("component layer requires graph schema_version 1.2.0")
            owner = entities.get(intent.component_id)
            if (
                self.origin != OriginKind.DECLARED
                or owner is None
                or owner.kind != EntityKind.COMPONENT
            ):
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
            if self.origin != OriginKind.OBSERVED or item.scope_id not in entities:
                raise ValueError("coverage describes an observed scope")
            if item.status != CoverageStatus.COMPLETE and not item.reason:
                raise ValueError("limited coverage needs a reason")
        self._validate_scopes(entities)
        self._validate_physical_intent(entities)
        self._validate_public_api()

    def _validate_public_api(self) -> None:
        if self.public_api and self.origin != OriginKind.DECLARED:
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
        if declarations and self.origin != OriginKind.DECLARED:
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
                if owner is None or owner.kind != EntityKind.COMPONENT:
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
                permission.kind != ArchitectureRuleKind.EXTERNAL_DEPENDENCY_SCOPE
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
            if permission.decided_by not in {DecisionMaker.ARCHITECT, DecisionMaker.AGENT}:
                raise ValueError("invalid external permission decider")

    def _validate_entities(self, entities: dict[str, Entity], evidence_ids: set[str]) -> None:
        planned_identities: set[tuple[str, EntityKind, str, str | None, Signature | None]] = set()
        for entity in self.entities:
            if not entity.id or not entity.qualified_name or not entity.language:
                raise ValueError("empty entity identity")
            if entity.file_path is not None:
                relative = contract_relative_path(entity.file_path)
                if (
                    entity.kind != EntityKind.MODULE
                    or relative is None
                    or str(relative) != entity.file_path
                ):
                    raise ValueError("invalid module file path")
            if entity.kind == EntityKind.COMPONENT and entity.parent_id is not None:
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
            if entity.signature is not None and entity.kind not in {
                EntityKind.METHOD,
                EntityKind.FUNCTION,
            }:
                raise ValueError("signature on a non-operation")
            if self.origin == OriginKind.DECLARED:
                if entity.presence == PresenceKind.PLANNED and entity.kind != EntityKind.COMPONENT:
                    identity = (
                        entity.qualified_name,
                        entity.kind,
                        entity.language,
                        entity.parent_id,
                        entity.signature,
                    )
                    if identity in planned_identities:
                        raise ValueError("duplicate planned entity")
                    planned_identities.add(identity)
                    if entity.kind == EntityKind.ATTRIBUTE and (
                        entity.parent_id is None
                        or entities[entity.parent_id].kind not in _CLASSIFIER_KINDS
                    ):
                        raise ValueError("planned attribute without a classifier")
                if entity.language == Language.PYTHON and entity.signature is not None:
                    names = [parameter.name for parameter in entity.signature.parameters]
                    if len(set(names)) != len(names):
                        raise ValueError("duplicate Python parameter name")
            if entity.initializer is not None:
                initializer: str = entity.initializer
                if entity.kind != EntityKind.BINDING or not initializer.strip():
                    raise ValueError("initializer needs a binding and non-empty source syntax")
            if entity.kind == EntityKind.METHOD and (
                entity.parent_id is None or entities[entity.parent_id].kind not in _CLASSIFIER_KINDS
            ):
                raise ValueError("method without a classifier")
            if entity.kind == EntityKind.ENUM_LITERAL and (
                entity.parent_id is None
                or entities[entity.parent_id].kind != EntityKind.ENUM
                or entity.modifiers
            ):
                raise ValueError("enum literal needs an enumeration parent and no modifiers")
            self._validate_evidence(entity.evidence_ids, entity.provenance, evidence_ids)
            for context in entity.definition_contexts:
                if self.origin != OriginKind.OBSERVED or entity.kind in {
                    EntityKind.PACKAGE,
                    EntityKind.MODULE,
                    EntityKind.COMPONENT,
                }:
                    raise ValueError("definition contexts describe observed source declarations")
                self._validate_evidence(context.evidence_ids, (), evidence_ids)

    def _validate_permission_metadata(
        self, edge: Relationship, entities: dict[str, Entity]
    ) -> None:
        if edge.kind == RelationshipKind.REQUIRES:
            rationale: str = edge.reason or ""
            if (
                self.origin != OriginKind.DECLARED
                or entities[edge.source_id].kind != EntityKind.COMPONENT
                or edge.target_id is None
                or entities[edge.target_id].kind != EntityKind.COMPONENT
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
            if edge.decided_by not in {None, DecisionMaker.ARCHITECT, DecisionMaker.AGENT}:
                raise ValueError("invalid dependency permission decider")
        elif edge.through or edge.decided_by is not None:
            raise ValueError("permission metadata belongs on requires relationships")

    def _validate_classifier_relationship(
        self, edge: Relationship, entities: dict[str, Entity]
    ) -> None:
        if self.origin == OriginKind.DECLARED and edge.kind in {
            RelationshipKind.INHERITS,
            RelationshipKind.REALIZES,
            RelationshipKind.MIXES_IN,
        }:
            for identity in (edge.source_id, edge.target_id):
                if identity is None:
                    continue
                endpoint = entities[identity]
                if endpoint.kind not in _CLASSIFIER_KINDS and not (
                    endpoint.kind == EntityKind.SYMBOL
                    and endpoint.presence == PresenceKind.REFERENCED
                ):
                    raise ValueError("classifier relationship needs classifier endpoints")
            if edge.kind == RelationshipKind.MIXES_IN and edge.target_id is not None:
                source = entities[edge.source_id]
                target = entities[edge.target_id]
                if source.kind not in {EntityKind.CLASS, EntityKind.ENUM} and not (
                    source.kind == EntityKind.SYMBOL and source.presence == PresenceKind.REFERENCED
                ):
                    raise ValueError("mixes_in relationship needs a class or enum source")
                if (
                    target.kind != EntityKind.MIXIN
                    and not (
                        target.kind == EntityKind.CLASS and ModifierKind.MIXIN in target.modifiers
                    )
                    and not (
                        target.kind == EntityKind.SYMBOL
                        and target.presence == PresenceKind.REFERENCED
                    )
                ):
                    raise ValueError("mixes_in relationship needs a mixin-capable target")

    def _validate_relationships(self, entities: dict[str, Entity], evidence_ids: set[str]) -> None:
        for edge in self.relationships:
            if not edge.id or edge.source_id not in entities:
                raise ValueError("unknown relationship source")
            if edge.target_id is not None and edge.target_id not in entities:
                raise ValueError("unknown relationship target")
            self._validate_classifier_relationship(edge, entities)
            self._validate_permission_metadata(edge, entities)
            if len(set(edge.candidate_ids)) != len(edge.candidate_ids) or any(
                candidate not in entities for candidate in edge.candidate_ids
            ):
                raise ValueError("invalid relationship candidates")
            if self.origin == OriginKind.DECLARED and (
                edge.resolution != ResolutionKind.NOT_APPLICABLE
                or edge.candidate_ids
                or edge.candidate_count is not None
                or edge.candidates_truncated
            ):
                raise ValueError("Target does not assert observed resolution")
            if edge.resolution == ResolutionKind.RESOLVED and (
                edge.target_id is None or edge.candidate_ids
            ):
                raise ValueError("resolved relationship needs one target")
            if (
                edge.resolution in {ResolutionKind.PARTIAL, ResolutionKind.UNRESOLVED}
                and edge.target_id is not None
            ):
                raise ValueError("uncertain relationship has no confirmed target")
            if edge.resolution == ResolutionKind.UNRESOLVED and edge.candidate_ids:
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
                or edge.resolution != ResolutionKind.PARTIAL
            ):
                raise ValueError(
                    "truncated candidates need a partial relationship and a valid count"
                )
            if edge.target_id is None and not edge.expression:
                raise ValueError("relationship without target or expression")
            if self.origin == OriginKind.DECLARED and edge.target_id is None:
                raise ValueError("Target relationship needs a declared endpoint")
            self._validate_evidence(edge.evidence_ids, edge.provenance, evidence_ids)

    def _validate_scopes(self, entities: dict[str, Entity]) -> None:
        seen: set[tuple[str, str]] = set()
        for scope in self.target_scopes:
            if RelationshipKind.REQUIRES in scope.relationship_kinds:
                raise ValueError(
                    "dependency permissions use existing Core rules, not UML completeness"
                )
            if self.origin != OriginKind.DECLARED or scope.scope_id not in entities:
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
        if self.origin == OriginKind.OBSERVED and not references:
            raise ValueError("source fact needs evidence")
        if self.origin == OriginKind.DECLARED:
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
    status: Literal[AssessmentStatus.FAIL, AssessmentStatus.UNKNOWN]
    rule_ids: tuple[str, ...]
    subjects: tuple[str, ...]
    graph_subject_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "status", AssessmentStatus(self.status))


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
    schema_version: ReportSchemaVersion = ReportSchemaVersion.V1_0_0
    findings: tuple[ReportFinding, ...] = ()
    memberships: tuple[ComponentMembership, ...] = ()
    decision_gaps: tuple[DependencyDecisionGap, ...] = ()

    def __post_init__(self) -> None:
        builtins.object.__setattr__(
            self, "schema_version", ReportSchemaVersion(self.schema_version)
        )

    def validate(self) -> None:
        if self.observed is None and not self.unavailable:
            raise ValueError("missing observed graph needs an unavailable reason")
        if self.schema_version == ReportSchemaVersion.V1_0_0 and any(
            graph is not None and graph.schema_version == GraphSchemaVersion.V1_2_0
            for graph in (self.observed, self.target)
        ):
            raise ValueError("graph layer vocabulary requires report schema_version 1.2.0")
        for graph, origin in (
            (self.observed, OriginKind.OBSERVED),
            (self.target, OriginKind.DECLARED),
        ):
            if graph is not None:
                if graph.origin != origin:
                    raise ValueError(f"report needs {origin} origin")
                graph.validate()
        graphs = tuple(graph for graph in (self.observed, self.target) if graph is not None)
        subjects: set[str] = {entity.id for graph in graphs for entity in graph.entities}
        subjects.update(relationship.id for graph in graphs for relationship in graph.relationships)
        self._validate_findings(subjects)
        components = (
            {entity.id for entity in self.target.entities if entity.kind == EntityKind.COMPONENT}
            if self.target
            else set()
        )
        modules = (
            {
                entity.id
                for entity in self.observed.entities
                if entity.kind == EntityKind.MODULE and entity.presence == PresenceKind.DEFINED
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
            {
                edge.id
                for edge in self.observed.relationships
                if edge.kind == RelationshipKind.IMPORTS
            }
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

    def _validate_findings(self, subjects: set[str]) -> None:
        finding_ids = [item.id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("report finding identities must be unique")
        source_evidence = {item.id for item in self.observed.evidence} if self.observed else set()
        for finding in self.findings:
            if (
                not finding.id
                or not finding.kind
                or not finding.title
                or finding.status not in {AssessmentStatus.FAIL, AssessmentStatus.UNKNOWN}
            ):
                raise ValueError("invalid recorded Core finding")
            if not set(finding.graph_subject_ids) <= subjects:
                raise ValueError("finding has an unavailable graph subject")
            if self.observed is not None and not set(finding.evidence_ids) <= source_evidence:
                raise ValueError("finding has unavailable source evidence")

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
