# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only request and response envelopes for replaceable language processes."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, TypeAlias

from .facts import (
    BASE_RESOLUTION_FEATURES,
    GATED_RESOLUTION_FEATURES,
    Language,
    SourceFacts,
    SourceSectionName,
)

PROTOCOL_VERSION: Final = "3.0.0"


class ProtocolVersion(StrEnum):
    V1 = "1.0.0"
    V2 = "2.0.0"
    V3 = PROTOCOL_VERSION
    V4 = "4.0.0"
    V5 = "5.0.0"
    V6 = "6.0.0"
    V7 = "7.0.0"
    V8 = "8.0.0"
    V9 = "9.0.0"


def since(first: ProtocolVersion) -> frozenset[ProtocolVersion]:
    """Return the protocol version and every later one; a feature stays in later versions."""
    versions = list(ProtocolVersion)
    return frozenset(versions[versions.index(first) :])


# 8.0.0 keeps 7.0.0 semantics on a compressed wire. 9.0.0 adds an explicit Explore source role.
FEATURE_GATED_PROTOCOLS: Final = since(ProtocolVersion.V7)


@dataclass(frozen=True, slots=True)
class SnapshotInput:
    root: str
    git_head: str
    dirty: bool | Literal["unknown"]


@dataclass(frozen=True, slots=True)
class SourceScope:
    roots: tuple[str, ...]
    namespace: str
    exclude_test_sources: bool = False


@dataclass(frozen=True, slots=True)
class PythonProviderSource:
    module: str
    path: str
    source: str
    digest: str


class PythonCollectionPhase(StrEnum):
    COLLECT = "collect"
    IMPORTS = "imports"
    PROVIDERS = "providers"


PYTHON_IMPORT_SURVEY_SECTIONS: Final[tuple[SourceSectionName, ...]] = (
    SourceSectionName.IMPORTS,
    SourceSectionName.UNKNOWNS,
)


@dataclass(frozen=True, slots=True)
class PythonSettings:
    language: Literal[Language.PYTHON] = Language.PYTHON
    provider_sources: tuple[PythonProviderSource, ...] = ()
    phase: PythonCollectionPhase = PythonCollectionPhase.COLLECT
    # Gated resolution families this scan needs; protocols before 7.0.0 collect every family.
    features: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DartSettings:
    language: Literal[Language.DART] = Language.DART


@dataclass(frozen=True, slots=True)
class RustSettings:
    language: Literal[Language.RUST] = Language.RUST


@dataclass(frozen=True, slots=True)
class TypeScriptSettings:
    tsconfig: str = "tsconfig.json"
    bundler: bool = False
    language: Literal[Language.TYPESCRIPT] = Language.TYPESCRIPT


ResolverSettings: TypeAlias = PythonSettings | DartSettings | RustSettings | TypeScriptSettings


def fixed_settings(
    language: Language,
) -> DartSettings | RustSettings | TypeScriptSettings | None:
    """The settings of a language that has no choice to make; `None` for Python."""
    if language == Language.DART:
        return DartSettings()
    if language == Language.RUST:
        return RustSettings()
    if language == Language.TYPESCRIPT:
        return TypeScriptSettings()
    return None


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
    provider_sources: tuple[PythonProviderSource, ...] = ()


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


def collected_resolution_features(
    version: ProtocolVersion, requested: Iterable[str]
) -> tuple[str, ...]:
    """Families a collector declares: every one before protocol 7.0.0, else base plus requested."""
    if version not in FEATURE_GATED_PROTOCOLS:
        return (*BASE_RESOLUTION_FEATURES, *GATED_RESOLUTION_FEATURES)
    wanted = frozenset(requested)
    return (
        *BASE_RESOLUTION_FEATURES,
        *(feature for feature in GATED_RESOLUTION_FEATURES if feature in wanted),
    )


class GapTitle:
    """The title text of a coverage gap that the host reads to name the cause (AD-336).

    A collector builds the title of a gap from these parts. The host matches the same parts, so a
    rewording changes both sides. The native collector repeats them in `imports.rs`; a test
    compares both texts.
    """

    NO_MODULE: Final = "Unresolved module: "
    UNIDENTIFIED_PACKAGE: Final = "Unidentified external package: "
    UNPUBLISHED_GLOBAL: Final = " has no unique unconditional publication"
    SCRIPT_GLOBALS_UNEXAMINED: Final = (
        "Script-global dependencies are not examined by the native collector"
    )
    SYNTAX_ERROR: Final = "Syntax error in "
    FILE_FAILURE: Final = " could not be analyzed"
    UNREADABLE_SOURCE: Final = "Unreadable selected source"
