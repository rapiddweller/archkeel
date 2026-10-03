# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only request and response envelopes for replaceable language processes."""

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from .facts import SourceFacts

PROTOCOL_VERSION: Final = "1.0.0"


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
    language: Literal["python"] = "python"


@dataclass(frozen=True, slots=True)
class DartSettings:
    language: Literal["dart"] = "dart"


@dataclass(frozen=True, slots=True)
class TypeScriptSettings:
    tsconfig: str = "tsconfig.json"
    language: Literal["typescript"] = "typescript"


ResolverSettings: TypeAlias = PythonSettings | DartSettings | TypeScriptSettings


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    snapshot: SnapshotInput
    scope: SourceScope
    resolver: ResolverSettings
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class CollectionResponse:
    facts: SourceFacts
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class CollectionError:
    kind: Literal["missing_tool", "timeout", "execution_error", "protocol_error"]
    subject: str
    message: str
