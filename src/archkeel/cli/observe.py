# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose configured language processes with the Core observer."""

import gc
import hashlib
import os
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.check.observation import analyze_source_snapshot
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ObservationResult, ProducerKind, ScanConfig
from archkeel.ir.codec import RawJson, observation_payload
from archkeel.ir.facts import SourceFacts
from archkeel.ir.phases import PhaseClock
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    ProtocolVersion,
)
from archkeel.ir.state_facts import VerifiedBinary

_CONFIGURED_LIMIT_REMEDY: Final = "Raise collector_output_limit_bytes in [scan]."
RUST_COLLECTOR = "archkeel-rust-collector"


# `native/hatch_build.py` puts the binaries of a platform wheel here (AD-317, AD-335), and the file
# with the SHA-256 of each binary beside it (AD-352).
_NATIVE_DIRECTORY: Final = Path(__file__).resolve().parents[1] / "_native"
_EXECUTABLE_SUFFIX: Final = sysconfig.get_config_var("EXE") or ""
DIGEST_SUFFIX: Final = ".sha256"
TYPESCRIPT_COLLECTOR: Final = "archkeel-typescript-collector"
_NATIVE_REMEDY = (
    "Install a native platform wheel: "
    "python -m pip install --only-binary=:all: --upgrade archkeel. "
    "In a source checkout, run make typescript-collector. See docs/known-limits.md for platforms."
)


def collect_cycles_less_often() -> None:
    """A one-shot command keeps its model until it exits: scan it 20 times less often (#1023)."""
    gc.set_threshold(50_000, 20, 100)


def executable(name: str, directory: Path | None = None) -> Path:
    return (directory or _NATIVE_DIRECTORY) / (name + _EXECUTABLE_SUFFIX)


def bundled_collector(name: str) -> str:
    """The path of the native collector `name` in this install.

    A platform wheel carries the binary. An sdist, an editable install and the pure wheel do not,
    so the path may not exist. Running it then gives `missing_tool` with this path in the message.
    """
    return str(executable(name))


@dataclass(frozen=True, slots=True)
class Bundled:
    """A native collector of this install: its path and the digest that its wheel recorded."""

    path: str
    digest: str


def _is_digest(text: str) -> bool:
    """The text is 64 lowercase hexadecimal digits."""
    return len(text) == 64 and set(text) <= set("0123456789abcdef")


class _VerifiedCollector(ProcessCollector):
    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        if self.pinned_digest is None:
            return CollectionError(
                CollectionErrorKind.EXECUTION_ERROR, self.argv[0], "Missing binary digest"
            )
        binary = Path(self.argv[0])
        try:
            verified = verified_binary(binary.name.removesuffix(_EXECUTABLE_SUFFIX), binary.parent)
        except OSError as error:
            return _native_error(self.argv[0], "unreadable_binary", str(error))
        except LookupError as error:
            return _native_error(self.argv[0], "missing_digest", str(error))
        except ValueError as error:
            return _native_error(self.argv[0], "digest_mismatch", str(error))
        if verified.digest != self.pinned_digest or verified.path != self.argv[0]:
            return _native_error(self.argv[0], "digest_mismatch", "The located binary changed.")
        return ProcessCollector.collect(
            replace(self, verified_binary=VerifiedBinary(verified.digest)), request
        )


def _native_error(path: str, reason: str, detail: str = "") -> CollectionError:
    return CollectionError(
        CollectionErrorKind.MISSING_TOOL,
        path,
        f"typescript_collector_{reason}: {detail} {_NATIVE_REMEDY}",
    )


@dataclass(frozen=True, slots=True)
class _UnavailableCollector:
    error: CollectionError

    def collect(self, _request: CollectionRequest) -> CollectionError:
        return self.error


def locate(name: str, directory: Path | None = None) -> Bundled | CollectionError:
    """Require the bundled executable and its recorded digest; never select another collector."""
    binary = str(executable(name, directory))
    if not os.path.isfile(binary):
        return _native_error(binary, "missing_binary", binary)
    try:
        text = Path(binary + DIGEST_SUFFIX).read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        return _native_error(binary, "missing_digest", str(error))
    if not _is_digest(text):
        return _native_error(binary, "invalid_digest")
    return Bundled(binary, f"sha256:{text}")


def verified_binary(name: str, directory: Path | None = None) -> Bundled:
    """The native binary `name` of this install, after its file has the digest that the wheel
    recorded beside it (AD-352). The core and each bundled collector use this check with the
    switch of the core (AD-390). The directory is the one of the package, never a path that the
    scanned repository or an environment variable names.

    `LookupError` without the binary or its digest file; `ValueError` for another digest.
    """
    located = locate(name, directory)
    if isinstance(located, CollectionError):
        raise LookupError(f"{executable(name, directory)} and its {DIGEST_SUFFIX} file")
    actual = "sha256:" + hashlib.sha256(Path(located.path).read_bytes()).hexdigest()
    if actual != located.digest:
        raise ValueError(
            f"{located.path} has {actual}, and its {DIGEST_SUFFIX} file records {located.digest}"
        )
    return located


def _verified_bundled(language: Language, directory: Path | None) -> Bundled | None:
    """AD-390: with the switch of the core, the bundled binary of the language after its digest
    check, or `None` for a language without one. The Rust collector always needs its digest; a
    TypeScript binary that is present needs it too, so a missing or stale digest file is an error
    and never a silent change to the Python collector. The process checks the file again just
    before the start."""
    if language == Language.RUST:
        return verified_binary(RUST_COLLECTOR, directory)
    if language == Language.TYPESCRIPT and os.path.exists(
        executable(TYPESCRIPT_COLLECTOR, directory)
    ):
        return verified_binary(TYPESCRIPT_COLLECTOR, directory)
    return None


# AD-346: the path of an `archkeel-store` binary. When it is set, the reply of a TypeScript or
# Rust collector goes through the Rust store. An opt-in for the proof of stage 1, not a default.
NATIVE_STORE = "ARCHKEEL_NATIVE_STORE"
# The languages whose replies the store checks completely (AD-346).
STORE_LANGUAGES = frozenset({Language.TYPESCRIPT, Language.RUST})


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
    pinned_digest: str | None = None,
    native_directory: Path | None = None,
    reply_sink: Callable[[bytes], None] | None = None,
    verify_bundled: bool = False,
) -> Observer:
    bundled = collector_argv is None
    native_python = bundled and language == Language.PYTHON
    native_typescript = bundled and language == Language.TYPESCRIPT
    # AD-394: TypeScript needs this install's binary and digest, with no Python fallback.
    launched = locate(TYPESCRIPT_COLLECTOR, native_directory) if native_typescript else None
    if isinstance(launched, CollectionError):
        return Observer(_UnavailableCollector(launched), producer=ProducerKind.BUNDLED)
    producer = (
        ProducerKind.BUNDLED
        if launched is not None
        else ProducerKind.PYTHON
        if bundled
        else ProducerKind.EXTERNAL
        if pinned_digest is None
        else ProducerKind.PINNED
    )
    native_rust = bundled and language == Language.RUST
    if verify_bundled and bundled:
        launched = _verified_bundled(language, native_directory) or launched
    if native_rust:
        # AD-335: the native binary is the only producer for Rust. Without it the run is a
        # `missing_tool` error that names the path, and no Python collector stands in.
        collector_argv = (bundled_collector(RUST_COLLECTOR),)
    if launched is not None:
        collector_argv = (launched.path,)
        pinned_digest = launched.digest
    if collector_argv is None:
        collector_argv = (sys.executable, "-I", "-B", "-m", f"archkeel.analyzer.{language}.entry")
    store = os.environ.get(NATIVE_STORE) if language in STORE_LANGUAGES else None
    collector = (_VerifiedCollector if launched is not None else ProcessCollector)(
        collector_argv,
        clock=clock,
        # The store reads the compressed reply of protocol 8 from any collector (AD-346).
        protocol_version=ProtocolVersion.V8 if native_typescript or native_rust or store else None,
        # A collector of this package must report the host version; a configured one need not.
        pin_adapter_version=bundled,
        store=store or None,
        pinned_digest=pinned_digest if launched is not None or not bundled else None,
        bundled=launched is not None,
        reply_sink=reply_sink,
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
        producer=producer,
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
