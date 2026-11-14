# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the crate edges of the Rust collector equal the oracles, on the real `native/`.

Consumer: the entry criteria of slice 5b-1. There is no second implementation of the collector,
so the oracle is another tool: `cargo metadata` for the declared dependencies. A used edge must be a
declared dependency, and each declared dependency must be a used edge.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest
from frozen_native import frozen_root as frozen_root

ROOT = Path(__file__).parents[1]
SYSROOT = {"std", "core", "alloc"}


def _reply(binary: Path, root: Path) -> bytes:
    request = {
        "protocol_version": "8.0.0",
        "snapshot": {"root": str(root), "git_head": "0" * 40, "dirty": False},
        "scope": {"roots": ["native"], "namespace": "native"},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def _facts(binary: Path, root: Path = ROOT) -> dict[str, Any]:
    return json.loads(zlib.decompress(_reply(binary, root)))["facts"]  # type: ignore[no-any-return]


def _edges(facts: dict[str, Any]) -> set[tuple[str, str]]:
    """The (crate, crate) pairs of the import records, without the standard library."""
    found: set[tuple[str, str]] = set()
    for section in facts["sections"]:
        for record in section["records"] if section["name"] == "imports" else ():
            data = record["data"]
            source = data["source_module"].split(".")[1]
            parts = data["target_module"].split(".")
            target = parts[1] if parts[0] == "native" else parts[0]
            # The edges inside one crate are module edges (slice 5b-2c): they are no crate edge.
            if target not in SYSROOT and target != source:
                found.add((source, target))
    return found


def _metadata() -> dict[str, list[str]]:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked", "--no-deps"],
        cwd=ROOT / "native",
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    packages = json.loads(out)["packages"]
    return {p["name"]: sorted({d["name"] for d in p["dependencies"]}) for p in packages}


def _declared() -> set[tuple[str, str]]:
    return {
        (name.replace("-", "_"), dep.replace("-", "_"))
        for name, deps in _metadata().items()
        for dep in deps
    }


@pytest.fixture(scope="module")
def facts(rust_binary: Path, frozen_root: Path) -> dict[str, Any]:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed; install Rust to run the oracle.")
    return _facts(rust_binary, frozen_root)


def test_the_scan_of_native_is_complete(facts: dict[str, Any]) -> None:
    # AD-357: a method call that may reach an impl block in another module is a pair-scoped gap.
    # The host drops the gaps that the contract allows, and native/expected-gaps.json pins the
    # rest. Any other gap means the scan of native/ missed something.
    gaps = facts["coverage"]["gaps"]
    assert [gap["title"] for gap in gaps if not gap["data"].get("source_module")] == []
    assert facts["coverage"]["full_scope"] is (not gaps)
    assert len(facts["files"]) == len(facts["coverage"]["selected_files"])


def test_the_edges_equal_the_declared_dependencies_of_cargo_metadata(
    facts: dict[str, Any],
) -> None:
    used, declared = _edges(facts), _declared()

    assert used - declared == set(), "a path names a crate that Cargo.toml does not declare"
    assert declared - used == set(), "Cargo.toml declares a crate that no path uses"


def test_two_runs_give_the_same_bytes_also_from_another_directory(
    rust_binary: Path, tmp_path: Path, frozen_root: Path
) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(frozen_root / "native", copy / "native")

    first = _reply(rust_binary, frozen_root)

    assert _reply(rust_binary, frozen_root) == first
    assert _reply(rust_binary, copy) == first
