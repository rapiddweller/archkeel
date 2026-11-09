# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #880: `ARCHKEEL_CODE_DIGEST` covers every source input of the native workspace.

Consumer: the host, which reads the digest of a reply to know which collector code made it and
to invalidate its caches. A source file that the digest misses lets a changed collector reuse a
stale result. The test builds copies of `native/`, so the repository's own `target/` is untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]
PACKAGE = "archkeel-typescript-collector"

# Each test builds the workspace from nothing, and one build uses every core. On 4 workers at the
# same time the builds took 45 to 75 s each and slowed the whole job, so they share one worker.
pytestmark = pytest.mark.xdist_group("test_collector_native_digest.py")


def _require_cargo() -> None:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo for the native TypeScript collector tests.")
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    # The builds below run on several workers at the same time and take no lock.
    install_rust_toolchain(cargo)


def _copy(destination: Path) -> Path:
    """Copy `native/` into `destination` without build output."""
    copy = destination / "native"
    shutil.copytree(ROOT / "native", copy, ignore=shutil.ignore_patterns("target"))
    return copy


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A copy of `native/` for one test."""
    _require_cargo()
    return _copy(tmp_path)


def _digest(workspace: Path) -> str:
    """Build the collector in `workspace` and return the digest that its build script emitted.

    Cargo hashes a path package by its path relative to the workspace root, so copies share one
    build directory. Each copy therefore gets its own target directory, or its fingerprints mix.
    """
    built = subprocess.run(
        ["cargo", "build", "--locked", "-p", PACKAGE, "--message-format=json"],
        cwd=workspace,
        env={**os.environ, "CARGO_TARGET_DIR": str(workspace.parent / "target")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    digests: set[str] = set()
    for line in built.stdout.splitlines():
        if not line.startswith("{"):
            continue
        message = json.loads(line)
        if message.get("reason") != "build-script-executed":
            continue
        digests.update(value for key, value in message["env"] if key == "ARCHKEEL_CODE_DIGEST")
    assert len(digests) == 1, built.stdout
    (digest,) = digests
    assert len(digest) == 64
    return digest


def test_an_unchanged_tree_keeps_its_digest(workspace: Path) -> None:
    first = _digest(workspace)
    second = _digest(workspace)
    assert first == second


def _edit_dependency_source(workspace: Path) -> None:
    identity = workspace / "wire/src/identity.rs"
    identity.write_text(identity.read_text() + "\n// digest test: an edit\n")


def _new_file_in_new_directory_of_dependency(workspace: Path) -> None:
    nested = workspace / "wire/src/nested"
    nested.mkdir()
    (nested / "extra.rs").write_text("pub const EXTRA: u8 = 1;\n")


def _new_file_in_new_directory_of_collector(workspace: Path) -> None:
    nested = workspace / "typescript/src/nested"
    nested.mkdir()
    (nested / "extra.rs").write_text("pub const EXTRA: u8 = 1;\n")


def _edit_cargo_lock(workspace: Path) -> None:
    lock = workspace / "Cargo.lock"
    lock.write_text(lock.read_text() + "\n# digest test: an edit\n")


@pytest.mark.parametrize(
    "change",
    [
        _edit_dependency_source,
        _new_file_in_new_directory_of_dependency,
        _new_file_in_new_directory_of_collector,
        _edit_cargo_lock,
    ],
    ids=[
        "edit-dependency-source",
        "new-directory-dependency",
        "new-directory-collector",
        "edit-cargo-lock",
    ],
)
def test_a_source_change_changes_the_digest(
    workspace: Path, change: Callable[[Path], None]
) -> None:
    before = _digest(workspace)
    change(workspace)
    after = _digest(workspace)
    assert after != before


@pytest.mark.parametrize(
    "planted",
    ["target/planted.rs", "typescript/target/planted.rs"],
    ids=["root-target", "nested-target"],
)
def test_a_source_in_a_target_directory_keeps_the_digest(tmp_path: Path, planted: str) -> None:
    """Build output is not an input: a `target` directory at any depth is skipped.

    Two fresh builds, each with its own copy: a planted file changes nothing when the same
    source edit is present in both. A file planted into an unchanged copy would prove nothing,
    because cargo does not run the build script again for a path it did not watch.
    """
    _require_cargo()
    reference = _copy(tmp_path / "reference")
    _edit_dependency_source(reference)
    with_build_output = _copy(tmp_path / "with-build-output")
    _edit_dependency_source(with_build_output)
    path = with_build_output / planted
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pub const PLANTED: u8 = 1;\n")
    assert _digest(with_build_output) == _digest(reference)
