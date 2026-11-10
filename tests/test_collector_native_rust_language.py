# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: `Language.RUST` in the host: its profile, its config value and its default collector.

Consumer: `observer_for`, which picks the collector of a language. The bundled binary of a
platform wheel is the only producer for Rust, so an install without it reports `missing_tool`.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli import observe
from archkeel.cli.config import ConfigError, parse_config
from archkeel.cli.observe import RUST_COLLECTOR, bundled_collector, observer_for
from archkeel.ir.facts import Language, SourceProfile
from archkeel.ir.profiles import PROFILES, profile_for
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    ProtocolVersion,
    RustSettings,
    SnapshotInput,
    SourceScope,
)

REQUEST = CollectionRequest(
    SnapshotInput("/repository", "a" * 40, False),
    SourceScope(("native",), "native"),
    RustSettings(),
)


def _install_without_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    package = tmp_path / "archkeel"
    monkeypatch.setattr(observe, "_NATIVE_DIRECTORY", package / "_native")
    return package


def test_the_config_accepts_rust_and_names_it_in_the_error() -> None:
    config = parse_config(
        b'[scan]\nlanguage = "rust"\nroots = ["native"]\nnamespace = "native"\n'
        b'contract = "c.json"\n',
        "archkeel.toml",
    )
    assert config.language is Language.RUST
    with pytest.raises(ConfigError, match='"python", "dart", "typescript", or "rust"'):
        parse_config(
            b'[scan]\nlanguage = "go"\nroots = ["a"]\nnamespace = "a"\ncontract = "c"\n',
            "archkeel.toml",
        )


def test_the_profile_decides_imports_only_and_gives_unknown_for_symbols() -> None:
    profile = profile_for(SourceProfile.RUST.value)
    assert profile is PROFILES[Language.RUST]
    assert profile.source_suffix == ".rs"
    assert {"symbol_placement", "boundary_types", "call_owner", "forbidden_call_argument"} <= (
        profile.unsupported_rules
    )
    # `std` is the language's own library, so `complete_external_scope` does not name it.
    assert {"std", "core", "alloc"} == set(profile.standard_library)


def test_without_the_bundled_binary_rust_is_a_missing_tool_that_names_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _install_without_binary(monkeypatch, tmp_path)
    expected = package / "_native" / (RUST_COLLECTOR + (".exe" if os.name == "nt" else ""))
    assert Path(bundled_collector(RUST_COLLECTOR)) == expected and not expected.exists()
    request = replace(REQUEST, snapshot=SnapshotInput(str(tmp_path), "a" * 40, False))

    result = observer_for(Language.RUST).collector.collect(request)

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.MISSING_TOOL
    assert str(expected) in result.subject
    assert "could not execute" in result.message


def test_with_the_bundled_binary_it_is_the_default_collector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _install_without_binary(monkeypatch, tmp_path)
    suffix = ".exe" if os.name == "nt" else ""
    binary = package / "_native" / f"{RUST_COLLECTOR}{suffix}"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")
    binary.chmod(0o755)

    assert bundled_collector(RUST_COLLECTOR) == str(binary)
    collector = observer_for(Language.RUST).collector

    assert isinstance(collector, ProcessCollector)
    assert collector.argv == (str(binary),)
    assert collector.protocol_version is ProtocolVersion.V8
    # A bundled collector must report the host version (AD-319).
    assert collector.pin_adapter_version


def test_an_explicit_argv_wins_over_the_bundled_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_without_binary(monkeypatch, tmp_path)
    collector = observer_for(Language.RUST, collector_argv=("/opt/mine",)).collector

    assert isinstance(collector, ProcessCollector)
    assert collector.argv == ("/opt/mine",)
    assert not collector.pin_adapter_version


def test_a_git_snapshot_of_a_rust_scan_holds_the_sources_and_every_manifest(
    tmp_path: Path,
) -> None:
    from rust_repository import repository

    from archkeel.check.snapshot import _git_archive_bytes, _materialize_archive

    root = repository(tmp_path / "repo", Path("/bin/true"))
    (root / "docs/notes.txt").write_text("not a source")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "notes"], cwd=root, check=True
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    archive = _git_archive_bytes(
        root, head, roots=(PurePosixPath("crates"),), language=Language.RUST
    )
    _materialize_archive(archive, tmp_path / "out", roots=("crates",), language=Language.RUST)

    kept = sorted(
        p.relative_to(tmp_path / "out").as_posix()
        for p in (tmp_path / "out").rglob("*")
        if p.is_file()
    )
    assert kept == [
        "crates/Cargo.toml",
        "crates/app/Cargo.toml",
        "crates/app/src/lib.rs",
        "crates/base/Cargo.toml",
        "crates/base/src/lib.rs",
    ]
