# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the crate edges of the Rust collector equal the oracles, on the real `native/`.

Consumer: the entry criteria of slice 5b-1. There is no second implementation of the collector,
so the oracles are other tools: `cargo metadata` for the declared dependencies, and the edge list of
`tests/test_self_native_layers.py` (AD-327) for the crates of the workspace. A used edge must be a
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
from test_self_native_layers import _layers, _metadata

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
            if target not in SYSROOT:
                found.add((source, target))
    return found


def _declared() -> set[tuple[str, str]]:
    return {
        (name.replace("-", "_"), dep.replace("-", "_"))
        for name, deps in _metadata().items()
        for dep in deps
    }


@pytest.fixture(scope="module")
def facts(rust_binary: Path) -> dict[str, Any]:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed; install Rust to run the oracle.")
    return _facts(rust_binary)


def test_the_scan_of_native_is_complete(facts: dict[str, Any]) -> None:
    assert facts["coverage"]["full_scope"] is True
    assert facts["coverage"]["gaps"] == []
    assert len(facts["files"]) == len(facts["coverage"]["selected_files"])


def test_the_edges_equal_the_declared_dependencies_of_cargo_metadata(
    facts: dict[str, Any],
) -> None:
    used, declared = _edges(facts), _declared()

    assert used - declared == set(), "a path names a crate that Cargo.toml does not declare"
    assert declared - used == set(), "Cargo.toml declares a crate that no path uses"


def test_the_crate_edges_equal_the_edge_list_of_the_layer_test(facts: dict[str, Any]) -> None:
    workspace = {name.replace("-", "_") for name in _layers()["crates"]}
    layer_edges = {
        (name.replace("-", "_"), use.replace("-", "_"))
        for name, entry in _layers()["crates"].items()
        for use in entry["may_use"]
    }

    assert {edge for edge in _edges(facts) if edge[1] in workspace} == layer_edges


def test_the_contract_requires_equal_the_layer_file() -> None:
    contract = json.loads((ROOT / "native/architecture-contract.json").read_text())
    labels = {item["label"]: item["packages"][0].split(".")[1] for item in contract["components"]}
    required = {
        (labels[item["label"]], labels[need["component"]])
        for item in contract["components"]
        for need in item.get("requires", ())
    }
    layers = {
        (name.replace("-", "_"), use.replace("-", "_"))
        for name, entry in _layers()["crates"].items()
        for use in entry["may_use"]
    }

    assert required == layers


def test_two_runs_give_the_same_bytes_also_from_another_directory(
    rust_binary: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(ROOT / "native", copy / "native", ignore=shutil.ignore_patterns("target"))

    first = _reply(rust_binary, ROOT)

    assert _reply(rust_binary, ROOT) == first
    assert _reply(rust_binary, copy) == first
