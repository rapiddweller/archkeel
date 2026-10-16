# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only request and response envelopes for replaceable language processes."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, TypeAlias

from .facts import Language, SourceFacts

PROTOCOL_VERSION: Final = "3.0.0"


class ProtocolVersion(StrEnum):
    V1 = "1.0.0"
    V2 = "2.0.0"
    V3 = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class SnapshotInput:
    root: str
    git_head: str
    dirty: bool | Literal["unknown"]


@dataclass(frozen=True, slots=True)
class SourceScope:
    roots: tuple[str, ...]
    namespace: str


@dataclass(frozen=True, slots=True)
class PythonSettings:
    language: Literal[Language.PYTHON] = Language.PYTHON


@dataclass(frozen=True, slots=True)
class DartSettings:
    language: Literal[Language.DART] = Language.DART


@dataclass(frozen=True, slots=True)
class TypeScriptSettings:
    tsconfig: str = "tsconfig.json"
    language: Literal[Language.TYPESCRIPT] = Language.TYPESCRIPT


ResolverSettings: TypeAlias = PythonSettings | DartSettings | TypeScriptSettings


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    snapshot: SnapshotInput
    scope: SourceScope
    resolver: ResolverSettings
    protocol_version: ProtocolVersion = ProtocolVersion(PROTOCOL_VERSION)


@dataclass(frozen=True, slots=True)
class CollectionResponse:
    facts: SourceFacts
    protocol_version: ProtocolVersion = ProtocolVersion(PROTOCOL_VERSION)


class CollectionErrorKind(StrEnum):
    MISSING_TOOL = "missing_tool"
    TIMEOUT = "timeout"
    EXECUTION_ERROR = "execution_error"
    PROTOCOL_ERROR = "protocol_error"


@dataclass(frozen=True, slots=True)
class CollectionError:
    kind: CollectionErrorKind
    subject: str
    message: str
