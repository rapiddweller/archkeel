# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable class state and ordered access facts, independent of declared roots."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


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
