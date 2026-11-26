# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2060: four routes from a crate outside the scan back into a member hide an indirect edge.

Each test runs `cargo run`: the member prints a marker, so the chain `app -> x -> base` really runs.
The rule `forbidden_dependency` with `indirect` must not PASS.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rust_repository import repository, validate
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
APP_LIB = "pub fn run() { x::f(); }\n"
HEAD = '[dependencies]\nbase-crate = "0.0.0"\n'
ROUTES = {
    "patch": (
        WORKSPACE + '[patch.crates-io]\nbase-crate = { path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "include": (
        WORKSPACE,
        "",
        'include!("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n',
    ),
    "path-attribute": (
        WORKSPACE,
        "",
        '#[path = "../../../crates/base/src/lib.rs"]\nmod b;\npub fn f() { b::make(); }\n',
    ),
}


def _marker(root: Path, offline: bool) -> str:
    command = ["cargo", "run", "-q", "--manifest-path", str(root / "crates/app/Cargo.toml")]
    done = subprocess.run(
        command + (["--offline"] if offline else []),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "CARGO_TARGET_DIR": str(root.parent / "target")},
    )
    assert done.returncode == 0, done.stderr
    return str(done.stdout)


def _scan(tmp_path: Path, release_core: Path, workspace: str, deps: str, source: str) -> Path:
    layout = {
        "crates/Cargo.toml": workspace,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": APP_LIB,
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X + deps,
        "vendor/x/src/lib.rs": source,
    }
    return repository(
        tmp_path / "repo", release_core, files=layout, components=PARTS, rules=_forbid(True)
    )


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_route_from_an_outside_crate_into_a_member_does_not_pass(
    tmp_path: Path, release_core: Path, route: str
) -> None:
    workspace, deps, source = ROUTES[route]
    root = _scan(tmp_path, release_core, workspace, deps, source)
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_git_dependency_on_the_repository_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    root = _scan(tmp_path, release_core, WORKSPACE, "", "pub fn f() { base_crate::make(); }\n")
    manifest = root / "vendor/x/Cargo.toml"
    manifest.write_text(
        manifest.read_text() + f'[dependencies]\nbase-crate = {{ git = "file://{root}/" }}\n'
    )
    _recommit(root)
    # A file URL needs no network, but Cargo may not fetch with `--offline`.
    assert _marker(root, offline=False) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_registry_dependency_that_a_patch_sends_to_a_member_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE + '[patch.crates-io]\nbase-crate = { path = "base" }\n',
        "crates/app/Cargo.toml": _app('base-crate = "0.0.0"\n'),
        "crates/app/src/lib.rs": "pub fn run() { base_crate::make(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
    }
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=PARTS, rules=_forbid(False)
    )
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]
