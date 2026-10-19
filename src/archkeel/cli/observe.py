# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose configured language processes with the Core observer."""

import sys
from pathlib import Path
from typing import Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.check.observation import analyze_source_snapshot
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ObservationResult
from archkeel.ir.codec import RawJson, observation_payload
from archkeel.ir.repository_files import RepositorySnapshotPaths


def observer_for(
    language: Language,
    *,
    collector_argv: tuple[str, ...] | None = None,
    tsconfig: str = "tsconfig.json",
    output_limit_bytes: int | None = None,
) -> Observer:
    native_python = collector_argv is None and language == Language.PYTHON
    if collector_argv is None:
        collector_argv = (sys.executable, "-I", "-B", "-m", f"archkeel.analyzer.{language}.entry")
    collector = (
        ProcessCollector(collector_argv)
        if output_limit_bytes is None
        else ProcessCollector(collector_argv, output_limit_bytes=output_limit_bytes)
    )
    return Observer(PythonProviderCollector(collector) if native_python else collector, tsconfig)


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
    repository_snapshot: RepositorySnapshotPaths | None = None,
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
        repository_snapshot=repository_snapshot,
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
