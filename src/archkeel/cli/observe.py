# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose configured language processes with the Core observer."""

import sys
from pathlib import Path
from typing import Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.observation import analyze_source_snapshot
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ObservationResult
from archkeel.ir.codec import RawJson, observation_payload


def observer_for(
    language: Language,
    *,
    collector_argv: tuple[str, ...] | None = None,
    tsconfig: str = "tsconfig.json",
) -> Observer:
    if collector_argv is None:
        collector_argv = (
            ("archkeel-typescript",)
            if language == "typescript"
            else (sys.executable, "-B", "-m", f"archkeel.analyzer.{language}.entry")
        )
    return Observer(ProcessCollector(collector_argv), tsconfig)


def observe(
    source_root: Path,
    *,
    roots: tuple[str, ...],
    namespace: str,
    contract: str,
    git_head: str,
    dirty: bool,
    contract_root: Path,
    language: Language = "python",
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
    language: Language = "python",
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
