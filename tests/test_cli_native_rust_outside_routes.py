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
LIB_INC = '[lib]\npath = "src/lib.inc"\n'
HEAD = '[dependencies]\nbase-crate = "0.0.0"\n'
ROUTES = {
    "patch": (
        WORKSPACE + '[patch.crates-io]\nbase-crate = { path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-spaced": (
        WORKSPACE + '[ patch.crates-io ]\nbase-crate = { path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-quoted": (
        WORKSPACE + '["patch".crates-io]\nbase-crate = { path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-table": (
        WORKSPACE + '[patch.crates-io.base-crate]\npath = "base"\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-alias": (
        WORKSPACE + '[patch.crates-io]\nbase-alias = { package = "base-crate", path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "include-space": (
        WORKSPACE,
        "",
        'include !("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n',
    ),
    "include-two-hops": (
        WORKSPACE,
        "",
        'include!("../../../bridge.rs");\npub fn f() { make(); }\n',
    ),
    "lib-inc": (WORKSPACE, LIB_INC, "// the target is lib.inc\n"),
    "include-inc": (WORKSPACE, "", 'include!("internal.inc");\npub fn f() { make(); }\n'),
    "patch-two-versions": (
        WORKSPACE
        + "[patch.crates-io]\n"
        + 'old = { package = "base-crate", path = "../vendor/other" }\n'
        + 'base-crate = { path = "base" }\n',
        '[dependencies]\nbase-crate = "=0.0.0"\n',
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-path-names-package": (
        WORKSPACE
        + '[patch.crates-io]\nbase-alias = { path = "package/../base", package = "base-crate" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "lib-path-into-member": (
        WORKSPACE,
        '[lib]\npath = "../../crates/base/src/lib.rs"\n',
        "// the target is the file of a member\n",
    ),
    "patch-literal-string": (
        WORKSPACE + "[patch.crates-io]\nbase-alias = { package = 'base-crate', path = \"base\" }\n",
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "include-alias": (
        WORKSPACE,
        "",
        'use std::include as load;\nload!("../../../crates/base/src/lib.rs");\n'
        "pub fn f() { make(); }\n",
    ),
    "patch-escaped-name": (
        WORKSPACE + '[patch.crates-io]\nalias = { package = "base\\u002dcrate", path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "patch-escaped-table": (
        WORKSPACE + '["pa\\u0074ch".crates-io]\nbase-crate = { path = "base" }\n',
        HEAD,
        "pub fn f() { base_crate::make(); }\n",
    ),
    "module-named-target": (
        WORKSPACE,
        "",
        "mod target;\npub fn f() { target::f(); }\n",
    ),
    "include-nested-git": (
        WORKSPACE,
        "",
        'include!(".git/bridge.rs");\npub fn f() { make(); }\n',
    ),
    "cfg-attr-bracket": (
        WORKSPACE,
        "",
        '#[cfg_attr(all(), doc = "[]", path = "../../../crates/base/src/lib.rs")]\n'
        "mod b;\npub fn f() { b::make(); }\n",
    ),
    "include-url-comment": (
        WORKSPACE,
        "",
        "use /* https://example.test */ std::include as load;\n"
        'load!("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n',
    ),
    "path-raw-string": (
        WORKSPACE,
        "",
        '#[path = r"../../../crates/base/src/lib.rs"]\nmod b;\npub fn f() { b::make(); }\n',
    ),
    "path-nested-comment": (
        WORKSPACE,
        "",
        '#[path /* outer /* inner */ outer */ = "../../../crates/base/src/lib.rs"]\n'
        "mod b;\npub fn f() { b::make(); }\n",
    ),
    "include-block-comment-line": (
        WORKSPACE,
        "",
        "/*\n// */ use std::include as load;\n"
        'load!("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n',
    ),
    "include": (
        WORKSPACE,
        "",
        'include!("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n',
    ),
    "include-computed": (
        WORKSPACE,
        "",
        'include!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../crates/base/src/lib.rs"));\n'
        "pub fn f() { make(); }\n",
    ),
    "path-attribute": (
        WORKSPACE,
        "",
        '#[path = "../../../crates/base/src/lib.rs"]\nmod b;\npub fn f() { b::make(); }\n',
    ),
}


EXTRA = {
    "include-nested-git": {
        "vendor/x/src/.git/bridge.rs": 'include!("../../../../crates/base/src/lib.rs");\n'
    },
    "module-named-target": {
        "vendor/x/src/target/mod.rs": (
            'include!("../../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n'
        )
    },
    "patch-path-names-package": {"crates/package/keep": "x\n"},
    "lib-path-into-member": {"crates/app/src/lib.rs": "pub fn run() { x::make(); }\n"},
    "include-inc": {"vendor/x/src/internal.inc": 'include!("../../../crates/base/src/lib.rs");\n'},
    "patch-two-versions": {
        "vendor/other/Cargo.toml": (
            '[package]\nname = "base-crate"\nversion = "0.0.1"\nedition = "2021"\n'
        ),
        "vendor/other/src/lib.rs": "pub fn make() {}\n",
    },
    "lib-inc": {
        "vendor/x/src/lib.inc": (
            'include!("../../../crates/base/src/lib.rs");\npub fn f() { make(); }\n'
        ),
    },
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


def _scan(
    tmp_path: Path,
    release_core: Path,
    workspace: str,
    deps: str,
    source: str,
    extra: dict[str, str],
) -> Path:
    layout = {
        "bridge.rs": 'include!("crates/base/src/lib.rs");\n',
        "crates/Cargo.toml": workspace,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": APP_LIB,
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X + deps,
        "vendor/x/src/lib.rs": source,
        **extra,
    }
    return repository(
        tmp_path / "repo", release_core, files=layout, components=PARTS, rules=_forbid(True)
    )


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_route_from_an_outside_crate_into_a_member_does_not_pass(
    tmp_path: Path, release_core: Path, route: str
) -> None:
    workspace, deps, source = ROUTES[route]
    root = _scan(tmp_path, release_core, workspace, deps, source, EXTRA.get(route, {}))
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_git_dependency_on_the_repository_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    root = _scan(tmp_path, release_core, WORKSPACE, "", "pub fn f() { base_crate::make(); }\n", {})
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


def test_an_include_inside_the_outside_crate_adds_no_gap(
    tmp_path: Path, release_core: Path
) -> None:
    source = 'include!("internal.rs");\npub fn f() { g(); }\n'
    extra = {"vendor/x/src/internal.rs": "pub fn g() {}\n"}
    root = _scan(tmp_path, release_core, WORKSPACE, "", source, extra)
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] == "PASS", result["frame"]["rules"]


def test_a_path_attribute_inside_the_outside_crate_adds_no_gap(
    tmp_path: Path, release_core: Path
) -> None:
    source = '#[path = "internal.rs"]\nmod b;\npub fn f() { b::g(); }\n'
    extra = {"vendor/x/src/internal.rs": "pub fn g() {}\n"}
    root = _scan(tmp_path, release_core, WORKSPACE, "", source, extra)
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] == "PASS", result["frame"]["rules"]


def test_a_source_that_is_a_symlink_to_a_member_file_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    root = _scan(tmp_path, release_core, WORKSPACE, "", "mod b;\npub fn f() { b::make(); }\n", {})
    (root / "vendor/x/src/b.rs").symlink_to("../../../crates/base/src/lib.rs")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    _recommit(root)
    assert _marker(root, offline=True) == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_directory_symlinks_that_lead_back_do_not_stop_the_search(
    tmp_path: Path, release_core: Path
) -> None:
    root = _scan(tmp_path, release_core, WORKSPACE, "", "pub fn f() {}\n", {})
    for name in ("loop-a", "loop-b", "loop-c"):
        (root / "vendor/x" / name).symlink_to(".")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    _recommit(root)
    result = validate(root)
    # The links lead to the crate itself: no source lies outside it, so no gap and the rule decides.
    assert result["frame"]["rules"]["FORBID"][1] == "PASS", result["frame"]["rules"]
