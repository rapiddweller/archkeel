# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable actionable diagnostics, source locations and owned diagnostic vocabulary."""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass
from enum import StrEnum


class DiagnosticKind(StrEnum):
    MISSING_TOOL = "missing_tool"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    SCOPE_EMPTY = "scope_empty"
    RULE_WITHOUT_SUBJECTS = "rule_without_subjects"
    RULE_UNSUPPORTED_BY_PROFILE = "rule_unsupported_by_profile"
    RUNTIME_MISMATCH = "runtime_mismatch"
    INCOMPARABLE_RUNTIME = "incomparable_runtime"
    CONTRACT_INVALID = "contract_invalid"
    EXISTING_FILES = "existing_files"
    FILTER_UNKNOWN = "filter_unknown"


class DiagnosticCode(StrEnum):
    DECISION_OPEN = "decision.open"
    DECISION_CONFLICT = "decision.conflict"
    CLOSED_WORLD_OBSERVED_FORBIDDEN = "closed_world.observed_forbidden"
    CLOSED_WORLD_DUPLICATE = "closed_world.duplicate"
    INTERFACE_UNDECLARED = "interface.undeclared"
    INTERFACE_UNUSED = "interface.unused"
    INTERFACE_USAGE_UNKNOWN = "interface.usage_unknown"
    INTERFACE_MISSING = "interface.missing"
    INTERFACE_PLANNED_BUILT = "interface.planned_built"
    RATIONALE_PLACEHOLDER = "rationale.placeholder"
    RATIONALE_REPEATED = "rationale.repeated"
    GRAPH_COUNT = "graph.count"
    GRAPH_DRIFT = "graph.drift"
    RULE_VIOLATED = "rule.violated"
    RESPONSIBILITY_MISSING = "responsibility.missing"
    REFERENCE_NAMESPACE = "reference.namespace"
    REFERENCE_PUBLIC_OWNER = "reference.public_owner"
    REFERENCE_PUBLIC_UNDERSCORE = "reference.public_underscore"
    REFERENCE_PROVENANCE = "reference.provenance"
    REFERENCE_PACKAGE_UNSCANNED = "reference.package_unscanned"
    API_SURFACE_MISSING = "api_surface.missing"
    CONTRACT_SCHEMA_VERSION = "contract.schema_version"
    CONTRACT_INVALID = "contract.invalid"
    BASELINE_INVALID = "baseline.invalid"
    AGAINST_INVALID = "against.invalid"
    AMENDMENT_INVALID = "amendment.invalid"
    OBSERVATION_INCOMPLETE = "observation.incomplete"
    INSIDE_PUBLIC_MISMATCH = "inside.public_mismatch"
    INSIDE_FORBIDDEN_IMPORT = "inside.forbidden_import"
    COMPATIBILITY_INVALID = "compatibility.invalid"
    BUDGET_EXCEEDED = "budget.exceeded"
    BUDGET_UNKNOWN = "budget.unknown"


@dataclass(frozen=True, slots=True)
class ReportLocation:
    path: str
    line: int


@dataclass(frozen=True, slots=True)
class Diagnostic:
    kind: DiagnosticKind
    subject: str
    unknown_claim: str
    remedy: str
    pointer: str | None = None
    code: DiagnosticCode | None = None
    locations: tuple[ReportLocation, ...] = ()
    contract_path: str | None = None

    def __post_init__(self) -> None:
        try:
            builtins.object.__setattr__(self, "kind", DiagnosticKind(self.kind))
        except ValueError as error:
            raise ValueError("invalid diagnostic kind") from error
        if not all(value.strip() for value in (self.subject, self.unknown_claim, self.remedy)):
            raise ValueError("diagnostic fields must not be empty")
        if re.search(r"[\r\n]", self.remedy):
            raise ValueError("diagnostic remedy must be one line")
        if self.pointer is not None and self.pointer and not re.match(r"/", self.pointer):
            raise ValueError("diagnostic pointer must be a JSON Pointer")
        if self.code is not None:
            try:
                builtins.object.__setattr__(self, "code", DiagnosticCode(self.code))
            except ValueError as error:
                raise ValueError("invalid diagnostic code") from error
        if self.kind == DiagnosticKind.CONTRACT_INVALID and self.code is None:
            raise ValueError("contract_invalid diagnostics require a code")
        if self.kind != DiagnosticKind.CONTRACT_INVALID and self.code is not None:
            raise ValueError("only contract_invalid diagnostics carry a code")


class DiagnosticError(ValueError):
    diagnostic: Diagnostic

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.unknown_claim)
