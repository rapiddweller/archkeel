# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Callable ports consumed by the check workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from archkeel.ir.facts import Language as Language
from archkeel.ir.facts import SourceFacts
from archkeel.ir.host_records import HostRecord, InitialPRHeadEvidence
from archkeel.ir.model import Diagnostic, DiagnosticKind
from archkeel.ir.model import ObservationResult as ObservationResult
from archkeel.ir.profiles import TEST_SCOPE_LANGUAGES
from archkeel.ir.protocol import CollectionError, CollectionRequest
from archkeel.ir.state_facts import ProducerKind as ProducerKind

_LISTED_TEST_FILES: Final = 20


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
    exclude_test_sources: bool = False

    def __post_init__(self) -> None:
        if self.exclude_test_sources and self.language not in TEST_SCOPE_LANGUAGES:
            raise ValueError(f"scan.exclude_test_sources is not supported for {self.language}")

    def scope_notes(
        self,
        files: tuple[str, ...],
        before: ScanConfig | None = None,
        revision: str | None = None,
    ) -> tuple[Diagnostic, ...]:
        """AD-313: name each excluded test file, so a PASS never hides what it did not read.

        `files` are the test files of the one listing that the collector read
        (Observer.excluded_for). `before` is the config of the compared revision: a changed test
        scope is a note too.
        """
        changed = (
            self._scope_change(before, revision)
            if before is not None and revision is not None
            else ()
        )
        return (*self._excluded_note(files), *changed)

    def _excluded_note(self, files: tuple[str, ...]) -> tuple[Diagnostic, ...]:
        if not self.exclude_test_sources:
            return ()
        shown = ", ".join(files[:_LISTED_TEST_FILES])
        more = len(files) - _LISTED_TEST_FILES
        listing = f" ({shown}{f' and {more} more' if more > 0 else ''})" if files else ""
        return (
            Diagnostic(
                DiagnosticKind.NOT_EXAMINED,
                "scan.exclude_test_sources",
                f"{len(files)} test source file(s) are excluded from this scan{listing}. "
                "File counts and verdicts cover the other files only.",
                "Set scan.exclude_test_sources to false in archkeel.toml to scan test sources too.",
            ),
        )

    def _scope_change(self, before: ScanConfig, revision: str) -> tuple[Diagnostic, ...]:
        """AD-313: a changed test scope makes two scans cover different files."""
        if before.exclude_test_sources == self.exclude_test_sources:
            return ()
        return (
            Diagnostic(
                DiagnosticKind.NOT_EXAMINED,
                "scan.exclude_test_sources",
                f"scan.exclude_test_sources is {str(self.exclude_test_sources).lower()} here and "
                f"{str(before.exclude_test_sources).lower()} at {revision[:12]}. The two scans "
                "cover different files.",
                "Review the files that the scope change adds or removes before you accept it.",
            ),
        )


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
