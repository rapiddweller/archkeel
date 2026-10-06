# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical ArchitectureIR primitives and deterministic serialization."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, get_args, get_type_hints

from .architecture_graph import AssessmentStatus, TargetDefinition
from .architecture_graph import ComponentRole as ComponentRole
from .architecture_graph import ContractModuleTarget as ContractModuleTarget
from .architecture_graph import ExternalDependencyScopeRule as ExternalDependencyScopeRule
from .architecture_graph import RootLayoutRule as RootLayoutRule
from .architecture_graph import RuleAssessment as RuleAssessment
from .architecture_graph import RuleAssessmentStatus as RuleAssessmentStatus
from .architecture_graph import contract_relative_path as contract_relative_path
from .facts import (
    EVIDENCE_FIELDS as EVIDENCE_FIELDS,
)
from .facts import (
    RECORD_FIELDS as RECORD_FIELDS,
)
from .facts import (
    AnalyzerInfo as AnalyzerInfo,
)
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
    in_scope as in_scope,
)
from .facts import (
    stable_id as stable_id,
)
from .host_records import InitialPRHeadEvidence
from .measurements import MeasurementBudgetName, Measurements, NameBudgetKind

if TYPE_CHECKING:
    from .architecture_projection import ArchitectureProjection

RawJson: TypeAlias = str | int | float | bool | None | Sequence["RawJson"] | Mapping[str, "RawJson"]


def public_api_id(selector: str) -> str:
    return f"API-{hashlib.sha256(selector.encode()).hexdigest()[:16]}"


SCHEMA_VERSION = "1.3.0"
DELTA_SCHEMA_VERSION = "1.4.0"
Verdict: TypeAlias = Literal["PASS", "FAIL"]
ComponentOwnership: TypeAlias = tuple[str, tuple[str, ...], tuple[str, ...]]
PackageComponentOwnership: TypeAlias = tuple[str, tuple[str, ...]]
ComponentOwnershipInput: TypeAlias = ComponentOwnership | PackageComponentOwnership
# AD-26's full vocabulary, for the one verdict that can also fail to decide (AD-67).
RuleVerdict: TypeAlias = AssessmentStatus
ComparisonStatus: TypeAlias = Literal["SUPPORTED", "UNKNOWN"]
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
    decided_by: Literal["architect", "agent"] | None = None
    # The physical package where this component is expected to live. `packages` remains
    # the ownership set; modules owned by this component outside `namespace` are violations.
    namespace: str | None = None
    # Exact module ownership is separate from recursive package ownership. None preserves
    # canonical bytes for contracts that do not declare exact modules.
    exact_modules: tuple[str, ...] | None = None
    layer: str | None = None


def facade_covers(
    module: str,
    name: str,
    component: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
) -> bool:
    """Answer facade coverage from the component contract and observed module exports."""
    public = component.public
    if public is None or name.startswith("_"):
        return False
    if f"{module}:{name}" in public:
        return True
    exports = exports_by_module.get(module)
    return module in public and (not exports or name in exports)


def interface_covers_import(
    target_module: str,
    symbol: str | None,
    reexport_chain: Iterable[str],
    component: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
) -> bool:
    """Match a concrete import route against a declared interface."""
    if component.public is None:
        return False
    if symbol is None:
        return target_module in component.public
    if symbol.startswith("_"):
        return False
    for entry in reexport_chain:
        module, _, name = entry.rpartition(".")
        if facade_covers(module, name, component, exports_by_module):
            return True
    return False


@dataclass(frozen=True, slots=True)
class RequiredComponent:
    """One component its owner may import, carrying the architect's reason for the edge (AD-32).

    `through` narrows the edge to module prefixes of the required component (AD-42); empty
    means its whole public surface, the way the entry always read before.

    `decided_by` names who decided this edge (AD-50); it overrides the component's own.
    """

    component: str
    rationale: str
    through: tuple[str, ...] = ()
    decided_by: Literal["architect", "agent"] | None = None


def requires_covers(
    source: ContractComponent | tuple[RequiredComponent, ...],
    target_label: str,
    target_module: str | None = None,
) -> bool:
    """Apply AD-42; without a module, ask only whether the target is declared."""
    entries = (source.requires or ()) if isinstance(source, ContractComponent) else source
    return any(
        entry.component == target_label
        and (
            target_module is None
            or not entry.through
            or any(in_scope(target_module, module) for module in entry.through)
        )
        for entry in entries
    )


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


CompatibilityLifetime: TypeAlias = Literal["permanent", "migration"]


@dataclass(frozen=True, slots=True)
class CompatibilityShim:
    """A declared old module path kept as a logic-free import compatibility shim."""

    module: str
    target: str
    lifetime: CompatibilityLifetime


@dataclass(frozen=True, slots=True)
class ContractMeasurementBudget:
    name: MeasurementBudgetName
    provenance: tuple[str, ...]


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
class ForbiddenDependencyRule:
    id: str
    kind: Literal["forbidden_dependency"]
    source: str
    target: str
    include_type_checking: bool
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    target_symbol: str | None = None
    allowed_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AllowedDependencyRule:
    """AD-15: a decision that a component pair may depend; it adds no report violation."""

    id: str
    kind: Literal["allowed_dependency"]
    source: str
    target: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


class SymbolClassKind(StrEnum):
    """The five values `class_kind` resolves to (`analyzer.embedded.symbols`'s fixpoint)."""

    PROTOCOL = "protocol"
    ENUM = "enum"
    PYDANTIC_MODEL = "pydantic_model"
    DATACLASS = "dataclass"
    CLASS = "class"


@dataclass(frozen=True, slots=True)
class TypeIgnoreAllowance:
    """One suppression bound to its scope, source line, statement and exact tag."""

    qualified_name: str
    line: int
    statement: str
    tag: str


@dataclass(frozen=True, slots=True)
class ForbiddenConstructRule:
    """`allowed_sources` match an owner scope by prefix, `exact_sources` only the scope named."""

    id: str
    kind: Literal["forbidden_construct"]
    source: str
    constructs: tuple[ForbiddenConstructKind, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()
    allowed_type_ignores: tuple[TypeIgnoreAllowance, ...] = ()


@dataclass(frozen=True, slots=True)
class CompleteAssignmentRule:
    id: str
    kind: Literal["complete_assignment"]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


@dataclass(frozen=True, slots=True)
class CompleteRequiresRule:
    """AD-32: a cross-component import no `requires` entry covers is a violation."""

    id: str
    kind: Literal["complete_requires"]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    include_type_checking: bool = True


@dataclass(frozen=True, slots=True)
class LayerOrderRule:
    """Declared requires permissions run from outer to inner layers, or stay in one layer."""

    id: str
    kind: Literal["layer_order"]
    layers: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    components: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class CompleteExternalScopeRule:
    id: str
    kind: Literal["complete_external_scope"]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


@dataclass(frozen=True, slots=True)
class NoComponentCyclesRule:
    """No import cycle at the declared level, among cycles touching `components` (AD-98).

    `level` None is the component level every contract before AD-98 declares, and
    `components` None is every cycle at that level: both stay absent from the canonical
    contract, so its bytes and AD-61's amendment digest do not move for existing contracts.
    """

    id: str
    kind: Literal["no_component_cycles"]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    level: Literal["module"] | None = None
    components: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class InterfaceBoundaryRule:
    id: str
    kind: Literal["interface_boundary"]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    include_type_checking: bool = True


@dataclass(frozen=True, slots=True)
class SiblingIsolationRule:
    id: str
    kind: Literal["sibling_isolation"]
    members: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    include_type_checking: bool = True


@dataclass(frozen=True, slots=True)
class SymbolPlacementRule:
    """A class of a named kind below `source` must be defined in an allowed module.

    `allowed_sources` match a defining module by prefix, `exact_sources` only the module
    named (AD-49): a package root is a prefix of every module below it, so only the exact
    form scopes the root and nothing below it.
    """

    id: str
    kind: Literal["symbol_placement"]
    source: str
    class_kinds: tuple[SymbolClassKind, ...]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoundaryTypeAllowance:
    """One exact signature, DTO field or opaque map-value exception."""

    qualified_name: str
    position: str
    field_path: str
    annotation: str
    container_depth: int | None = None


@dataclass(frozen=True, slots=True)
class BoundaryTypesRule:
    """A component's declared facade function below `source` takes and returns no bare
    `dict`/`object`, and no named type outside a builtin, an enum, a Pydantic model, or a type
    some component's own `public` list already declares (AD-58, amended by AD-63).

    Only a function the owning component's `public` list itself covers is inspected: the rule
    reads the contract's declared facade, not a naming convention over every non-underscore,
    module-level function. `allowed_sources` and `exact_sources` exempt an owner the way
    `forbidden_construct` exempts one (AD-49).
    """

    id: str
    kind: Literal["boundary_types"]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]
    allowed_sources: tuple[str, ...] = ()
    exact_sources: tuple[str, ...] = ()
    allowed_positions: tuple[BoundaryTypeAllowance, ...] = ()


ArchitectureRule: TypeAlias = (
    ForbiddenDependencyRule
    | AllowedDependencyRule
    | ForbiddenConstructRule
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
)

# Typed authoring kinds come from ArchitectureRule. Record consumers also assess UML intent.
UML_TARGET_KIND: Final = "uml_target"
ARCHITECTURE_TARGET_KIND: Final = "architecture_target"
TARGET_GRAPH_RECORD_KINDS: Final = frozenset({UML_TARGET_KIND, ARCHITECTURE_TARGET_KIND})
RULE_KINDS: Final[frozenset[str]] = frozenset(
    kind
    for rule_type in get_args(ArchitectureRule)
    for kind in get_args(get_type_hints(rule_type)["kind"])
)
RULE_RECORD_KINDS: Final = RULE_KINDS | {UML_TARGET_KIND}


# The symbol kinds that carry a signature. One set, because a record's `kind` and its
# older `symbol_category` field hold the same three values and two copies may drift apart.
FUNCTION_KINDS = frozenset({"function", "method"})


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


def module_in_ownership(module: str, packages: Iterable[str], exact_modules: Iterable[str]) -> bool:
    """Apply recursive package and exact module ownership selectors together."""
    return module in exact_modules or any(in_scope(module, package) for package in packages)


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


def declared_package_pair(
    source: str,
    target: str,
    target_symbol: str | None,
    components: tuple[ComponentOwnership, ...],
) -> tuple[str, str] | None:
    """Resolve an unqualified rule naming two uniquely declared package selectors."""
    if target_symbol is not None:
        return None
    source_owners = {label for label, packages, _ in components if source in packages}
    target_owners = {label for label, packages, _ in components if target in packages}
    if len(source_owners) != 1 or len(target_owners) != 1:
        return None
    return next(iter(source_owners)), next(iter(target_owners))


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
    schema_version: Literal["2.1.0", "2.2.0", "2.3.0"]
    components: tuple[ContractComponent, ...]
    rules: tuple[ArchitectureRule, ...]
    schema: str | None = None
    declarations: ContractDeclarations | None = None

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
_SCALAR_FIELDS: Final = frozenset({"source", "target", "root", "namespace", "command", "owner"})


def _rule_references(
    index: int, rule: ArchitectureRule, external: frozenset[str]
) -> list[ModuleReference]:
    """One rule's fields that name a module, a module prefix or a qualified symbol."""
    named: list[tuple[str, tuple[str, ...], bool]] = []
    if isinstance(
        rule,
        ForbiddenDependencyRule
        | AllowedDependencyRule
        | ForbiddenConstructRule
        | CompleteAssignmentRule
        | CompleteExternalScopeRule
        | SymbolPlacementRule
        | BoundaryTypesRule,
    ):
        named += [("source", (rule.source,), True)]
    if isinstance(rule, AllowedDependencyRule):
        named += [("target", (rule.target,), True)]
    if isinstance(rule, ForbiddenDependencyRule):
        # AD-97: a forbidden SDK library (`dart.io`) is a real target outside the namespace.
        named += [("target", (rule.target,), rule.target not in external)]
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
    if isinstance(rule, BoundaryTypesRule):
        references += [
            ModuleReference(
                f"/rules/{index}/allowed_positions/{item}/qualified_name",
                allowance.qualified_name,
                False,
            )
            for item, allowance in enumerate(rule.allowed_positions)
        ]
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


DiagnosticKind: TypeAlias = Literal[
    "missing_tool",
    "timeout",
    "parse_error",
    "scope_empty",
    "rule_without_subjects",
    "rule_unsupported_by_profile",
    "runtime_mismatch",
    "incomparable_runtime",
    "contract_invalid",
    "existing_files",
    "filter_unknown",
]

# AD-12: sixteen findings shared one kind and differed only in prose.
DiagnosticCode: TypeAlias = Literal[
    "decision.open",
    "decision.conflict",
    "closed_world.observed_forbidden",
    "closed_world.duplicate",
    "interface.undeclared",
    "interface.unused",
    "interface.usage_unknown",
    "interface.missing",
    "interface.planned_built",
    "rationale.placeholder",
    "rationale.repeated",
    "graph.count",
    "graph.drift",
    "rule.violated",
    "reference.namespace",
    "reference.public_owner",
    "reference.public_underscore",
    "reference.provenance",
    "reference.package_unscanned",
    "api_surface.missing",
    "contract.schema_version",
    "contract.invalid",
    "baseline.invalid",
    "against.invalid",
    "amendment.invalid",
    "observation.incomplete",
    "inside.public_mismatch",
    "inside.forbidden_import",
    "compatibility.invalid",
    "budget.exceeded",
    "budget.unknown",
]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    kind: DiagnosticKind
    subject: str
    unknown_claim: str
    remedy: str
    pointer: str | None = None
    code: DiagnosticCode | None = None

    def __post_init__(self) -> None:
        if self.kind not in get_args(DiagnosticKind):
            raise ValueError("invalid diagnostic kind")
        if not all(value.strip() for value in (self.subject, self.unknown_claim, self.remedy)):
            raise ValueError("diagnostic fields must not be empty")
        if "\n" in self.remedy or "\r" in self.remedy:
            raise ValueError("diagnostic remedy must be one line")
        if self.pointer is not None and self.pointer and not self.pointer.startswith("/"):
            raise ValueError("diagnostic pointer must be a JSON Pointer")
        if self.code is not None and self.code not in get_args(DiagnosticCode):
            raise ValueError("invalid diagnostic code")
        if self.kind == "contract_invalid" and self.code is None:
            raise ValueError("contract_invalid diagnostics require a code")
        if self.kind != "contract_invalid" and self.code is not None:
            raise ValueError("only contract_invalid diagnostics carry a code")


class DiagnosticError(ValueError):
    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.unknown_claim)


@dataclass(frozen=True, slots=True)
class ObservationResult:
    observation: Observation | None
    coverage: Coverage | None
    diagnostics: tuple[Diagnostic, ...]

    def __post_init__(self) -> None:
        if self.observation is not None and self.observation.coverage != self.coverage:
            raise ValueError("analyzer coverage differs from its observation")
        if (
            self.observation is None or self.coverage is None or self.coverage.status != "PASS"
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
        measured = (self.baseline is not None, self.head is not None)
        if measured != ((True, True) if self.status == "SUPPORTED" else (False, False)):
            raise ValueError("measurements exist exactly when regression checks are SUPPORTED")


@dataclass(frozen=True, slots=True)
class ArchitectureDelta:
    schema_version: str
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
class ReportLocation:
    path: str
    line: int


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


CallStatus: TypeAlias = Literal["unresolved", "partially_resolved"]


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


@dataclass(frozen=True, slots=True)
class UnresolvedCallChange:
    """AD-100: one unresolved call whose count differs between two compared revisions.

    Its identity is the file, the calling scope and the call expression, never the line, so
    code that only moves is no change. Identical expressions in one caller share that identity
    and differ by count; `lines` then names every line of it on the side holding more, because
    which one is new cannot be decided. A removed call's lines are those of the older revision.
    """

    change: Literal["added", "removed"]
    caller: str
    expression: str
    reason: str
    component: str | None
    path: str
    lines: tuple[int, ...]
    before: int
    after: int


@dataclass(frozen=True, slots=True)
class RunResult:
    command: str
    exit_code: Literal[0, 1, 2]
    observation_complete: Literal["PASS", "UNKNOWN"] = "UNKNOWN"
    declared_rules: RuleVerdict = "UNKNOWN"
    expectation_fulfilled: Literal["PASS", "FAIL", "UNKNOWN", "n/a"] = "UNKNOWN"
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
    # AD-77: baseline drift is reported as deterministic fingerprint counts.
    baseline_new: int | None = None
    baseline_resolved: int | None = None
    delta: ArchitectureDelta | None = None
    provenance: CheckProvenance | None = None
    open_decisions: tuple[OpenDecision, ...] = ()
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

    def __post_init__(self) -> None:
        if self.exit_code == 2 and not self.diagnostics:
            raise ValueError("exit 2 requires at least one Diagnostic")
        if self.diagnostics and self.exit_code != 2:
            raise ValueError("diagnostics require exit 2")
