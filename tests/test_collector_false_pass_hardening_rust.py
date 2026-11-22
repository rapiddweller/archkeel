# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: a real violation in a Rust project is never PASS (see the TypeScript file).

`cargo check` accepts each plant.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rust_repository import repository, rule, statuses, validate
from test_collector_false_pass_hardening import component, needs_cargo


def rust_parts(public_b: str = "native.app.b") -> tuple[dict, ...]:
    """Two components, `a` and `b`, as two modules of the crate `app`."""
    cite = {"provenance": ["docs/target.md"]}
    return (
        {**component("a", "native.app", needs=("b",)), "packages": ["native.app.a"], **cite},
        {
            **component("b", "native.app", public=[public_b]),
            "packages": ["native.app.b"],
            **cite,
        },
    )


RUST_LIB = "pub mod a;\npub mod b;\n"
RUST_RULES = {
    "forbidden": rule(
        "A-NO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    ),
    "cycles": rule("NO-CYCLES", "no_component_cycles"),
    "boundary": rule("BOUNDARY", "interface_boundary"),
}


def rust_check(root: Path, tmp_path: Path) -> None:
    """`cargo check` must accept the plant: it is valid Rust."""
    env = {"CARGO_TARGET_DIR": str(tmp_path / "target")}
    command = ["cargo", "check", "--quiet", "--offline", "--manifest-path", "crates/Cargo.toml"]
    done = subprocess.run(
        command, cwd=root, capture_output=True, text=True, env={**os.environ, **env}, check=False
    )
    assert done.returncode == 0, done.stderr


def rust(
    tmp_path: Path,
    release_core: Path,
    files: dict[str, str],
    rules: tuple[dict, ...],
    parts: tuple[dict, ...] | None = None,
) -> tuple[Path, dict[str, str]]:
    root = repository(
        tmp_path / "repo",
        release_core,
        {"crates/app/src/lib.rs": RUST_LIB, **files},
        components=parts or rust_parts(),
        rules=rules,
        drawn="    a --> b",
    )
    rust_check(root, tmp_path)
    result = validate(root)
    return root, statuses(result)


RUST_HIDDEN = {
    "include": {
        "crates/app/src/a.rs": 'include!("b.rs");\n',
        "crates/app/src/b.rs": "pub fn g() {}\n",
    },
    "path-module": {
        "crates/app/src/a.rs": '#[path = "b.rs"]\nmod inner;\npub fn f() { inner::g(); }\n',
        "crates/app/src/b.rs": "pub fn g() {}\n",
    },
    "macro-use": {
        "crates/app/src/a.rs": "pub fn f() { crate::b::make!(); }\n",
        "crates/app/src/b.rs": "macro_rules! make { () => { () }; }\n"
        "pub(crate) use make;\npub fn g() {}\n",
    },
}


@needs_cargo
@pytest.mark.parametrize("name", sorted(RUST_HIDDEN))
def test_a_hidden_rust_edge_is_never_pass(release_core: Path, tmp_path: Path, name: str) -> None:
    _, found = rust(tmp_path, release_core, RUST_HIDDEN[name], (RUST_RULES["forbidden"],))
    assert found["A-NO-B"] in {"FAIL", "UNKNOWN"}


RUST_CONSTRUCTS = {
    "assert": "pub fn f(v: i32) { assert!(v > 0); }\n",
    "assert_eq": "pub fn f(v: i32) { assert_eq!(v, 1); }\n",
    "debug_assert": "pub fn f(v: i32) { debug_assert!(v > 0); }\n",
}


@needs_cargo
@pytest.mark.parametrize("name", sorted(RUST_CONSTRUCTS))
def test_a_forbidden_rust_construct_is_never_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    files = {"crates/app/src/a.rs": RUST_CONSTRUCTS[name], "crates/app/src/b.rs": ""}
    construct = rule(
        "CONSTRUCT",
        "forbidden_construct",
        source="native.app.a",
        constructs=["assert"],
    )
    _, found = rust(tmp_path, release_core, files, (construct,))
    assert found["CONSTRUCT"] in {"FAIL", "UNKNOWN"}


@needs_cargo
def test_a_rust_file_that_the_layout_does_not_allow_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        "crates/app/src/lib.rs": RUST_LIB + "pub mod extra;\n",
        "crates/app/src/a.rs": "",
        "crates/app/src/b.rs": "",
        "crates/app/src/extra.rs": "pub fn extra() {}\n",
    }
    layout = rule(
        "LAYOUT",
        "root_layout",
        root="native.app",
        allowed_children=["native.app.a", "native.app.b"],
    )
    _, found = rust(tmp_path, release_core, files, (layout,))
    assert found["LAYOUT"] == "FAIL"


@needs_cargo
def test_a_private_rust_import_across_components_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        "crates/app/src/b/mod.rs": "pub mod api;\npub mod secret;\n",
        "crates/app/src/b/api.rs": "pub fn ok() {}\n",
        "crates/app/src/b/secret.rs": "pub fn hidden() {}\n",
        "crates/app/src/a.rs": "use crate::b::secret::hidden;\npub fn f() { hidden(); }\n",
    }
    parts = rust_parts("native.app.b.api")
    _, found = rust(tmp_path, release_core, files, (RUST_RULES["boundary"],), parts)
    assert found["BOUNDARY"] == "FAIL"


@needs_cargo
def test_a_rust_cycle_is_never_pass(release_core: Path, tmp_path: Path) -> None:
    files = {
        "crates/app/src/a.rs": "use crate::b::g;\npub fn f() { g(); }\n",
        "crates/app/src/b.rs": "use crate::a::f;\npub fn g() { if false { f(); } }\n",
    }
    _, found = rust(tmp_path, release_core, files, (RUST_RULES["cycles"],))
    assert found["NO-CYCLES"] == "FAIL"
