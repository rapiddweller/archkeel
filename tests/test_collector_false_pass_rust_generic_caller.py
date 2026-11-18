# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-806: the caller owns dispatch through a generic or dynamic callee."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rust_repository import claims, component, repository, rule, statuses, validate

NO_B_TO_C = rule(
    "NO-B-TO-C",
    "forbidden_dependency",
    source="native.app.b",
    target="native.app.c",
    include_type_checking=True,
)
COMPONENTS = (
    component("base", "base_crate"),
    component("caller", "app.b"),
    component("callee", "app.a"),
    component("implementation", "app.c"),
    component("facade", "app.d"),
)
IMPL = (
    "impl std::fmt::Display for S { "
    "fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result "
    '{ f.write_str("implementation") } }\n'
)


def cargo(root: Path, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["cargo", "check", "--offline", "--manifest-path", str(root / "crates/Cargo.toml")],
        env={**os.environ, "CARGO_TARGET_DIR": str(target)},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("form", ["generic", "dyn", "reexport", "direct"])
def test_caller_cannot_pass_when_it_dispatches_to_the_third_module(
    tmp_path: Path, release_core: Path, form: str
) -> None:
    dynamic = form == "dyn"
    callee = (
        "pub fn apply(x: Box<dyn std::fmt::Display>) -> String { x.to_string() }\n"
        if dynamic
        else "pub fn apply<T: std::fmt::Display>(x: T) -> String { x.to_string() }\n"
    )
    result_type = "Box<dyn std::fmt::Display>" if dynamic else "crate::c::S"
    value = "Box::new(S)" if dynamic else "S"
    implementation = f"pub struct S;\n{IMPL}pub fn make() -> {result_type} {{ {value} }}\n"
    facade = (
        "pub use crate::c::make;\n"
        if form == "reexport"
        else f"pub fn make() -> {result_type} {{ crate::c::make() }}\n"
    )
    producer = "crate::c::make()" if form == "direct" else "crate::d::make()"
    files = {
        "crates/app/src/lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "crates/app/src/a.rs": callee,
        "crates/app/src/b.rs": f"pub fn run() -> String {{ crate::a::apply({producer}) }}\n",
        "crates/app/src/c.rs": implementation,
        "crates/app/src/d.rs": facade,
    }
    root = repository(
        tmp_path / "repo", release_core, files, components=COMPONENTS, rules=(NO_B_TO_C,)
    )
    compiled = cargo(root, tmp_path / "target")
    assert compiled.returncode == 0, compiled.stderr
    result = validate(root)
    verdict = statuses(result)["NO-B-TO-C"]
    print(f"{form}: {verdict}")
    assert verdict in {"FAIL", "UNKNOWN"}, (verdict, claims(result), result)
    assert any("native.app.b" in row and "native.app.c" in row for row in claims(result)), result
    if verdict == "UNKNOWN":
        assert "native.app.b -> native.app.c" in result["frame"]["explained"]["NO-B-TO-C"]
    if form == "direct":
        assert verdict == "FAIL", result

    with (root / "crates/app/src/lib.rs").open("a") as source:
        source.write('#[test] fn dispatches() { assert_eq!(b::run(), "implementation"); }\n')
    executed = subprocess.run(
        ["cargo", "test", "--offline", "--manifest-path", str(root / "crates/Cargo.toml")],
        env={**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert executed.returncode == 0, executed.stderr

    (root / "crates/app/src/c.rs").write_text(implementation.replace(IMPL, ""))
    mutation = cargo(root, tmp_path / "target")
    assert mutation.returncode != 0, mutation.stderr


def test_generic_callee_does_not_get_its_callers_private_impl(
    tmp_path: Path, release_core: Path
) -> None:
    no_a_to_b = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    files = {
        "crates/app/src/lib.rs": "mod a;\nmod b;\n",
        "crates/app/src/a.rs": "pub fn make<T: Default>() -> T { T::default() }\n",
        "crates/app/src/b.rs": (
            "#[derive(Default)] struct Hidden;\n"
            "pub fn trigger() { let _: Hidden = crate::a::make(); }\n"
        ),
    }
    root = repository(tmp_path / "repo", release_core, files, rules=(no_a_to_b,))
    compiled = cargo(root, tmp_path / "target")
    assert compiled.returncode == 0, compiled.stderr
    result = validate(root)
    assert statuses(result)["NO-A-TO-B"] == "PASS", result


def test_generic_caller_must_not_hide_an_impl_in_another_crate(
    tmp_path: Path, release_core: Path
) -> None:
    no_caller_to_impl = rule(
        "NO-B-TO-BASE-C",
        "forbidden_dependency",
        source="native.app.b",
        target="native.base_crate.c",
        include_type_checking=True,
    )
    implementation = f"pub struct S;\n{IMPL}pub fn make() -> S {{ S }}\n"
    files = {
        "crates/base/src/lib.rs": "pub mod c;\n",
        "crates/base/src/c.rs": implementation,
        "crates/app/src/lib.rs": "mod a;\nmod b;\nmod d;\n",
        "crates/app/src/a.rs": (
            "pub fn apply<T: std::fmt::Display>(x: T) -> String { x.to_string() }\n"
        ),
        "crates/app/src/b.rs": "pub fn run() -> String { crate::a::apply(crate::d::make()) }\n",
        "crates/app/src/d.rs": "pub use base_crate::c::make;\n",
    }
    root = repository(
        tmp_path / "repo",
        release_core,
        files,
        components=COMPONENTS,
        rules=(no_caller_to_impl,),
    )
    compiled = cargo(root, tmp_path / "target")
    assert compiled.returncode == 0, compiled.stderr
    result = validate(root)
    verdict = statuses(result)["NO-B-TO-BASE-C"]
    print(f"cross-crate: {verdict}")
    assert verdict in {"FAIL", "UNKNOWN"}, (verdict, claims(result), result)
    assert any("native.app.b" in row and "native.base_crate.c" in row for row in claims(result)), (
        result
    )
    if verdict == "UNKNOWN":
        assert (
            "native.app.b -> native.base_crate.c" in result["frame"]["explained"]["NO-B-TO-BASE-C"]
        )
    with (root / "crates/app/src/lib.rs").open("a") as source:
        source.write('#[test] fn dispatches() { assert_eq!(b::run(), "implementation"); }\n')
    executed = subprocess.run(
        ["cargo", "test", "--offline", "--manifest-path", str(root / "crates/Cargo.toml")],
        env={**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert executed.returncode == 0, executed.stderr
    (root / "crates/base/src/c.rs").write_text(implementation.replace(IMPL, ""))
    mutation = cargo(root, tmp_path / "target")
    assert mutation.returncode != 0, mutation.stderr
