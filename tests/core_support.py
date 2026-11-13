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


def _build(*arguments: str, timeout: int = 1200) -> None:
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [_cargo(), "build", "--locked", "-q", "-p", "archkeel-core", *arguments]
    # All workers of all test sessions on this checkout share one build lock.
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command, cwd=NATIVE, capture_output=True, text=True, check=False, timeout=timeout
        )
    assert done.returncode == 0, done.stderr


@pytest.fixture(scope="session")
def built() -> Path:
    """The directory of the debug core, in a target directory of its own."""
    target = NATIVE / "target" / "shell"
    _build("--target-dir", str(target))
    return target / "debug"


@pytest.fixture(scope="session")
def release_core() -> Path:
    """The release core: the build that a measurement of time or memory must use."""
    _build("--release")
    return NATIVE / "target" / "release" / f"archkeel-core{SUFFIX}"


@pytest.fixture(scope="session")
def core_binary() -> Path:
    """The debug core. A test names it as the core of the install for its runs."""
    target = NATIVE / "target" / "shell"
    _build("--target-dir", str(target))
    return target / "debug" / f"archkeel-core{SUFFIX}"


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
