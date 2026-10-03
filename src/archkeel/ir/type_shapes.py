# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable source type syntax; binding resolution and policy belong to evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


@dataclass(frozen=True)
class TypeName:
    text: str
    name: str


@dataclass(frozen=True)
class TypeMember:
    text: str
    owner: TypeShape
    member: str


@dataclass(frozen=True)
class TypeApplication:
    text: str
    head: TypeShape
    arguments: tuple[TypeShape, ...]
    tuple_arguments: bool


@dataclass(frozen=True)
class TypeUnion:
    text: str
    left: TypeShape
    right: TypeShape


class LiteralKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    NONE = "none"
    ELLIPSIS = "ellipsis"
    OTHER = "other"


@dataclass(frozen=True)
class TypeLiteral:
    text: str
    kind: LiteralKind


@dataclass(frozen=True)
class TypeUnpack:
    text: str
    argument: TypeShape


@dataclass(frozen=True)
class UnresolvedType:
    text: str
    valid_syntax: bool


TypeShape: TypeAlias = (
    TypeName | TypeMember | TypeApplication | TypeUnion | TypeLiteral | TypeUnpack | UnresolvedType
)
TypeShapeIndex: TypeAlias = Mapping[str, TypeShape]
