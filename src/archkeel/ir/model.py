# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical ArchitectureIR primitives and deterministic serialization."""

from __future__ import annotations

import builtins
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from .amendment import AmendmentStatus as AmendmentStatus
from .architecture_graph import ArchitectureRuleGrammar, TargetDefinition
from .architecture_graph import ArchitectureRuleKind as ArchitectureRuleKind
from .architecture_graph import AssessmentStatus as AssessmentStatus
from .architecture_graph import ComponentRole as ComponentRole
from .architecture_graph import ContractModuleTarget as ContractModuleTarget
from .architecture_graph import DecisionMaker as DecisionMaker
from .architecture_graph import ExternalDependencyScopeRule as ExternalDependencyScopeRule
from .architecture_graph import NumericOperandForm as NumericOperandForm
from .architecture_graph import ProtocolDeclarationRole as ProtocolDeclarationRole
from .architecture_graph import ProtocolDeclarationVisibility as ProtocolDeclarationVisibility
from .architecture_graph import RootLayoutRule as RootLayoutRule
from .architecture_graph import RuleAssessment as RuleAssessment
from .architecture_graph import RuleAssessmentStatus as RuleAssessmentStatus
from .architecture_graph import contract_relative_path as contract_relative_path
from .contract_version import ContractVersion as ContractVersion
from .dependency import ComponentOwnership as ComponentOwnership
from .dependency import DependencyOwner as DependencyOwner
from .dependency import DependencySelection as DependencySelection
from .dependency import DependencySelector as DependencySelector
from .dependency import DependencyTargetKind as DependencyTargetKind
from .dependency import ImportSymbolMarker as _ImportSymbolMarker
from .dependency import ModuleSelection as ModuleSelection
from .dependency import SelectorMatch as SelectorMatch
from .dependency import module_in_ownership as module_in_ownership
from .diagnostics import Diagnostic as Diagnostic
from .diagnostics import DiagnosticCode as DiagnosticCode
from .diagnostics import DiagnosticError as DiagnosticError
from .diagnostics import DiagnosticKind as DiagnosticKind
from .diagnostics import ReportLocation as ReportLocation
from .facts import (
    EVIDENCE_FIELDS as EVIDENCE_FIELDS,
)
from .facts import (
    RECORD_FIELDS as RECORD_FIELDS,
)
from .facts import (
    AnalyzerInfo as AnalyzerInfo,
)
from .facts import ConditionSelector as ConditionSelector
from .facts import ConditionSelectorKind as ConditionSelectorKind
from .facts import (
    Evidence as Evidence,
)
from .facts import (
    EvidenceClass as EvidenceClass,
)
from .facts import (
    ForbiddenConstructKind as ForbiddenConstructKind,
)
from .facts import (
    JsonValue as JsonValue,
)
from .facts import (
    Record as Record,
)
from .facts import (
    RecordData as RecordData,
)
from .facts import (
    RuntimeInfo as RuntimeInfo,
)
from .facts import (
    SourceInfo as SourceInfo,
)
from .facts import (
    SourceNameVisibility,
    SourceResolution,
    parse_source_resolution,
)
from .facts import (
    SymbolClassKind as SymbolClassKind,
)
from .facts import (
    in_scope as in_scope,
)
from .facts import (
    stable_id as stable_id,
)
from .host_records import InitialPRHeadEvidence
from .measurements import MeasurementBudgetName as MeasurementBudgetName
from .measurements import Measurements
from .measurements import NameBudgetKind as NameBudgetKind
from .source_records import source_name_visibility as _source_name_visibility

if TYPE_CHECKING:
    from .architecture_projection import ArchitectureProjection

RawJson: TypeAlias = str | int | float | bool | None | Sequence["RawJson"] | Mapping[str, "RawJson"]


def public_api_id(selector: str) -> str:
    return f"API-{hashlib.sha256(selector.encode()).hexdigest()[:16]}"


SCHEMA_VERSION = "2.9.0"
DELTA_SCHEMA_VERSION = "2.0.0"


class DeltaVersion(StrEnum):
    V1_2 = "1.2.0"
    V1_3 = "1.3.0"
    V1_4 = "1.4.0"
    V2_0 = DELTA_SCHEMA_VERSION


def supports_nullable_delta_counts(version: DeltaVersion) -> bool:
    """Nullable call/dimension counts entered the Delta wire in 1.4."""
    return version in {DeltaVersion.V1_4, DeltaVersion.V2_0}


class Command(StrEnum):
    REPORT = "report"
    VALIDATE = "validate"
    CHECK = "check"
    INIT = "init"
    SKILL = "skill"
    ARGUMENTS = "arguments"


class ExpectationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "n/a"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


PackageComponentOwnership: TypeAlias = tuple[str, tuple[str, ...]]
ComponentOwnershipInput: TypeAlias = ComponentOwnership | PackageComponentOwnership
RuleVerdict: TypeAlias = AssessmentStatus


class GraphTopologyLevel(StrEnum):
    MODULE = "module"
    PACKAGE = "package"


class ComparisonStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNKNOWN = "UNKNOWN"


CLASSIFIED_SECTIONS = (
    "metrics",
    "declarations",
    "scope_observations",
    "packages",
    "modules",
    "symbols",
    "imports",
    "dependency_edges",
    "transitive_paths",
    "path_observations",
    "cycles",
    "calls",
    "references",
    "bindings",
    "typing_signals",
    "constructs",
    "contexts",
    "context_evidence",
    "violations",
    "unknowns",
)


def identity_is_known(value: str) -> bool:
    """Equality of missing provenance cannot establish comparable observations."""
    return bool(value.strip()) and value.strip().casefold() != "unknown"


@dataclass(frozen=True, slots=True)
class ContractInfo:
    schema_version: str
    digest: str
    path: str


class ContractPathKind(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class ContractCapability:
    id: str
    name: str
    label: str
    review_order: int
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractComponent:
    id: str
    label: str
    role: ComponentRole
    packages: tuple[str, ...]
    responsibilities: tuple[str, ...]
    forbidden_responsibilities: tuple[str, ...]
    provenance: tuple[str, ...]
    capability_id: str | None = None
    requires: tuple[RequiredComponent, ...] | None = None
    # AD-20: the contract describing this component's inside, as a repository-relative path.
    # A reference to a file, never a parent or child link: the levels stay separate contracts.
    inside: str | None = None
    public: tuple[str, ...] | None = None
    # AD-56: entries not yet built, the same `pkg.module`/`pkg.module:Name` shape as `public`
    # and disjoint from it, so an entry lives in exactly one list and cannot drift between
    # "declared" and "not built yet".
    planned: tuple[str, ...] | None = None
    # AD-50: who decided this component's `public` list, and every `requires` entry that
    # names nobody of its own. None records no attribution, the way a contract read before.
    decided_by: DecisionMaker | None = None
    # The physical package where this component is expected to live. `packages` remains
    # the ownership set; modules owned by this component outside `namespace` are violations.
    namespace: str | None = None
    # Exact module ownership is separate from recursive package ownership. None preserves
    # canonical bytes for contracts that do not declare exact modules.
    exact_modules: tuple[str, ...] | None = None
    layer: str | None = None

    def __post_init__(self) -> None:
        if self.decided_by is not None:
            builtins.object.__setattr__(self, "decided_by", DecisionMaker(self.decided_by))


ModuleExports: TypeAlias = dict[str, frozenset[str] | None]


def stated_exports(all_exports: JsonValue, all_literal: JsonValue) -> frozenset[str] | None:
    """A module's stated export surface, or None when it states none (AD-244).

    The analyzer records `all_exports` empty both without `__all__` and for `__all__ = []`;
    only `all_literal` proves the second, which states an empty surface.
    """
    names = (
        frozenset(name for name in all_exports if isinstance(name, str))
        if isinstance(all_exports, tuple)
        else frozenset()
    )
    return names if names or all_literal is True else None


def module_exports(observation: Observation) -> ModuleExports:
    return {
        module: stated_exports(record.data.get("all_exports"), record.data.get("all_literal"))
        for record in observation.records("modules") or ()
        if isinstance((module := record.data.get("qualified_name")), str)
    }


def facade_covers(
    module: str,
    name: str,
    component: ContractComponent,
    exports_by_module: ModuleExports,
) -> bool:
    """Answer facade coverage from the component contract and observed module exports."""
    public = component.public
    if public is None or _source_name_visibility(name) is SourceNameVisibility.PRIVATE:
        return False
    if f"{module}:{name}" in public:
        return True
    exports = exports_by_module.get(module)
    # A star import binds exactly the stated surface, which a module entry exposes.
    return module in public and (exports is None or name == "*" or name in exports)


def interface_covers_import(
    target_module: str,
    symbol: str | None,
    reexport_chain: Iterable[str],
    component: ContractComponent,
    exports_by_module: ModuleExports,
) -> bool:
    """Match a concrete import route against a declared interface."""
    if component.public is None:
        return False
    if symbol is None:
        return target_module in component.public
    if _source_name_visibility(symbol) is SourceNameVisibility.PRIVATE:
        return False
    for entry in reexport_chain:
        module, _, name = entry.rpartition(".")
        if facade_covers(module, name, component, exports_by_module):
            return True
    return False


@dataclass(frozen=True, slots=True)
class RequiredComponent:
    """One component its owner may import, carrying the architect's reason for the edge (AD-32).

    `through` narrows the edge to module prefixes or exact module:symbol ports (AD-42,
    issue #564); empty means its whole public surface.

    `decided_by` names who decided this edge (AD-50); it overrides the component's own.
    """

    component: str
    rationale: str
    through: tuple[str, ...] = ()
    decided_by: DecisionMaker | None = None

    def __post_init__(self) -> None:
        if self.decided_by is not None:
            builtins.object.__setattr__(self, "decided_by", DecisionMaker(self.decided_by))


def requires_covers(
    source: ContractComponent | tuple[RequiredComponent, ...],
    target_label: str,
    target_module: str | None = None,
    target_symbol: str | None = None,
) -> bool:
    """Match a concrete required port; without a module, query the declared target."""
    entries = (source.requires or ()) if isinstance(source, ContractComponent) else source
    return any(
        entry.component == target_label
        and (
            target_module is None
            or not entry.through
            or any(
                _required_port_assessment(port, target_module, target_symbol, symbols_known=True)
                is AssessmentStatus.PASS
                for port in entry.through
            )
        )
        for entry in entries
    )


def _required_port_assessment(
    port: str, target_module: str, target_symbol: str | None, *, symbols_known: bool
) -> AssessmentStatus:
    # Selectors are wire text, even when an accepted str subclass overrides partition.
    module, separator, symbol = builtins.str.partition(port, ":")
    if not separator:
        return AssessmentStatus.PASS if in_scope(target_module, module) else AssessmentStatus.FAIL
    if target_module != module:
        return AssessmentStatus.FAIL
    if not symbols_known:
        return AssessmentStatus.UNKNOWN
    return AssessmentStatus.PASS if target_symbol == symbol else AssessmentStatus.FAIL


def requires_import_assessment(
    source: ContractComponent,
    target_label: str,
    target_module: str,
    symbol: str | None,
    *,
    symbols_known: bool,
) -> AssessmentStatus:
    """Judge actual import names once; a wildcard cannot prove an exact symbol port."""
    try:
        marker = _ImportSymbolMarker(symbol) if symbol is not None else None
    except ValueError:
        marker = None
    named = symbols_known and marker is None
    if requires_covers(source, target_label, target_module, symbol if named else None):
        return AssessmentStatus.PASS
    if not named and any(
        entry.component == target_label
        and any(
            _required_port_assessment(port, target_module, symbol, symbols_known=False)
            is AssessmentStatus.UNKNOWN
            for port in entry.through
        )
        for entry in source.requires or ()
    ):
        return AssessmentStatus.UNKNOWN
    return AssessmentStatus.FAIL


@dataclass(frozen=True, slots=True)
class ContractReviewScope:
    id: str
    label: str
    parent_id: str
    subjects: tuple[str, ...]
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractCommand:
    id: str
    command: str
    description: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractPath:
    id: str
    label: str
    kind: ContractPathKind
    steps: tuple[str, ...]
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractOwner:
    id: str
    label: str
    owner: str
    responsibility: str
    provenance: tuple[str, ...]


class CompatibilityLifetime(StrEnum):
    PERMANENT = "permanent"
    MIGRATION = "migration"


@dataclass(frozen=True, slots=True)
class CompatibilityShim:
    """A declared old module path kept as a logic-free import compatibility shim."""

    module: str
    target: str
    lifetime: CompatibilityLifetime

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "lifetime", CompatibilityLifetime(self.lifetime))


@dataclass(frozen=True, slots=True)
class ContractMeasurementBudget:
    name: MeasurementBudgetName
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "name", MeasurementBudgetName(self.name))


@dataclass(frozen=True, slots=True)
class FacadeBudget:
    """AD-99: the most names one component's declared facade may export."""

    component: str
    max_names: int
    provenance: tuple[str, ...]

    @property
    def subject(self) -> str:
        return self.component


@dataclass(frozen=True, slots=True)
class CouplingBudget:
    """AD-99: the most facade names `source` may import from `target`'s declared facade."""

    source: str
    target: str
    max_names: int
    provenance: tuple[str, ...]

    @property
    def subject(self) -> str:
        return f"{self.source} -> {self.target}"


@dataclass(frozen=True, slots=True)
class CallOwnerRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.CALL_OWNER]
    source: str
    target: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoundedNumericOperandRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND]
    source: str
    form: NumericOperandForm
    terminal_suffix: str
    minimum_value: int
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker

    def __post_init__(self) -> None:
        ArchitectureRuleGrammar.__post_init__(self)
        builtins.object.__setattr__(self, "form", NumericOperandForm(self.form))


@dataclass(frozen=True, slots=True)
class ForbiddenCallArgumentRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.FORBIDDEN_CALL_ARGUMENT]
    source: str
    target: str
    parameter: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


@dataclass(frozen=True, slots=True)
class CatalogArgumentRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.CATALOG_ARGUMENT]
    source: str
    target: str
    parameter: str
    catalog: str
    overlays: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    source_match: SelectorMatch = SelectorMatch.PREFIX


@dataclass(frozen=True, slots=True)
class CatalogUseRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.CATALOG_USE]
    source: str
    catalog: str
    overlays: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    member: str | None = None
    source_match: SelectorMatch = SelectorMatch.PREFIX
    target: str | None = None
    parameter: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenEffectUnderConditionRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.FORBIDDEN_EFFECT_UNDER_CONDITION]
    source: str
    target: str
    condition: ConditionSelector
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


@dataclass(frozen=True, slots=True)
class ForbiddenDependencyRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.FORBIDDEN_DEPENDENCY]
    source: str
    target: str
    include_type_checking: bool
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    target_symbol: str | None = None
    allowed_sources: tuple[str, ...] = ()
    source_match: SelectorMatch = SelectorMatch.PREFIX
    target_match: SelectorMatch = SelectorMatch.PREFIX
    target_kind: DependencyTargetKind = DependencyTargetKind.MODULE

    @property
    def selector(self) -> DependencySelector:
        return DependencySelector(
            self.source,
            self.target,
            self.target_symbol,
            self.source_match,
            self.target_match,
            self.target_kind,
        )


@dataclass(frozen=True, slots=True)
class AllowedDependencyRule(ArchitectureRuleGrammar):
    """AD-15: a decision that a component pair may depend; it adds no report violation."""

    id: str
    kind: Literal[ArchitectureRuleKind.ALLOWED_DEPENDENCY]
    source: str
    target: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


class RuleUncertaintyCause(StrEnum):
    MISSING_OWNERSHIP = "missing_ownership"
    MISSING_INTENT = "missing_intent"
    UNSUPPORTED_ANALYSIS = "unsupported_analysis"
    INCOMPLETE_EXECUTION = "incomplete_execution"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TypeIgnoreAllowance:
    """One suppression bound to its scope, source line, statement and exact tag."""

    qualified_name: str
    line: int
    statement: str
    tag: str


class ConstructSelectorRole(StrEnum):
    READ = "read"
    WRITE = "write"
    CALL = "call"
    REFLECT = "reflect"
    CONSTRUCTOR = "constructor"
    TYPE_PROBE = "type_probe"
    EQUALITY = "equality"
    MEMBERSHIP = "membership"
    MATCH = "match"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"


@dataclass(frozen=True, slots=True)
class ConstructSelector:
    """One nominal receiver/member selection with an optional literal operand."""

    receiver: str
    member: str | None
    role: ConstructSelectorRole
    literal: str | None = None


class SourceOwnershipMode(StrEnum):
    RETIRED = "retired"
    CONFINED = "confined"


class SourceOwnershipRole(StrEnum):
    DEFINITION = "definition"
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    VALUE_TRANSFER = "value_transfer"
    PARAMETER_DEFAULT = "parameter_default"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class SourceOwnershipRule(ArchitectureRuleGrammar):
    """A source-bound name, callable transfer, default, or fallback ownership constraint."""

    id: str
    kind: Literal[ArchitectureRuleKind.SOURCE_OWNERSHIP]
    source: str
    mode: SourceOwnershipMode
    roles: tuple[SourceOwnershipRole, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    symbols: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    owner: str | None = None
    value_owner: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenConstructRule(ArchitectureRuleGrammar):
    """`allowed_sources` match an owner scope by prefix, `exact_sources` only the scope named."""

    id: str
    kind: Literal[ArchitectureRuleKind.FORBIDDEN_CONSTRUCT]
    source: str
    constructs: tuple[ForbiddenConstructKind, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()
    allowed_type_ignores: tuple[TypeIgnoreAllowance, ...] = ()
    selector: ConstructSelector | None = None


@dataclass(frozen=True, slots=True)
class CompleteAssignmentRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.COMPLETE_ASSIGNMENT]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


@dataclass(frozen=True, slots=True)
class CompleteRequiresRule(ArchitectureRuleGrammar):
    """AD-32: a cross-component import no `requires` entry covers is a violation."""

    id: str
    kind: Literal[ArchitectureRuleKind.COMPLETE_REQUIRES]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    include_type_checking: bool = True


@dataclass(frozen=True, slots=True)
class LayerOrderRule(ArchitectureRuleGrammar):
    """Declared requires permissions run from outer to inner layers, or stay in one layer."""

    id: str
    kind: Literal[ArchitectureRuleKind.LAYER_ORDER]
    layers: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    components: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class CompleteExternalScopeRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.COMPLETE_EXTERNAL_SCOPE]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


class CycleLevel(StrEnum):
    COMPONENT = "component"
    MODULE = "module"


@dataclass(frozen=True, slots=True)
class NoComponentCyclesRule(ArchitectureRuleGrammar):
    """No import cycle at the declared level, among cycles touching `components` (AD-98).

    `level` None is the component level every contract before AD-98 declares, and
    `components` None is every cycle at that level: both stay absent from the canonical
    contract, so its bytes and AD-61's amendment digest do not move for existing contracts.
    """

    id: str
    kind: Literal[ArchitectureRuleKind.NO_COMPONENT_CYCLES]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    level: Literal[CycleLevel.MODULE] | None = None
    components: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        ArchitectureRuleGrammar.__post_init__(self)
        if self.level is not None:
            level = CycleLevel(self.level)
            builtins.object.__setattr__(
                self, "level", None if level is CycleLevel.COMPONENT else level
            )


@dataclass(frozen=True, slots=True)
class ModuleObjectGrant:
    """One exact caller may import one exact module object, without publishing its names."""

    source_module: str
    target_module: str


@dataclass(frozen=True, slots=True)
class InterfaceBoundaryRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.INTERFACE_BOUNDARY]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    include_type_checking: bool = True
    module_object_grants: tuple[ModuleObjectGrant, ...] | None = None


@dataclass(frozen=True, slots=True)
class SiblingIsolationRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.SIBLING_ISOLATION]
    members: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    include_type_checking: bool = True


@dataclass(frozen=True, slots=True)
class SymbolPlacementRule(ArchitectureRuleGrammar):
    """A class of a named kind below `source` must be defined in an allowed module.

    `allowed_sources` match a defining module by prefix, `exact_sources` only the module
    named (AD-49): a package root is a prefix of every module below it, so only the exact
    form scopes the root and nothing below it.
    """

    id: str
    kind: Literal[ArchitectureRuleKind.SYMBOL_PLACEMENT]
    source: str
    class_kinds: tuple[SymbolClassKind, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoundaryAliasBody:
    origin: str
    shape: str


@dataclass(frozen=True, slots=True)
class BoundaryTypeAllowance:
    """One exact signature, DTO field or opaque map-value exception."""

    qualified_name: str
    position: str
    field_path: str
    annotation: str
    container_depth: int | None = None
    mapping_depth: int | None = None
    alias_body: BoundaryAliasBody | None = None
    key_alias_body: BoundaryAliasBody | None = None
    literal_mapping_arm: str | None = None
    native_mapping: bool = False

    def __repr__(self) -> str:
        base = (
            "BoundaryTypeAllowance("
            f"qualified_name={self.qualified_name!r}, position={self.position!r}, "
            f"field_path={self.field_path!r}, annotation={self.annotation!r}, "
            f"container_depth={self.container_depth!r}"
        )
        if self.mapping_depth is not None:
            base += f", mapping_depth={self.mapping_depth!r}"
        if self.alias_body is not None:
            base += f", alias_body={self.alias_body!r}"
        if self.key_alias_body is not None:
            base += f", key_alias_body={self.key_alias_body!r}"
        if self.literal_mapping_arm is not None:
            base += f", literal_mapping_arm={self.literal_mapping_arm!r}"
        if self.native_mapping:
            base += ", native_mapping=True"
        return base + ")"


@dataclass(frozen=True, slots=True)
class BoundaryTypesRule(ArchitectureRuleGrammar):
    """A component's declared facade function below `source` takes and returns no bare
    `dict`/`object`, and no named type outside a builtin, an enum, a Pydantic model, or a type
    some component's own `public` list already declares (AD-58, amended by AD-63).

    Only a function the owning component's `public` list itself covers is inspected: the rule
    reads the contract's declared facade, not a naming convention over every non-underscore,
    module-level function. `allowed_sources` and `exact_sources` exempt an owner the way
    `forbidden_construct` exempts one (AD-49).
    """

    id: str
    kind: Literal[ArchitectureRuleKind.BOUNDARY_TYPES]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()
    allowed_positions: tuple[BoundaryTypeAllowance, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtocolDeclarationSelector:
    role: ProtocolDeclarationRole
    name: str
    visibility: ProtocolDeclarationVisibility
    optional: bool = False

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "role", ProtocolDeclarationRole(self.role))
        builtins.object.__setattr__(
            self, "visibility", ProtocolDeclarationVisibility(self.visibility)
        )


@dataclass(frozen=True, slots=True)
class ProtocolDeclarationsRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.PROTOCOL_DECLARATIONS]
    source: str
    protocol: str
    selectors: tuple[ProtocolDeclarationSelector, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker


ArchitectureRule: TypeAlias = (
    CallOwnerRule
    | BoundedNumericOperandRule
    | ForbiddenCallArgumentRule
    | CatalogArgumentRule
    | CatalogUseRule
    | ForbiddenEffectUnderConditionRule
    | ForbiddenDependencyRule
    | AllowedDependencyRule
    | ForbiddenConstructRule
    | SourceOwnershipRule
    | ExternalDependencyScopeRule
    | CompleteAssignmentRule
    | RootLayoutRule
    | CompleteExternalScopeRule
    | CompleteRequiresRule
    | LayerOrderRule
    | NoComponentCyclesRule
    | InterfaceBoundaryRule
    | SiblingIsolationRule
    | SymbolPlacementRule
    | BoundaryTypesRule
    | ProtocolDeclarationsRule
)

# Typed authoring kinds come from ArchitectureRule. Record consumers also assess UML intent.
UML_TARGET_KIND: Final = "uml_target"
ARCHITECTURE_TARGET_KIND: Final = "architecture_target"
TARGET_GRAPH_RECORD_KINDS: Final = frozenset({UML_TARGET_KIND, ARCHITECTURE_TARGET_KIND})
RULE_KINDS: Final[frozenset[ArchitectureRuleKind]] = frozenset(ArchitectureRuleKind)
RULE_RECORD_KINDS: Final = RULE_KINDS | {UML_TARGET_KIND}


# The symbol kinds that carry a signature. One set, because a record's `kind` and its
# older `symbol_category` field hold the same three values and two copies may drift apart.
FUNCTION_KINDS = frozenset({"function", "method"})


def parse_graph_topology_level(value: JsonValue | RawJson) -> GraphTopologyLevel | None:
    """Recognize the owned topology domain while leaving other record metadata opaque."""
    if not isinstance(value, str):
        return None
    try:
        return GraphTopologyLevel(value)
    except ValueError:
        return None


def text_value(value: object) -> str:
    """Read a string out of open record data, or the empty string when it is not one.

    Record payloads are open JSON (AD-2), so every derivation that reads a field needs
    this same narrowing. It lives here because `ir.model` is the declared owner of record
    shapes, and because three derivations had each written it out separately.
    """
    return value if isinstance(value, str) else ""


def int_value(value: object, *, default: int = 0) -> int:
    """Read a whole number out of open record data, or `default` when it is not one.

    `bool` is an `int` in Python, so a narrowing that forgets it turns a flag into a count
    without ever failing; two derivations had each written this out separately.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def component_owns_module(component: ContractComponent, module: str) -> bool:
    """Match one exact module or a descendant of one of the component's packages."""
    return module_in_ownership(module, component.packages, component.exact_modules or ())


def package_owners(components: Iterable[tuple[str, tuple[str, ...]]]) -> dict[str, str]:
    """Map each declared package to its owning component label, by exact match.

    Exact match only: a rule whose `source` and `target` each name a package this way
    decides (`ir.decisions`) or enforces (the analyzer's forbidden-dependency matching) the
    whole ordered component pair, every package of one component against every package of
    the other. A rule scoped to a submodule or a `target_symbol` narrows the rule instead,
    and is unaffected by this mapping.
    """
    return {package: label for label, packages in components for package in packages}


def dependency_owners(components: tuple[ComponentOwnership, ...]) -> tuple[DependencyOwner, ...]:
    """Adapt legacy ownership triples once at the model-to-policy boundary."""
    return tuple(
        DependencyOwner(identity, ModuleSelection(packages, exact_modules))
        for identity, packages, exact_modules in components
    )


def declared_package_pair(
    source: str,
    target: str,
    target_symbol: str | None,
    components: tuple[ComponentOwnership, ...],
    *,
    source_match: SelectorMatch = SelectorMatch.PREFIX,
    target_match: SelectorMatch = SelectorMatch.PREFIX,
    target_kind: DependencyTargetKind = DependencyTargetKind.MODULE,
) -> tuple[str, str] | None:
    """Compatibility facade for the owned dependency selection API."""
    selector = DependencySelector(
        source, target, target_symbol, source_match, target_match, target_kind
    )
    return selector.component_pair(dependency_owners(components))


def forbidden_dependency_scopes(
    rule: ForbiddenDependencyRule, components: tuple[ComponentOwnership, ...]
) -> DependencySelection:
    """Use the shared selector for Core subjects, receipts and import matching."""
    return rule.selector.select(dependency_owners(components))


@dataclass(frozen=True, slots=True)
class ContractDeclarations:
    capabilities: tuple[ContractCapability, ...] = ()
    review_scopes: tuple[ContractReviewScope, ...] = ()
    public_api: tuple[str, ...] = ()
    public_api_provenance: tuple[str, ...] = ()
    public_commands: tuple[ContractCommand, ...] = ()
    context_roots: tuple[str, ...] = ()
    context_roots_provenance: tuple[str, ...] = ()
    paths: tuple[ContractPath, ...] = ()
    spot_owners: tuple[ContractOwner, ...] = ()
    compat: tuple[CompatibilityShim, ...] = ()
    measurement_budgets: tuple[ContractMeasurementBudget, ...] = ()
    # AD-99: None when the contract names no such list, so its canonical bytes, and every
    # amendment digest bound to them, stay what they were before budgets existed.
    facade_budgets: tuple[FacadeBudget, ...] | None = None
    coupling_budgets: tuple[CouplingBudget, ...] | None = None
    # Optional so contracts without module targets retain their canonical bytes and digest.
    modules: tuple[ContractModuleTarget, ...] | None = None
    uml: TargetDefinition | None = None


@dataclass(frozen=True, slots=True)
class ArchitectureContract:
    schema_version: ContractVersion
    components: tuple[ContractComponent, ...]
    rules: tuple[ArchitectureRule, ...]
    schema: str | None = None
    declarations: ContractDeclarations | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "schema_version", ContractVersion(self.schema_version))

    def component_for(self, module: str) -> ContractComponent | None:
        """Return the only component owning a module; overlapping ownership owns nothing."""
        owners = [
            component for component in self.components if component_owns_module(component, module)
        ]
        return owners[0] if len(owners) == 1 else None


class ContractInputError(ValueError):
    """A contract declaration fails a semantic check and has a source location."""

    def __init__(self, pointer: str, subject: str, message: str) -> None:
        self.pointer = pointer
        self.subject = subject
        super().__init__(message)


@dataclass(frozen=True)
class InsideContractMount:
    """One explicitly mounted contract, scoped by the component that names it."""

    parent: ContractComponent
    parent_contract: ArchitectureContract
    owner_id: str
    parent_id: str
    pointer: str
    path: str
    identity: str
    contract: ArchitectureContract
    digest: str
    canonical_digest: str


@dataclass(frozen=True)
class InsideContractIssue:
    """A declared inside reference that cannot be safely mounted."""

    parent: ContractComponent
    parent_id: str
    pointer: str
    path: str
    reason: str
    input_error: ContractInputError | None = None


@dataclass(frozen=True)
class InsideContractTree:
    """One deterministic depth-first view of a root contract and all explicit insides."""

    root: ArchitectureContract
    mounts: tuple[InsideContractMount, ...]
    issues: tuple[InsideContractIssue, ...]
    paths: tuple[str, ...]
    digest: str
    comparison_digest: str
    comparison_contract: ArchitectureContract


def last_name(name: str) -> str:
    """The segment after a name's last `.` or `:`: what a moved module or symbol keeps."""
    symbol: str = name.rpartition(":")[2]
    return symbol.rpartition(".")[2]


@dataclass(frozen=True, slots=True)
class ModuleReference:
    """One contract field that names a module, a module prefix or a `module:Name` symbol.

    `pointer` is the field's JSON pointer into `ir.codec.contract_bytes`' document. `held` says
    whether `validate` holds the name to the scan namespace (`reference.namespace`); a command, a
    path step or a shim may name something outside it, and a rename rewrites them all (AD-105).
    """

    pointer: str
    value: str
    held: bool


def _references(
    pointer: str, named: list[tuple[str, tuple[str, ...], bool]]
) -> list[ModuleReference]:
    """Each value of the `named` fields, a scalar field given as a one-item tuple."""
    return [
        ModuleReference(
            f"{pointer}/{field}" if field in _SCALAR_FIELDS else f"{pointer}/{field}/{item}",
            value,
            held,
        )
        for field, values, held in named
        for item, value in enumerate(values)
    ]


# The fields that hold one name rather than a list of them.
_SCALAR_FIELDS: Final = frozenset(
    {"source", "target", "catalog", "root", "namespace", "command", "owner"}
)


def _boundary_allowance_references(
    index: int, allowances: tuple[BoundaryTypeAllowance, ...]
) -> list[ModuleReference]:
    references: list[ModuleReference] = []
    references += [
        ModuleReference(
            f"/rules/{index}/allowed_positions/{item}/qualified_name",
            allowance.qualified_name,
            False,
        )
        for item, allowance in enumerate(allowances)
    ]
    references += [
        ModuleReference(
            f"/rules/{index}/allowed_positions/{item}/alias_body/origin",
            allowance.alias_body.origin,
            False,
        )
        for item, allowance in enumerate(allowances)
        if allowance.alias_body is not None
    ]
    references += [
        ModuleReference(
            f"/rules/{index}/allowed_positions/{item}/key_alias_body/origin",
            allowance.key_alias_body.origin,
            False,
        )
        for item, allowance in enumerate(allowances)
        if allowance.key_alias_body is not None
    ]
    return references


def _call_owner_references(index: int, rule: CallOwnerRule) -> list[ModuleReference]:
    return _references(
        f"/rules/{index}",
        [
            ("source", (rule.source,), True),
            ("target", (rule.target,), False),
            ("allowed_sources", rule.allowed_sources, True),
            ("exact_sources", rule.exact_sources, True),
        ],
    )


def _module_object_grant_references(
    index: int, rule: InterfaceBoundaryRule
) -> list[ModuleReference]:
    return [
        ModuleReference(f"/rules/{index}/module_object_grants/{item}/{field}", value, True)
        for item, grant in enumerate(rule.module_object_grants or ())
        for field, value in (
            ("source_module", grant.source_module),
            ("target_module", grant.target_module),
        )
    ]


def _catalog_references(
    index: int, rule: CatalogArgumentRule | CatalogUseRule
) -> list[ModuleReference]:
    named = [
        ("source", (rule.source,), True),
        ("catalog", (rule.catalog,), True),
        ("overlays", rule.overlays, True),
    ]
    if isinstance(rule, CatalogArgumentRule):
        named.insert(1, ("target", (rule.target,), True))
    elif rule.target is not None:
        named.insert(1, ("target", (rule.target,), True))
    return _references(f"/rules/{index}", named)


def _rule_references(
    index: int, rule: ArchitectureRule, external: frozenset[str]
) -> list[ModuleReference]:
    """One rule's fields that name a module, a module prefix or a qualified symbol."""
    if isinstance(rule, CallOwnerRule):
        return _call_owner_references(index, rule)
    if isinstance(rule, ForbiddenCallArgumentRule):
        return _references(
            f"/rules/{index}",
            [("source", (rule.source,), True), ("target", (rule.target,), False)],
        )
    if isinstance(rule, CatalogArgumentRule | CatalogUseRule):
        return _catalog_references(index, rule)
    return _generic_rule_references(index, rule, external)


def _generic_rule_references(
    index: int, rule: ArchitectureRule, external: frozenset[str]
) -> list[ModuleReference]:
    special = _special_rule_references(index, rule)
    if special is not None:
        return special
    named: list[tuple[str, tuple[str, ...], bool]] = []
    if isinstance(
        rule,
        ForbiddenDependencyRule
        | AllowedDependencyRule
        | ForbiddenConstructRule
        | BoundedNumericOperandRule
        | SourceOwnershipRule
        | CompleteAssignmentRule
        | CompleteExternalScopeRule
        | SymbolPlacementRule
        | BoundaryTypesRule
        | ProtocolDeclarationsRule,
    ):
        named += [("source", (rule.source,), True)]
    if isinstance(rule, AllowedDependencyRule):
        named += [("target", (rule.target,), True)]
    if isinstance(rule, ForbiddenDependencyRule):
        # AD-97: a forbidden SDK library (`dart.io`) is a real target outside the namespace.
        named += [
            (
                "target",
                (rule.target,),
                rule.target not in external and rule.target_kind is DependencyTargetKind.MODULE,
            )
        ]
    if isinstance(
        rule,
        ForbiddenDependencyRule
        | ExternalDependencyScopeRule
        | SymbolPlacementRule
        | BoundaryTypesRule,
    ):
        named += [("allowed_sources", rule.allowed_sources, True)]
    if isinstance(rule, ExternalDependencyScopeRule | SymbolPlacementRule | BoundaryTypesRule):
        named += [("exact_sources", rule.exact_sources, True)]
    if isinstance(rule, SourceOwnershipRule):
        return _source_ownership_references(index, rule, named)
    if isinstance(rule, ForbiddenConstructRule):
        named += [
            ("allowed_sources", rule.allowed_sources, False),
            ("exact_sources", rule.exact_sources, False),
        ]
    if isinstance(rule, SiblingIsolationRule):
        named += [("members", rule.members, True)]
    if isinstance(rule, RootLayoutRule):
        named += [
            ("root", (rule.root,), False),
            ("allowed_children", rule.allowed_children, False),
        ]
    references = _references(f"/rules/{index}", named)
    if isinstance(rule, InterfaceBoundaryRule):
        references += _module_object_grant_references(index, rule)
    if isinstance(rule, BoundaryTypesRule):
        references += _boundary_allowance_references(index, rule.allowed_positions)
    if isinstance(rule, ProtocolDeclarationsRule):
        references += [ModuleReference(f"/rules/{index}/protocol", rule.protocol, True)]
    if isinstance(rule, ForbiddenConstructRule):
        references += [
            ModuleReference(
                f"/rules/{index}/allowed_type_ignores/{item}/qualified_name",
                allowance.qualified_name,
                False,
            )
            for item, allowance in enumerate(rule.allowed_type_ignores)
        ]
    return references


def _source_ownership_references(
    index: int, rule: SourceOwnershipRule, named: list[tuple[str, tuple[str, ...], bool]]
) -> list[ModuleReference]:
    if rule.owner is not None:
        named.append(("owner", (rule.owner,), True))
    references = _references(f"/rules/{index}", named)
    for field, values in (("symbols", rule.symbols), ("parameters", rule.parameters)):
        references.extend(
            ModuleReference(f"/rules/{index}/{field}/{position}", value, False)
            for position, value in enumerate(values)
        )
    if rule.value_owner is not None:
        value_owner: str = rule.value_owner
        references.append(ModuleReference(f"/rules/{index}/value_owner", value_owner, False))
    return references


def _special_rule_references(index: int, rule: ArchitectureRule) -> list[ModuleReference] | None:
    if isinstance(rule, CallOwnerRule):
        return _call_owner_references(index, rule)
    if isinstance(rule, ForbiddenCallArgumentRule):
        return _references(
            f"/rules/{index}",
            [("source", (rule.source,), True), ("target", (rule.target,), False)],
        )
    if isinstance(rule, ForbiddenEffectUnderConditionRule):
        references: list[ModuleReference] = _references(
            f"/rules/{index}",
            [("source", (rule.source,), True), ("target", (rule.target,), False)],
        )
        references.append(
            ModuleReference(f"/rules/{index}/condition/owner", rule.condition.owner, False)
        )
        return references
    return None


def module_references(
    contract: ArchitectureContract, *, external: frozenset[str] = frozenset()
) -> tuple[ModuleReference, ...]:
    """Every contract field that names a module, a module prefix or a `module:Name` symbol.

    This is the one list (AD-105): a recognised rename rewrites exactly these, never an id,
    label, kind or other value, and `validate` holds the entries marked `held` to the scan
    namespace. A `forbidden_dependency` target in `external`, an SDK library outside every
    namespace (AD-97), is not held.
    """
    declarations = contract.declarations or ContractDeclarations()
    references: list[ModuleReference] = []
    for index, component in enumerate(contract.components):
        references += _references(
            f"/components/{index}",
            [
                ("packages", component.packages, True),
                ("exact_modules", component.exact_modules or (), True),
                ("public", component.public or (), True),
                ("planned", component.planned or (), True),
                ("namespace", () if component.namespace is None else (component.namespace,), False),
            ],
        )
        references += [
            ModuleReference(f"/components/{index}/requires/{position}/through/{item}", value, True)
            for position, entry in enumerate(component.requires or ())
            for item, value in enumerate(entry.through)
        ]
    for index, rule in enumerate(contract.rules):
        references += _rule_references(index, rule, external)
    references += _references(
        "/declarations",
        [
            ("public_api", declarations.public_api, True),
            ("context_roots", declarations.context_roots, True),
        ],
    )
    for index, scope in enumerate(declarations.review_scopes):
        references += _references(
            f"/declarations/review_scopes/{index}", [("subjects", scope.subjects, True)]
        )
    for index, path in enumerate(declarations.paths):
        references += _references(f"/declarations/paths/{index}", [("steps", path.steps, False)])
    for index, command in enumerate(declarations.public_commands):
        references += _references(
            f"/declarations/public_commands/{index}", [("command", (command.command,), False)]
        )
    for index, owner in enumerate(declarations.spot_owners):
        references += _references(
            f"/declarations/spot_owners/{index}", [("owner", (owner.owner,), True)]
        )
    for index, shim in enumerate(declarations.compat):
        references += [
            ModuleReference(f"/declarations/compat/{index}/module", shim.module, False),
            ModuleReference(f"/declarations/compat/{index}/target", shim.target, False),
        ]
    if declarations.uml is not None:
        references += [
            ModuleReference(
                f"/declarations/uml/entities/{index}/qualified_name",
                entity.qualified_name,
                entity.presence != "referenced",
            )
            for index, entity in enumerate(declarations.uml.entities)
        ]
    return tuple(references)


@dataclass(frozen=True, slots=True)
class Coverage:
    status: Verdict
    files_discovered: int
    files_read: int
    files_parsed: int
    calls_analyzed: int | None
    calls_resolved: int | None
    calls_partially_resolved: int | None
    calls_unresolved: int | None
    ast_coverage_percent: float
    call_resolution_percent: float | None
    failures: tuple[Record, ...]
    rules: Verdict | None = None


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    records: tuple[Record, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    schema_version: str
    analyzer: AnalyzerInfo
    source: SourceInfo
    contract: ContractInfo
    coverage: Coverage
    sections: tuple[Section, ...]
    evidence: tuple[Evidence, ...]
    python_version: str | None = None
    runtime: RuntimeInfo | None = None
    producer: AnalyzerInfo | None = None

    def records(self, section: str) -> tuple[Record, ...] | None:
        return next((item.records for item in self.sections if item.name == section), None)


@dataclass(frozen=True, slots=True)
class WideningFinding:
    code: Literal["ir.widening"]
    subject: str
    field: str


class ContractChangeDirection(StrEnum):
    WIDENED = "widened"
    NARROWED = "narrowed"


@dataclass(frozen=True, slots=True)
class ContractChange:
    """One semantic contract change since `--against`, amended or not (AD-255)."""

    direction: ContractChangeDirection
    subject: str
    field: str
    message: str


class UmlEligibility(StrEnum):
    BLOCKED = "blocked"
    VALIDATED_PARTIAL_SOURCE = "validated_partial_source"
    AUTHENTICATED_PARTIAL = "authenticated_partial"


@dataclass(frozen=True, slots=True)
class ObservationResult:
    observation: Observation | None
    coverage: Coverage | None
    diagnostics: tuple[Diagnostic, ...]
    uml_eligibility: UmlEligibility = UmlEligibility.BLOCKED
    partial_uml_diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.observation is not None and self.observation.coverage != self.coverage:
            raise ValueError("analyzer coverage differs from its observation")
        if (
            self.observation is None
            or self.coverage is None
            or self.coverage.status != Verdict.PASS
        ) and not self.diagnostics:
            raise ValueError("incomplete observation requires a diagnostic")

    @property
    def exit_code(self) -> Literal[0, 2]:
        return 2 if self.diagnostics else 0


@dataclass(frozen=True, slots=True)
class Projection:
    id: str
    evidence_class: str
    area: str
    kind: str
    title: str
    subjects: tuple[str, ...]
    data: RecordData
    evidence: tuple[Evidence, ...]


class KnownSemanticChangeKind(StrEnum):
    """Actions understood by current Delta production and governance, not an open wire schema."""

    ADDED = "added"
    REMOVED = "removed"
    RELOCATED = "relocated"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class SemanticChange:
    dimension: str
    change: str
    fingerprint: str
    before_count: int
    after_count: int
    before: Projection | None
    after: Projection | None
    before_fingerprints: tuple[str, ...] | None = None
    after_fingerprints: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class DimensionDelta:
    name: str
    status: ComparisonStatus
    before_count: int | None
    after_count: int | None
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    relocated: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ComparisonStatus):
            builtins.object.__setattr__(self, "status", ComparisonStatus(self.status))


@dataclass(frozen=True, slots=True)
class DeltaProvenance:
    checker_digest: str
    analyzer_digest: str
    contract_digest: str
    baseline_digest: str
    head_digest: str


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    git_head: str
    source_digest: str
    coverage_status: Verdict
    python_version: str | None = None
    runtime: RuntimeInfo | None = None
    producer: AnalyzerInfo | None = None


@dataclass(frozen=True, slots=True)
class DeltaCoverage:
    status: Verdict
    baseline_status: Verdict
    head_status: Verdict
    supported_dimensions: tuple[str, ...]
    unknown_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeltaUnknown:
    id: str
    dimension: str
    reason: str
    evidence_class: Literal["UNKNOWN"] = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RatchetObservations:
    status: ComparisonStatus
    baseline: Measurements | None = None
    head: Measurements | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ComparisonStatus):
            builtins.object.__setattr__(self, "status", ComparisonStatus(self.status))
        measured = (self.baseline is not None, self.head is not None)
        if measured != (
            (True, True) if self.status is ComparisonStatus.SUPPORTED else (False, False)
        ):
            raise ValueError("measurements exist exactly when regression checks are SUPPORTED")


@dataclass(frozen=True, slots=True)
class ArchitectureDelta:
    schema_version: DeltaVersion
    analyzer: AnalyzerInfo
    provenance: DeltaProvenance
    baseline: SnapshotSummary
    head: SnapshotSummary
    contract: ContractInfo
    coverage: DeltaCoverage
    dimensions: tuple[DimensionDelta, ...]
    ratchets: RatchetObservations
    semantic_changes: tuple[SemanticChange, ...]
    unknowns: tuple[DeltaUnknown, ...]

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "schema_version", DeltaVersion(self.schema_version))


@dataclass(frozen=True, slots=True)
class CheckProvenance:
    baseline: str
    expectation: str
    head: str
    accepted_digest: str
    expected_digest: str
    initial_pr: InitialPRHeadEvidence | None = None


@dataclass(frozen=True, slots=True)
class OpenDecision:
    """AD-15: one ordered component pair neither allowed nor forbidden by the contract.

    `forbidden_option` and `allowed_option` are the exact rules `init --json` and
    `validate --json` offer for this pair; only their `rationale` still needs the
    architect's words.
    """

    source: str
    target: str
    source_package: str | None
    target_package: str | None
    observed: bool
    import_sites: int
    forbidden_option: ForbiddenDependencyRule | None
    allowed_option: AllowedDependencyRule | None
    source_packages: tuple[str, ...] = ()
    target_packages: tuple[str, ...] = ()
    source_exact_modules: tuple[str, ...] = ()
    target_exact_modules: tuple[str, ...] = ()
    options_unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DraftedComponentSize:
    """One drafted component's measured size, so a per-child draft carries what it hides.

    `label` matches a component `init` proposed; `modules` and `inner_edges` come from the
    same aggregation a declared component's size uses (AD-38), applied to the draft grouping
    before any component exists. Defined here, not in `ir.structure`, so `RunResult` names no
    type from a module that in turn depends on this one.
    """

    label: str
    modules: int
    inner_edges: int


@dataclass(frozen=True, slots=True)
class ReviewClaims:
    """How many candidates each review claim named, or None where its signal was missing.

    Counts only (AD-35). A claim that could not be derived is None rather than zero, because
    "nothing found" and "nothing looked at" are different answers (AD-5).
    """

    unreferenced_symbols: int | None
    oversized_components: int | None
    unread_bindings: int | None
    repeated_logic: int | None
    type_fanin: int | None


class FindingKind(StrEnum):
    """What a ranked finding is; the declaration order is the rank order (AD-258)."""

    VIOLATION = "violation"
    MODULE_CYCLE = "module_cycle"
    PACKAGE_CYCLE = "package_cycle"
    FAN_IN_HUB = "fan_in_hub"
    FAN_OUT_HUB = "fan_out_hub"


@dataclass(frozen=True, slots=True)
class CyclePathStep:
    """One edge a cycle's path crosses; `location` is the first import site that makes it.

    `type_checking_only` is true when every import of the edge sits under TYPE_CHECKING, which
    marks the edge as the cheapest one to remove.
    """

    source: str
    target: str
    location: ReportLocation | None
    type_checking_only: bool


@dataclass(frozen=True, slots=True)
class CyclePath:
    """The shortest closed walk through a cycle; `omitted_edges` counts the edges off it."""

    steps: tuple[CyclePathStep, ...]
    omitted_edges: int


@dataclass(frozen=True, slots=True)
class Finding:
    """One ranked finding the report opens with; terminal, HTML and JSON all read this list.

    Identity is `kind` plus `canonical_fingerprint(rules, subjects)` (AD-52, AD-106). `size` is
    the kind's own measure: occurrences, internal import edges or the hub's fan count.
    `change` and `before` stay None until a comparison fills them, so absence never reads
    as "new" (AD-130).
    """

    kind: FindingKind
    rules: tuple[str, ...]
    subjects: tuple[str, ...]
    size: int
    title: str
    sentence: str
    locations: tuple[ReportLocation, ...]
    component_ids: tuple[str, ...]
    change: Literal["known", "new", "reduced", "resolved"] | None = None
    before: int | None = None
    path: CyclePath | None = None


@dataclass(frozen=True, slots=True)
class ViolationCounts:
    """How many violations each rule and each crossed component pair holds (AD-51).

    Both are derived from one observation's violation records, so a time series built from
    `report --json` and the records themselves can never disagree.
    """

    by_rule: tuple[tuple[str, int], ...]
    by_component_pair: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class InterfaceBudgetResult:
    """AD-99: one declared facade or pair budget, as `validate` measured it.

    `pointer` is the declaring contract entry, `max_names` its target and `over_target` the
    known distance to it.
    `new_names` and `removed_names` compare with the baseline's accepted names, and are None
    when the run had no baseline. `uncounted` names the imports or modules that keep `names`
    a lower bound.
    """

    budget: NameBudgetKind
    subject: str
    pointer: str
    max_names: int
    count: int
    over_target: int
    names: tuple[str, ...]
    uncounted: tuple[str, ...]
    new_names: tuple[str, ...] | None = None
    removed_names: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "budget", NameBudgetKind(self.budget))


@dataclass(frozen=True, slots=True)
class ReportFilter:
    """A render-time projection of one report's violations, never a second observation (AD-60).

    `only_violations` and the `rule`/`component` facets narrow which violation records a
    rendered report shows; `architecture.json`, `declared_rules` and the exit code stay
    computed from every violation regardless, so a filtered run judges exactly what an
    unfiltered one would. `rule` matches a fingerprint's rule id exactly, top-level or the
    `<component>:<rule id>` an inside declares (AD-36); `component` matches either side of an
    import violation's crossing, source or target, since a filter narrowing to one area wants
    every violation touching it either way.
    """

    only_violations: bool = False
    rule: str | None = None
    component: str | None = None
    # AD-100: list the unresolved and partially resolved calls instead of the violations.
    only_calls: bool = False
    only_architecture: bool = False
    full_architecture: bool = False


@dataclass(frozen=True, slots=True)
class FilteredViolation:
    """Command projection; source locations never enter canonical violation records."""

    record: Record
    locations: tuple[ReportLocation, ...]


@dataclass(frozen=True, slots=True)
class BaselineViolationComparison:
    """Fingerprint-level counts preserve ambiguity between repeated findings."""

    rules: tuple[str, ...]
    subjects: tuple[str, ...]
    known_count: int
    shared_count: int
    current_count: int
    new_count: int
    resolved_count: int
    status: Literal["known", "new", "reduced", "resolved", "contracted", "unknown"]


CallStatus: TypeAlias = Literal[SourceResolution.UNRESOLVED, SourceResolution.PARTIALLY_RESOLVED]


@dataclass(frozen=True, slots=True)
class CallRow:
    """AD-100: one call the analyzer could not resolve to exactly one target.

    Read from the observation's own `calls` record and its evidence line. `component` owns the
    calling module, None when no component or several claim it.
    """

    status: CallStatus
    caller: str
    expression: str
    reason: str
    component: str | None
    path: str
    line: int

    def __post_init__(self) -> None:
        status = parse_source_resolution(self.status)
        if status not in {
            SourceResolution.UNRESOLVED,
            SourceResolution.PARTIALLY_RESOLVED,
        }:
            raise ValueError("call row needs an unresolved or partially resolved status")
        builtins.object.__setattr__(self, "status", status)


CallChangeKind: TypeAlias = Literal[KnownSemanticChangeKind.ADDED, KnownSemanticChangeKind.REMOVED]


@dataclass(frozen=True, slots=True)
class UnresolvedCallChange:
    """AD-100: one unresolved call whose count differs between two compared revisions.

    Its identity is the file, the calling scope and the call expression, never the line, so
    code that only moves is no change. Identical expressions in one caller share that identity
    and differ by count; `lines` then names every line of it on the side holding more, because
    which one is new cannot be decided. A removed call's lines are those of the older revision.
    """

    change: CallChangeKind
    caller: str
    expression: str
    reason: str
    component: str | None
    path: str
    lines: tuple[int, ...]
    before: int
    after: int

    def __post_init__(self) -> None:
        change = KnownSemanticChangeKind(self.change)
        if change not in {KnownSemanticChangeKind.ADDED, KnownSemanticChangeKind.REMOVED}:
            raise ValueError("call change needs an added or removed direction")
        builtins.object.__setattr__(self, "change", change)


@dataclass(frozen=True, slots=True)
class RunResult:
    command: Command
    exit_code: Literal[0, 1, 2]
    observation_complete: Literal[AssessmentStatus.PASS, AssessmentStatus.UNKNOWN] = (
        AssessmentStatus.UNKNOWN
    )
    declared_rules: AssessmentStatus = AssessmentStatus.UNKNOWN
    expectation_fulfilled: ExpectationOutcome = ExpectationOutcome.UNKNOWN
    diagnostics: tuple[Diagnostic, ...] = ()
    coverage: Coverage | None = None
    observation: Observation | None = None
    python_version: str | None = None
    measurements: Measurements | None = None
    artifact: str | None = None
    git_predicate: Verdict | None = None
    host_order: Verdict | None = None
    host_source: str | None = None
    failures: tuple[str, ...] = ()
    # Present as null without --against; otherwise only unamended/rejected changes.
    widenings: tuple[WideningFinding, ...] | None = None
    # AD-255: every contract change with its direction; null without --against.
    contract_changes: tuple[ContractChange, ...] | None = None
    amendment_status: AmendmentStatus | None = None
    # AD-77: baseline drift is reported as deterministic fingerprint counts.
    baseline_new: int | None = None
    baseline_resolved: int | None = None
    delta: ArchitectureDelta | None = None
    provenance: CheckProvenance | None = None
    open_decisions: tuple[OpenDecision, ...] = ()
    # When set, count is exact and completeness is true iff every counted pair is listed.
    # Both default to None for legacy results that do not report these fields.
    open_decision_count: int | None = None
    open_decisions_complete: bool | None = None
    # AD-16: (agent-decided rules, total rules), from `ir.decisions.agent_decisions`.
    agent_decisions: tuple[int, int] | None = None
    # AD-35: review-claim counts, from `ir.decisions.review_claims`.
    claims: ReviewClaims | None = None
    # AD-51: the same violations grouped, from `ir.decisions.violation_counts`.
    violations_by_rule: tuple[tuple[str, int], ...] | None = None
    violations_by_component_pair: tuple[tuple[str, str, int], ...] | None = None
    # AD-38: `init`'s own drafted components with their measured size, from `draft_contract`.
    draft_sizes: tuple[DraftedComponentSize, ...] | None = None
    # AD-60: the filter behind a rendered `report`, or None when it shows every violation.
    report_filter: ReportFilter | None = None
    # AD-60: the violation records `report_filter` selects, the same ones the HTML table
    # shows; None whenever no filter was given, so an unfiltered result's shape is unchanged.
    filtered_violations: tuple[FilteredViolation, ...] | None = None
    # AD-100: the call sites behind a calls_unresolved change; None when no two revisions'
    # calls were compared.
    unresolved_call_changes: tuple[UnresolvedCallChange, ...] | None = None
    # AD-100: why a run that compared calls names no call site; None when it names them or
    # compared none.
    unresolved_call_note: str | None = None
    # AD-100: `report --only calls`, every unresolved and partially resolved call it selects.
    filtered_calls: tuple[CallRow, ...] | None = None
    architecture_projection: ArchitectureProjection | None = None
    rule_assessments: tuple[RuleAssessment, ...] | None = None
    baseline_path: str | None = None
    baseline_comparisons: tuple[BaselineViolationComparison, ...] | None = None
    # AD-99: every declared facade and pair budget `validate` measured; None when none exists.
    interface_budgets: tuple[InterfaceBudgetResult, ...] | None = None
    # AD-101: the scan.roots a report, validate or check run read. A verdict covers these and
    # no source beside them, such as a test tree another configuration governs.
    scan_roots: tuple[str, ...] | None = None
    # AD-105: each package prefix `validate --against` found renamed, old name first; empty when
    # the compared revision renamed nothing, None when the run compared no revision.
    renames: tuple[tuple[str, str], ...] | None = None
    # AD-258: the ranked findings a report opens with, from `ir.findings.findings`; None where
    # no report computed them, so an absent list never reads as "no findings".
    findings: tuple[Finding, ...] | None = None

    def __post_init__(self) -> None:
        if self.amendment_status is not None:
            builtins.object.__setattr__(
                self, "amendment_status", AmendmentStatus(self.amendment_status)
            )
        if self.exit_code == 2 and not self.diagnostics:
            raise ValueError("exit 2 requires at least one Diagnostic")
        if self.diagnostics and self.exit_code != 2:
            raise ValueError("diagnostics require exit 2")
        completion = AssessmentStatus(self.observation_complete)
        if completion not in {AssessmentStatus.PASS, AssessmentStatus.UNKNOWN}:
            raise ValueError("observation_complete must be PASS or UNKNOWN")
        builtins.object.__setattr__(self, "command", Command(self.command))
        builtins.object.__setattr__(self, "observation_complete", completion)
        builtins.object.__setattr__(self, "declared_rules", AssessmentStatus(self.declared_rules))
        builtins.object.__setattr__(
            self, "expectation_fulfilled", ExpectationOutcome(self.expectation_fulfilled)
        )
