# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable class state and ordered access facts, independent of declared roots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


@dataclass(frozen=True)
class FieldState:
    name: str
    annotation: str | None
    binding: Literal["UNKNOWN", "non_reassignable"]
    referent_mutability: Literal["UNKNOWN", "mutable_container"]
    mutability: Literal["UNKNOWN", "object_immutable", "mutable"]
    evidence_ids: tuple[str, ...]
    property_assignment: Literal["available", "unavailable"] | None = None


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
    access: Literal["read", "write", "mutation"]
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
