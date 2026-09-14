# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical ArchitectureIR primitives and deterministic serialization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias, get_args

from .measurements import Measurements

SCHEMA_VERSION = "1.2.0"
Verdict: TypeAlias = Literal["PASS", "FAIL"]
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
    "typing_signals",
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


@dataclass(frozen=True, slots=True)
class ForbiddenDependencyRule:
    id: str
    kind: Literal["forbidden_dependency"]
    source: str
    target: str
    include_type_checking: bool
    rationale: str
    provenance: tuple[str, ...]
    target_symbol: str | None = None
    allowed_sources: tuple[str, ...] = ()


class ForbiddenConstructKind(StrEnum):
    GETATTR = "getattr"
    HASATTR = "hasattr"
    CAST = "cast"
    EVAL = "eval"
    EXEC = "exec"
    DYNAMIC_IMPORT = "dynamic_import"
    TYPE_IGNORE = "type_ignore"


@dataclass(frozen=True, slots=True)
class ForbiddenConstructRule:
    id: str
    kind: Literal["forbidden_construct"]
    source: str
    constructs: tuple[ForbiddenConstructKind, ...]
    rationale: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExternalDependencyScopeRule:
    id: str
    kind: Literal["external_dependency_scope"]
    dependency: str
    allowed_sources: tuple[str, ...]
    rationale: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompleteAssignmentRule:
    id: str
    kind: Literal["complete_assignment"]
    source: str
    rationale: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NoComponentCyclesRule:
    id: str
    kind: Literal["no_component_cycles"]
    rationale: str
    provenance: tuple[str, ...]


ArchitectureRule: TypeAlias = (
    ForbiddenDependencyRule
    | ForbiddenConstructRule
    | ExternalDependencyScopeRule
    | CompleteAssignmentRule
    | NoComponentCyclesRule
)


def in_scope(name: str, scope: str) -> bool:
    """Match a qualified name against a dotted prefix without partial segments."""
    return name == scope or name.startswith(f"{scope}.")


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


@dataclass(frozen=True, slots=True)
class ArchitectureContract:
    schema_version: Literal["2.0.0"]
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
]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    kind: DiagnosticKind
    subject: str
    unknown_claim: str
    remedy: str
    pointer: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in get_args(DiagnosticKind):
            raise ValueError("invalid diagnostic kind")
        if not all(value.strip() for value in (self.subject, self.unknown_claim, self.remedy)):
            raise ValueError("diagnostic fields must not be empty")
        if "\n" in self.remedy or "\r" in self.remedy:
            raise ValueError("diagnostic remedy must be one line")
        if self.pointer is not None and self.pointer and not self.pointer.startswith("/"):
            raise ValueError("diagnostic pointer must be a JSON Pointer")


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
class RunResult:
    command: str
    exit_code: Literal[0, 1, 2]
    observation_complete: Literal["PASS", "UNKNOWN"] = "UNKNOWN"
    declared_rules: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
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
    delta: ArchitectureDelta | None = None
    provenance: CheckProvenance | None = None

    def __post_init__(self) -> None:
        if self.exit_code == 2 and not self.diagnostics:
            raise ValueError("exit 2 requires at least one Diagnostic")
        if self.diagnostics and self.exit_code != 2:
            raise ValueError("diagnostics require exit 2")
