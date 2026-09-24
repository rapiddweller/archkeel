# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical ArchitectureIR primitives and deterministic serialization."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final, Literal, TypeAlias, get_args, get_type_hints

from .measurements import MeasurementBudgetName, Measurements, NameBudgetKind

SCHEMA_VERSION = "1.3.0"
Verdict: TypeAlias = Literal["PASS", "FAIL"]
# AD-26's full vocabulary, for the one verdict that can also fail to decide (AD-67).
RuleVerdict: TypeAlias = Literal["PASS", "FAIL", "UNKNOWN"]
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
RECORD_FIELDS = (
    "id",
    "evidence_class",
    "area",
    "kind",
    "title",
    "subjects",
    "evidence_ids",
    "rule_ids",
    "fact_ids",
    "provenance",
    "data",
)
EVIDENCE_FIELDS = ("id", "file", "line", "end_line", "column", "excerpt")


class EvidenceClass(StrEnum):
    FACT = "FACT"
    DECLARED_RULE = "DECLARED_RULE"
    VIOLATION = "VIOLATION"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


def stable_id(prefix: str, *parts: object) -> str:
    """Return a compact content-derived ID independent of traversal order."""
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


@dataclass(frozen=True, slots=True)
class RecordData:
    """Immutable, profile-owned JSON payload; the common schema leaves its keys open."""

    entries: tuple[tuple[str, JsonValue], ...] = ()

    def __post_init__(self) -> None:
        if len({key for key, _ in self.entries}) != len(self.entries):
            raise ValueError("duplicate record data key")

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return next((value for name, value in self.entries if name == key), default)


JsonValue: TypeAlias = str | int | float | bool | None | tuple["JsonValue", ...] | RecordData


@dataclass(frozen=True, slots=True)
class Record:
    id: str
    evidence_class: EvidenceClass
    area: str
    kind: str
    title: str
    subjects: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    provenance: tuple[str, ...]
    data: RecordData


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    file: str
    line: int
    end_line: int
    column: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class AnalyzerInfo:
    name: str
    version: str
    code_digest: str


@dataclass(frozen=True, slots=True)
class SourceInfo:
    git_head: str
    dirty: bool | Literal["unknown"]
    source_digest: str
    scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractInfo:
    schema_version: str
    digest: str
    path: str


class ComponentRole(StrEnum):
    COMPONENT = "component"
    INTERFACE = "interface"
    CONTRACT = "contract"
    PROJECTION = "projection"
    FOUNDATION = "foundation"


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


def contract_relative_path(value: str) -> PurePosixPath | None:
    """Return a contract-declared repository path, or None when it leaves the repository.

    Every path a contract names is attacker-adjacent input: it may escape with `..`, with an
    absolute path or with a Windows separator. The judgement stays pure so the analyzer and
    `check` can share it while neither may import the other (AD-34); each caller adds its own
    filesystem check, which keeps `ir` free of I/O (AD-17).
    """
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        return None
    return relative


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


class ForbiddenConstructKind(StrEnum):
    GETATTR = "getattr"
    HASATTR = "hasattr"
    CAST = "cast"
    EVAL = "eval"
    EXEC = "exec"
    DYNAMIC_IMPORT = "dynamic_import"
    TYPE_IGNORE = "type_ignore"
    ANY_ANNOTATION = "any_annotation"
    PLACEHOLDER_BODY = "placeholder_body"
    ASSERT = "assert"
    BROAD_EXCEPT = "broad_except"
    SETATTR = "setattr"
    DELATTR = "delattr"
    VARS = "vars"
    DUNDER_DICT = "dunder_dict"
    STRING_LITERAL_COMPARE = "string_literal_compare"


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
class CompleteAssignmentRule:
    id: str
    kind: Literal["complete_assignment"]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


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
class CompleteExternalScopeRule:
    id: str
    kind: Literal["complete_external_scope"]
    source: str
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


@dataclass(frozen=True, slots=True)
class NoComponentCyclesRule:
    id: str
    kind: Literal["no_component_cycles"]
    rationale: str
    provenance: tuple[str, ...]
    decided_by: Literal["architect", "agent"]


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
    """One exact nested field exception for a declared boundary position (#134)."""

    qualified_name: str
    position: str
    field_path: str
    annotation: str


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
    | NoComponentCyclesRule
    | InterfaceBoundaryRule
    | SiblingIsolationRule
    | SymbolPlacementRule
    | BoundaryTypesRule
)

# Every rule kind the ArchitectureRule union names, read by reflection so a new rule kind is
# recognized without a second hand-written list (AD-16). `ir.decisions` and `ir.baseline` both
# read this one set instead of each keeping their own (AD-60).
RULE_KINDS: Final[frozenset[str]] = frozenset(
    kind
    for rule_type in get_args(ArchitectureRule)
    for kind in get_args(get_type_hints(rule_type)["kind"])
)


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


def in_scope(name: str, scope: str) -> bool:
    """Match a qualified name against a dotted prefix without partial segments."""
    return name == scope or name.startswith(f"{scope}.")


def package_owners(components: Iterable[tuple[str, tuple[str, ...]]]) -> dict[str, str]:
    """Map each declared package to its owning component label, by exact match.

    Exact match only: a rule whose `source` and `target` each name a package this way
    decides (`ir.decisions`) or enforces (the analyzer's forbidden-dependency matching) the
    whole ordered component pair, every package of one component against every package of
    the other. A rule scoped to a submodule or a `target_symbol` narrows the rule instead,
    and is unaffected by this mapping.
    """
    return {package: label for label, packages in components for package in packages}


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


@dataclass(frozen=True, slots=True)
class ArchitectureContract:
    schema_version: Literal["2.1.0"]
    components: tuple[ContractComponent, ...]
    rules: tuple[ArchitectureRule, ...]
    schema: str | None = None
    declarations: ContractDeclarations | None = None

    def component_for(self, module: str) -> ContractComponent | None:
        """Return the only component owning a module; overlapping ownership owns nothing."""
        owners = [
            component
            for component in self.components
            if any(in_scope(module, package) for package in component.packages)
        ]
        return owners[0] if len(owners) == 1 else None


@dataclass(frozen=True, slots=True)
class Coverage:
    status: Verdict
    files_discovered: int
    files_read: int
    files_parsed: int
    calls_analyzed: int
    calls_resolved: int
    calls_partially_resolved: int
    calls_unresolved: int
    ast_coverage_percent: float
    call_resolution_percent: float
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

    def records(self, section: str) -> tuple[Record, ...] | None:
        return next((item.records for item in self.sections if item.name == section), None)


DiagnosticKind: TypeAlias = Literal[
    "missing_tool",
    "timeout",
    "parse_error",
    "scope_empty",
    "rule_without_subjects",
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
    before_count: int
    after_count: int
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


@dataclass(frozen=True, slots=True)
class OpenDecision:
    """AD-15: one ordered component pair neither allowed nor forbidden by the contract.

    `forbidden_option` and `allowed_option` are the exact rules `init --json` and
    `validate --json` offer for this pair; only their `rationale` still needs the
    architect's words.
    """

    source: str
    target: str
    source_package: str
    target_package: str
    observed: bool
    import_sites: int
    forbidden_option: ForbiddenDependencyRule
    allowed_option: AllowedDependencyRule


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

    `max_names` is the contract's target and `over_target` the known distance to it.
    `new_names` and `removed_names` compare with the baseline's accepted names, and are None
    when the run had no baseline. `uncounted` names the imports or modules that keep `names`
    a lower bound.
    """

    budget: NameBudgetKind
    subject: str
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
    filtered_violations: tuple[Record, ...] | None = None
    # AD-99: every declared facade and pair budget `validate` measured; None when none exists.
    interface_budgets: tuple[InterfaceBudgetResult, ...] | None = None

    def __post_init__(self) -> None:
        if self.exit_code == 2 and not self.diagnostics:
            raise ValueError("exit 2 requires at least one Diagnostic")
        if self.diagnostics and self.exit_code != 2:
            raise ValueError("diagnostics require exit 2")
