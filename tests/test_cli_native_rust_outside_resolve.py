# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2105: Cargo evidence instead of a text search of outside sources.

Three routes that a text search cannot see: a `[patch]` in `.cargo/config.toml`, a procedural macro
outside the scan that reads a member with `std::fs`, and a workspace root above the scan roots that
holds the `[patch]`. Each test runs `cargo run` (the member prints a marker) and checks that the
indirect rule does not PASS.
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


def _run(directory: Path, manifest: str, *extra: str, env: dict[str, str] | None = None) -> str:
    """`cargo run` from `directory`: Cargo reads `.cargo/config.toml` from there."""
    done = subprocess.run(
        ["cargo", "run", "-q", "--offline", "--manifest-path", manifest, *extra],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "CARGO_TARGET_DIR": str(directory.parent / "target"),
            **(env or {}),
        },
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
    # Without the permission the dep-info is not read: the leaf is not proven, no PASS.
    unbuilt = outcome(root, "validate", allow_build=False)[1]
    assert unbuilt["frame"]["rules"]["FORBID"][1] != "PASS", unbuilt["frame"]["rules"]


@pytest.mark.parametrize("build", [True, False], ids=["build", "no-build"])
def test_an_optional_dependency_that_a_feature_enables_does_not_hide_an_edge(
    tmp_path: Path, release_core: Path, build: bool
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app(
            'x = { path = "../../vendor/x" }\n[features]\nbridge = ["x/bridge"]\n'
        ),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": (
            FOREIGN_X
            + '[dependencies]\nbase-crate = { path = "../../crates/base", optional = true }\n'
            + '[features]\nbridge = ["dep:base-crate"]\n'
        ),
        "vendor/x/src/lib.rs": (
            '#[cfg(feature = "bridge")]\npub fn f() { base_crate::make(); }\n'
            '#[cfg(not(feature = "bridge"))]\npub fn f() {}\n'
        ),
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml", "--features", "bridge") == "app ran\n"
    result = outcome(root, "validate", allow_build=build)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_workspace_wrapper_of_the_repository_does_not_run_without_the_permission(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app(""),
        "crates/app/src/lib.rs": "pub fn run() {}\n",
        "crates/app/src/main.rs": MARKED_MAIN,
    }
    root = _scan(tmp_path, release_core, layout)
    marker = tmp_path / "wrapper-ran"
    wrapper = root / "wrap.sh"
    wrapper.write_text(f'#!/bin/sh\ntouch "{marker}"\nexec "$@"\n')
    wrapper.chmod(0o755)
    config = root / "crates/.cargo/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f'[build]\nrustc-workspace-wrapper = "{wrapper}"\n')
    _recommit(root)
    marker.unlink(missing_ok=True)
    outcome(root, "validate", allow_build=False)
    assert not marker.exists(), "the scan ran an executable of the repository"


@pytest.mark.parametrize("header", ["env", "\\u0065nv"], ids=["plain", "escaped"])
def test_a_config_table_of_the_repository_names_no_compiler(
    tmp_path: Path, release_core: Path, header: str
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app(""),
        "crates/app/src/lib.rs": "pub fn run() {}\n",
        "crates/app/src/main.rs": MARKED_MAIN,
    }
    root = _scan(tmp_path, release_core, layout)
    marker = tmp_path / "compiler-ran"
    fake = root / "bin"
    fake.mkdir()
    (fake / "rustc").write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n')
    (fake / "rustc").chmod(0o755)
    config = root / "crates/.cargo/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        f'["{header}"]\nPATH = {{ value = "{fake}:/usr/bin:/bin", force = true }}\n'
        if header != "env"
        else f'[env]\nPATH = {{ value = "{fake}:/usr/bin:/bin", force = true }}\n'
    )
    _recommit(root)
    marker.unlink(missing_ok=True)
    outcome(root, "validate", allow_build=False)
    assert not marker.exists(), "the scan ran a compiler that the repository named"


def test_a_crate_name_that_starts_with_lib_is_proven(tmp_path: Path, release_core: Path) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('liberty = { path = "../../vendor/liberty" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { liberty::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/liberty/Cargo.toml": FOREIGN_X.replace('"x"', '"liberty"'),
        "vendor/liberty/src/lib.rs": "pub fn f() {}\n",
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] == "PASS", result["frame"]["rules"]


def test_an_include_that_only_the_release_profile_compiles_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X,
        "vendor/x/src/lib.rs": (
            "#[cfg(debug_assertions)]\npub fn f() {}\n"
            '#[cfg(not(debug_assertions))]\ninclude!("../../../crates/base/src/lib.rs");\n'
            "#[cfg(not(debug_assertions))]\npub fn f() { make(); }\n"
        ),
    }
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml", "--release") == "app ran\n"
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_an_included_file_named_like_an_output_is_still_an_input(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X,
        "vendor/x/src/lib.rs": 'include!("alias.d");\npub fn f() { make(); }\n',
    }
    root = _scan(tmp_path, release_core, layout)
    (root / "vendor/x/src/alias.d").symlink_to("../../../crates/base/src/lib.rs")
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


CFG_INCLUDE = (
    '#[cfg({cfg})]\ninclude!("../../../crates/base/src/lib.rs");\n'
    "#[cfg({cfg})]\npub fn f() {{ make(); }}\n#[cfg(not({cfg}))]\npub fn f() {{}}\n"
)


def _cfg_layout(cfg: str) -> dict[str, str]:
    return {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X,
        "vendor/x/src/lib.rs": CFG_INCLUDE.format(cfg=cfg),
    }


def test_an_include_behind_a_cfg_that_the_build_sets_later_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    root = _scan(tmp_path, release_core, _cfg_layout("foo"))
    _recommit(root)
    assert _run(root, "crates/app/Cargo.toml", env={"RUSTFLAGS": "--cfg foo"}) == "app ran\n"
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_an_include_behind_a_cfg_that_a_cargo_config_sets_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    layout = _cfg_layout("foo")
    layout["crates/.cargo/config.toml"] = '[build]\nrustflags = ["--cfg", "foo"]\n'
    root = _scan(tmp_path, release_core, layout)
    _recommit(root)
    assert _run(root / "crates", "app/Cargo.toml") == "app ran\n"
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


@pytest.mark.parametrize("cfg", ['target_os = "windows"', 'target_arch = "riscv64"'])
def test_an_include_behind_a_cfg_of_another_target_does_not_pass(
    tmp_path: Path, release_core: Path, cfg: str
) -> None:
    # Another target cannot run here, so no marker: the include is real on that target.
    root = _scan(tmp_path, release_core, _cfg_layout(cfg))
    _recommit(root)
    result = outcome(root, "validate", allow_build=True)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


@pytest.mark.parametrize("build", [True, False], ids=["build", "no-build"])
def test_a_git_dependency_with_another_name_that_includes_a_member_does_not_pass(
    tmp_path: Path, release_core: Path, build: bool
) -> None:
    layout = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": _app(""),
        "crates/app/src/lib.rs": "pub fn run() { gitdep::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
    }
    root = _scan(tmp_path, release_core, layout)
    source = tmp_path / "gitdep"
    (source / "src").mkdir(parents=True)
    (source / "Cargo.toml").write_text(FOREIGN_X.replace('"x"', '"gitdep"'))
    member = root / "crates/base/src/lib.rs"
    (source / "src/lib.rs").write_text(f'include!("{member}");\npub fn f() {{ make(); }}\n')
    git = ["git", "-C", str(source), "-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "dep"]):
        subprocess.run([*git, *step], check=True, capture_output=True)
    manifest = root / "crates/app/Cargo.toml"
    manifest.write_text(manifest.read_text() + f'gitdep = {{ git = "file://{source}" }}\n')
    # A file URL needs no network: the lock file is made without `--offline`.
    lock = ["cargo", "generate-lockfile", "--manifest-path", str(root / "crates/Cargo.toml")]
    subprocess.run(lock, check=True, capture_output=True)
    _recommit(root)
    done = subprocess.run(
        ["cargo", "run", "-q", "--manifest-path", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "CARGO_TARGET_DIR": str(root.parent / "target")},
    )
    assert done.returncode == 0 and done.stdout == "app ran\n", done.stderr
    result = outcome(root, "validate", allow_build=build)[1]
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]
