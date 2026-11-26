# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2105: Cargo evidence instead of a text search of outside sources.

Three routes that a text search cannot see: a `[patch]` in `.cargo/config.toml`, a procedural macro outside the scan
that reads a member with `std::fs`, and a workspace root above the scan roots that holds the `[patch]`. Each test runs
`cargo run` (the member prints a marker) and checks that the indirect rule does not PASS.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rust_repository import outcome, repository
from test_cli_native_rust_non_member_crate import (
    FOREIGN_X,
    MARKED_MAIN,
    PARTS,
    _app,
    _forbid,
    _recommit,
    pytestmark,
)

__all__ = ["pytestmark"]

WORKSPACE = '[workspace]\nmembers = ["app", "base"]\n'
CONFIG_PATCH = '[patch.crates-io]\nbase-crate = { path = "base" }\n'


def _run(directory: Path, manifest: str) -> str:
    """`cargo run` from `directory`: Cargo reads `.cargo/config.toml` from there."""
    done = subprocess.run(
        ["cargo", "run", "-q", "--offline", "--manifest-path", manifest],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "CARGO_TARGET_DIR": str(directory.parent / "target")},
    )
    assert done.returncode == 0, done.stderr
    return str(done.stdout)


def _scan(tmp_path: Path, release_core: Path, layout: dict[str, str]) -> Path:
    return repository(
        tmp_path / "repo", release_core, files=layout, components=PARTS, rules=_forbid(True)
    )


@pytest.mark.parametrize("build", [True, False], ids=["build", "no-build"])
def test_a_patch_in_a_cargo_config_does_not_hide_an_edge(
    tmp_path: Path, release_core: Path, build: bool
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/.cargo/config.toml": CONFIG_PATCH,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X + '[dependencies]\nbase-crate = "0.0.0"\n',
        "vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root / "crates", "app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=build)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


PROC_MACRO = (
    "extern crate proc_macro;\nuse proc_macro::TokenStream;\n#[proc_macro]\n"
    "pub fn bring(_: TokenStream) -> TokenStream {\n"
    '    let dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();\n'
    '    let file = format!("{dir}/../../crates/base/src/lib.rs");\n'
    "    std::fs::read_to_string(file).unwrap().parse().unwrap()\n}\n"
)


@pytest.mark.parametrize("build", [True, False], ids=["build", "no-build"])
def test_a_procedural_macro_that_reads_a_member_does_not_pass(
    tmp_path: Path, release_core: Path, build: bool
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('pm = { path = "../../vendor/pm" }\n'),
        "crates/app/src/lib.rs": "pm::bring!();\npub fn run() { make(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/pm/Cargo.toml": FOREIGN_X.replace('"x"', '"pm"') + "[lib]\nproc-macro = true\n",
        "vendor/pm/src/lib.rs": PROC_MACRO,
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=build)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


@pytest.mark.parametrize("build", [True, False], ids=["build", "no-build"])
def test_a_patch_in_a_workspace_above_the_scan_roots_does_not_hide_an_edge(
    tmp_path: Path, release_core: Path, build: bool
) -> None:
    layout = {
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X + '[dependencies]\nbase-crate = "0.0.0"\n',
        "vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    root = _scan(tmp_path, release_core, layout)
    (root / "crates/Cargo.toml").unlink()
    (root / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/app", "crates/base"]\n'
        '[patch.crates-io]\nbase-crate = { path = "crates/base" }\n'
    )
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=build)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_leaf_that_reaches_no_member_keeps_its_pass_with_the_permission_to_build(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X,
        "vendor/x/src/lib.rs": "pub fn f() {}\n",
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml") == "app ran\n"
    built = outcome(root, "validate", allow_build=True)[1]
    assert built["frame"]["rules"]["FORBID"][1] == "PASS", built["frame"]["rules"]
    # Without the permission the dep-info is not read: the leaf is not proven, so the rule does not PASS.
    unbuilt = outcome(root, "validate", allow_build=False)[1]
    assert unbuilt["frame"]["rules"]["FORBID"][1] != "PASS", unbuilt["frame"]["rules"]
