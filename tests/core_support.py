# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the core of this checkout once and run the product entry with it.

Consumer: each test that sends a real project through the default path. The shell finds the core
of its own install; a test names the binary that it built, so that a stale build of another
profile cannot answer.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from corpus_support import case, materialized
from filelock import FileLock

from archkeel.cli import core_only

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
SUFFIX = ".exe" if os.name == "nt" else ""
# A corpus case that the core decides with PASS.
HONEST = "probe/sources-test-an-honest-project-gives-pass-in-both-producers-honest"


def _cargo() -> str:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the core tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    return cargo


CACHE_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by cargo.\n"
)


def ensure_target_dir(native: Path) -> None:
    """Give `native/target` the `CACHEDIR.TAG` that cargo writes when it creates the directory.

    A test that makes the directory first for the build lock leaves it untagged, and so does an
    older checkout. The core then counts the build output as source and refuses a scan of this
    checkout over its work budget. A missing tag is added; an existing tag is kept.
    """
    target = native / "target"
    target.mkdir(exist_ok=True)
    with contextlib.suppress(FileExistsError), (target / "CACHEDIR.TAG").open("x") as tag:
        tag.write(CACHE_TAG)


COLLECTORS = ("archkeel-typescript-collector", "archkeel-rust-collector")


def _build(*arguments: str, timeout: int = 1200) -> None:
    ensure_target_dir(NATIVE)
    command = [_cargo(), "build", "--locked", "-q", "-p", "archkeel-core", *arguments]
    # All workers of all test sessions on this checkout share one build lock.
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command, cwd=NATIVE, capture_output=True, text=True, check=False, timeout=timeout
        )
    assert done.returncode == 0, done.stderr


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A private copy of the debug binaries; another worker can relink the shared build."""
    target = NATIVE / "target" / "shell"
    packages = [argument for name in COLLECTORS for argument in ("-p", name)]
    _build(*packages, "--target-dir", str(target))
    copied = tmp_path_factory.mktemp("core-binaries")
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        for name in ("archkeel-core", *COLLECTORS):
            shutil.copy2(target / "debug" / f"{name}{SUFFIX}", copied)
    return copied


@pytest.fixture(scope="session")
def release_core() -> Path:
    """The release core: the build that a measurement of time or memory must use."""
    _build("--release")
    return NATIVE / "target" / "release" / f"archkeel-core{SUFFIX}"


@pytest.fixture(scope="session")
def core_binary(built: Path) -> Path:
    """The debug core. A test names it as the core of the install for its runs."""
    return built / f"archkeel-core{SUFFIX}"


@contextlib.contextmanager
def case_root(name: str) -> Iterator[Path]:
    with materialized(case(name)) as root:
        yield root.resolve()


def run(*arguments: str) -> tuple[int, dict[str, Any]]:
    """Run the product entry in this process with `--json`; return the exit code and document."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = core_only.run([*arguments, "--json"])
    return code, json.loads(output.getvalue())
