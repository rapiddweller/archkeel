# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose configured language processes with the Core observer."""

import os
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Final, Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.check.observation import analyze_source_snapshot
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ObservationResult, ScanConfig
from archkeel.ir.codec import RawJson, observation_payload
from archkeel.ir.phases import PhaseClock
from archkeel.ir.protocol import ProtocolVersion

_CONFIGURED_LIMIT_REMEDY: Final = "Raise collector_output_limit_bytes in [scan]."
RUST_COLLECTOR = "archkeel-rust-collector"
# `native/hatch_build.py` puts the binaries of a platform wheel here (AD-317, AD-335).
_NATIVE_DIRECTORY = Path(__file__).resolve().parents[1] / "_native"
_EXECUTABLE_SUFFIX = sysconfig.get_config_var("EXE") or ""


def bundled_collector(name: str) -> str:
    """The path of the native collector `name` in this install.

    A platform wheel carries the binary. An sdist, an editable install and the pure wheel do not,
    so the path may not exist. Running it then gives `missing_tool` with this path in the message.
    """
    return str(_NATIVE_DIRECTORY / (name + _EXECUTABLE_SUFFIX))


# AD-346: the path of an `archkeel-store` binary. When it is set, the reply of a TypeScript
# collector goes through the Rust store. It is an opt-in for the proof of stage 1, not a default.
NATIVE_STORE = "ARCHKEEL_NATIVE_STORE"


def observer_for(
    language: Language,
    *,
    collector_argv: tuple[str, ...] | None = None,
    tsconfig: str = "tsconfig.json",
    output_limit_bytes: int | None = None,
    output_limit_remedy: str | None = None,
    timeout_seconds: int | None = None,
    bundler: bool = False,
    exclude_test_sources: bool = False,
    clock: PhaseClock | None = None,
) -> Observer:
    bundled = collector_argv is None
    native_python = bundled and language == Language.PYTHON
    native_typescript = bundled and language == Language.TYPESCRIPT
    native_rust = bundled and language == Language.RUST
    if native_rust:
        # AD-335: the native binary is the only producer for Rust. Without it the run is a
        # `missing_tool` error that names the path, and no Python collector stands in.
        collector_argv = (bundled_collector(RUST_COLLECTOR),)
    if collector_argv is None:
        collector_argv = (sys.executable, "-I", "-B", "-m", f"archkeel.analyzer.{language}.entry")
    store = os.environ.get(NATIVE_STORE) if language == Language.TYPESCRIPT else None
    collector = ProcessCollector(
        collector_argv,
        clock=clock,
        # The store reads the compressed reply of protocol 8 from any collector (AD-346).
        protocol_version=ProtocolVersion.V8 if native_typescript or native_rust or store else None,
        # A collector of this package must report the host version; a configured one need not.
        pin_adapter_version=bundled,
        store=store or None,
    )
    if output_limit_bytes is not None:
        collector = replace(collector, output_limit_bytes=output_limit_bytes)
    if output_limit_remedy is not None:
        collector = replace(collector, output_limit_remedy=output_limit_remedy)
    if timeout_seconds is not None:
        collector = replace(collector, timeout_seconds=timeout_seconds)
    return Observer(
        PythonProviderCollector(collector) if native_python else collector,
        tsconfig,
        bundler,
        clock,
        exclude_test_sources,
    )


def configured_observer(
    config: ScanConfig, factory: Callable[..., Observer], clock: PhaseClock | None = None
) -> Observer:
    """AD-313: `report`, `validate` and `check` observe one configured scope.

    The caller hands in `observer_for`, so a test replaces it in one place.
    """
    return factory(
        config.language,
        collector_argv=config.collector_argv,
        tsconfig=config.tsconfig or "tsconfig.json",
        output_limit_bytes=config.collector_output_limit_bytes,
        output_limit_remedy=_CONFIGURED_LIMIT_REMEDY,
        timeout_seconds=config.collector_timeout_seconds,
        bundler=config.bundler,
        exclude_test_sources=config.exclude_test_sources,
        clock=clock,
    )


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
