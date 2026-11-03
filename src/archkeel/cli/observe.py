# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose configured language processes with the Core observer."""

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.check.observation import analyze_source_snapshot
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ObservationResult, SourceCollector
from archkeel.ir.codec import RawJson, observation_payload
from archkeel.ir.facts import SourceFacts
from archkeel.ir.phases import PhaseClock
from archkeel.ir.protocol import CollectionError, CollectionRequest


def observer_for(
    language: Language,
    *,
    collector_argv: tuple[str, ...] | None = None,
    tsconfig: str = "tsconfig.json",
    output_limit_bytes: int | None = None,
    timeout_seconds: int | None = None,
    bundler: bool = False,
    clock: PhaseClock | None = None,
) -> Observer:
    native_python = collector_argv is None and language == Language.PYTHON
    if collector_argv is None:
        collector_argv = (sys.executable, "-I", "-B", "-m", f"archkeel.analyzer.{language}.entry")
    collector = ProcessCollector(collector_argv, clock=clock)
    if output_limit_bytes is not None:
        collector = replace(collector, output_limit_bytes=output_limit_bytes)
    if timeout_seconds is not None:
        collector = replace(collector, timeout_seconds=timeout_seconds)
    return Observer(
        PythonProviderCollector(collector) if native_python else collector,
        tsconfig,
        bundler,
        clock,
    )


@dataclass(slots=True)
class _CollectOnce:
    """AD-285: explore observes twice; an equal request reuses the facts of the first pass."""

    collector: SourceCollector
    request: CollectionRequest | None = None
    facts: SourceFacts | CollectionError | None = None

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        if self.facts is None or request != self.request:
            self.request, self.facts = request, self.collector.collect(request)
        return self.facts


def explore_observer() -> Observer:
    """The Python observer of `archkeel explore`, which collects the source once."""
    observer = observer_for(Language.PYTHON)
    return replace(observer, collector=_CollectOnce(observer.collector))


def observe(
    source_root: Path,
    *,
    roots: tuple[str, ...],
    namespace: str,
    contract: str,
    git_head: str,
    dirty: bool,
    contract_root: Path,
    language: Language = Language.PYTHON,
) -> ObservationResult:
    return observer_for(language)(
        source_root,
        roots=roots,
        namespace=namespace,
        contract=contract,
        git_head=git_head,
        dirty=dirty,
        contract_root=contract_root,
        language=language,
    )


def analyze_snapshot(
    source_root: Path,
    *,
    git_head: str,
    dirty: bool | Literal["unknown"],
    contract_root: Path | None = None,
    contract_path: Path | None = None,
    roots: tuple[str, ...] = ("src",),
    namespace: str = "src",
    language: Language = Language.PYTHON,
) -> tuple[dict[str, RawJson], int]:
    """Compose source collection and Core assembly for local demo and audit tools."""
    observation, exit_code = analyze_source_snapshot(
        observer_for(language).collector,
        source_root,
        git_head=git_head,
        dirty=dirty,
        contract_root=contract_root,
        contract_path=contract_path,
        roots=roots,
        namespace=namespace,
        language=language,
    )

    return observation_payload(observation), exit_code
