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
from frozen_native import live_files

from archkeel.cli import core_only

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
SUFFIX = ".exe" if os.name == "nt" else ""


# AD-670: the Rust collector states no public symbol facts yet, so the self-check of native/ has
# these UNKNOWN rules and no others. The tuple is the stated goal, not a pin: it is empty when the
# goal is reached, and the expected status is then PASS (AD-1064).
NATIVE_UNKNOWN = (
    "NATIVE-INTERFACE-BOUNDARY",
    "NATIVE-NO-MODULE-CYCLES",
    "NATIVE-REQUIRES-COMPLETE",
)
# AD-1212: the edges that `docs/architecture/native.md` draws and that only the compiler proves
# (AD-1136). A scan without compiler facts holds each one as `graph.needs_facts`. A new one is added
# here; a stale edge is a `graph.drift` and is never added.
NATIVE_COMPILER_ONLY_EDGES = (
    "core-baseline->report-payload",
    "core-engine->model-terms",
    "eval-rules->model-match",
)
NATIVE_SELF_STATUS = (2, "UNKNOWN") if NATIVE_UNKNOWN else (0, "PASS")
SHELL_SELF_STATUS = (0, "PASS")


def build_environment() -> dict[str, str]:
    """The environment of every build of the shared `native/target`, the same for all of them.

    The build script reads `ARCHKEEL_VERSION` and cargo relinks the binary when it changes, so an
    exported value, or a builder with another value, would replace the core under a worker that
    runs it. The version is set here, the same as the default of a local build (#1182).
    """
    return {**os.environ, "ARCHKEEL_VERSION": "0+unknown"}


# A corpus case that the core decides with PASS.
HONEST = "probe/sources-test-an-honest-project-gives-pass-in-both-producers-honest"
# A provenance page with one marked component graph and no edge (AD-466): the graph of a contract
# with one component, or with components that do not import each other.
EMPTY_GRAPH = "# Provenance\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n```\n"


def copy_cited(root: Path, source: Path, contract: str) -> None:
    """Copy each document that the contract `contract` of `source` cites as provenance.

    AD-466: a scan reads its cited documents, so a copy of a tree that a test scans must hold them.
    """
    document = json.loads((source / contract).read_text(encoding="utf-8"))
    cited = {
        path
        for item in [*document["components"], *document["rules"]]
        for path in item.get("provenance", [])
    }
    for path in cited:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / path, root / path)


def copy_native(root: Path, source: Path = ROOT) -> None:
    """Copy `native/` of `source` without its build, and each document that its contract cites.

    Pass the frozen tree as `source` (`frozen_native.frozen_root`), which holds both.
    """
    shutil.copytree(source / "native", root / "native", ignore=shutil.ignore_patterns("target"))
    copy_cited(root, source, "native/architecture-contract.json")
    # `native/` includes files outside it (`schema/`, the driver of `tools/rustc-facts`). Without
    # them it cannot compile, and a scan of the copy loses the compiler facts (#2127).
    for name in live_files(source):
        if not name.startswith("native/"):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, root / name)


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
            command,
            cwd=NATIVE,
            env=build_environment(),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
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


def prebuilt_core(binary: Path) -> Path | None:
    """The release core when `make` built it for this session (#1205, AD-674), else None.

    `ARCHKEEL_REQUIRE_PREBUILT` is set by the test targets of the Makefile, which depend on
    `make core`, and by the PR gate, which downloads the core of main. A test then never builds
    the shared core:
    a missing binary is a failure of the gate, not a reason to rebuild it under other tests.
    """
    if not os.environ.get("ARCHKEEL_REQUIRE_PREBUILT"):
        return None
    if not binary.is_file():
        pytest.fail(f"{binary} is missing: run `make core` before the tests (#1205)")
    return binary


@pytest.fixture(scope="session")
def release_core() -> Path:
    """The release core: the build that a measurement of time or memory must use."""
    binary = NATIVE / "target" / "release" / f"archkeel-core{SUFFIX}"
    if (prebuilt := prebuilt_core(binary)) is not None:
        return prebuilt
    _build("--release", *(argument for name in COLLECTORS for argument in ("-p", name)))
    return binary


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
