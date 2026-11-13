# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable class state and ordered access facts, independent of declared roots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class AnalyzerInfo:
    name: str
    version: str
    code_digest: str


class RuntimeRequirementState(StrEnum):
    DECLARED = "declared"
    METADATA_MISSING = "metadata_missing"
    METADATA_INVALID = "metadata_invalid"
    REQUIREMENT_MISSING = "requirement_missing"
    REQUIREMENT_INVALID = "requirement_invalid"


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    name: str
    version: str
    required: str | None = None
    # Diagnostic context does not change runtime comparability for saved snapshots.
    requirement_state: RuntimeRequirementState = field(
        default=RuntimeRequirementState.DECLARED, compare=False
    )


@dataclass(frozen=True, slots=True)
class VerifiedBinary:
    """Host-only evidence of a bundled executable checked in this run; never read from wire."""

    digest: str
    analyzer: str
    runtime: RuntimeInfo | None = None


def native_runtime_valid(runtime: RuntimeInfo) -> bool:
    lower = re.fullmatch(r">=([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", runtime.required or "")
    version = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", runtime.version)
    return (
        runtime.name == "rust"
        and runtime.requirement_state == RuntimeRequirementState.DECLARED
        and lower is not None
        and version is not None
        and tuple(map(int, version.groups())) >= tuple(int(v or 0) for v in lower.groups())
    )


class BindingState(StrEnum):
    UNKNOWN = "UNKNOWN"
    NON_REASSIGNABLE = "non_reassignable"


class ReferentMutability(StrEnum):
    UNKNOWN = "UNKNOWN"
    MUTABLE_CONTAINER = "mutable_container"


class ObjectMutability(StrEnum):
    UNKNOWN = "UNKNOWN"
    OBJECT_IMMUTABLE = "object_immutable"
    MUTABLE = "mutable"


class PropertyAssignment(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class StateAccess(StrEnum):
    READ = "read"
    WRITE = "write"
    MUTATION = "mutation"


@dataclass(frozen=True)
class FieldState:
    name: str
    annotation: str | None
    binding: BindingState
    referent_mutability: ReferentMutability
    mutability: ObjectMutability
    evidence_ids: tuple[str, ...]
    property_assignment: PropertyAssignment | None = None


@dataclass(frozen=True)
class ClassStateFacts:
    qualified_name: str
    module: str
    frozen: bool
    protocol: bool
    fields: tuple[FieldState, ...]
    methods: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class StateParameter:
    name: str
    annotation: str | None


@dataclass(frozen=True)
class Assignment:
    targets: tuple[str, ...]
    constructor: str | None
    annotation: str | None
    alias: str | None


@dataclass(frozen=True)
class AttributeAccess:
    binding: str
    path: tuple[str, ...]
    access: StateAccess
    evidence_id: str


@dataclass(frozen=True)
class ArgumentPass:
    binding: str
    target: str
    evidence_id: str


StateEvent: TypeAlias = Assignment | AttributeAccess | ArgumentPass


@dataclass(frozen=True)
class FunctionStateTrace:
    scope: str
    module: str
    class_owner: str | None
    receiver: str | None
    parameters: tuple[StateParameter, ...]
    events: tuple[StateEvent, ...]


@dataclass(frozen=True)
class StateFacts:
    classes: tuple[ClassStateFacts, ...]
    functions: tuple[FunctionStateTrace, ...]


class ProducerKind(StrEnum):
    """Who made the facts. The host knows it from how it started the collector (AD-344)."""

    PYTHON = "python"  # the collector of this package
    BUNDLED = "bundled"  # the native collector of this package, started with its digest
    PINNED = "pinned"  # a configured collector whose file has the pinned digest
    EXTERNAL = "external"  # a configured collector without a pin: it cannot prove a rule
