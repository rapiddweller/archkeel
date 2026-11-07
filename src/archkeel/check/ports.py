# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Callable ports consumed by the check workflows."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from archkeel.ir.facts import Language as Language
from archkeel.ir.facts import SourceFacts
from archkeel.ir.host_records import HostRecord, InitialPRHeadEvidence
from archkeel.ir.model import ObservationResult as ObservationResult
from archkeel.ir.protocol import CollectionError, CollectionRequest


@dataclass(frozen=True, slots=True)
class ScanConfig:
    roots: tuple[str, ...]
    namespace: str
    contract: str
    digest: str
    language: Language = Language.PYTHON
    tsconfig: str | None = None
    collector_argv: tuple[str, ...] | None = None
    collector_output_limit_bytes: int | None = None
    collector_timeout_seconds: int | None = None
    bundler: bool = False


@dataclass(frozen=True, slots=True)
class FilesToWrite:
    """Ordered repository-relative paths and bytes for the caller to write."""

    entries: tuple[tuple[str, bytes], ...] = ()


class Analyzer(Protocol):
    def __call__(
        self,
        source_root: Path,
        *,
        roots: tuple[str, ...],
        namespace: str,
        contract: str,
        git_head: str,
        dirty: bool,
        contract_root: Path,
        language: Language,
    ) -> ObservationResult: ...


class Host(Protocol):
    def __call__(
        self,
        root: Path,
        *,
        expectation_sha: str,
        candidate_sha: str,
        environ: Mapping[str, str],
    ) -> tuple[HostRecord, ...] | InitialPRHeadEvidence: ...


class SourceCollector(Protocol):
    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError: ...
