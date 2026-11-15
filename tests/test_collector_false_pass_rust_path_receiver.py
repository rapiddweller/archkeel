# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""A qualified inherent call must expose its implementation module (part of #880)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, claims, repository, rule, statuses, validate

FORBID = rule(
    "NO-APP-TO-IMPL",
    "forbidden_dependency",
    source="native.app",
    target="native.base_crate.implementation",
    include_type_checking=True,
)


def _plant(
    root: Path,
    binary: Path,
    caller: str,
    base_source: str = "pub struct S;\nmod implementation;\n",
    implementation: str = "impl crate::S { pub fn m() -> u8 { 2 } }\n",
) -> dict[str, Any]:
    sources = {
        "crates/base/src/lib.rs": base_source,
        "crates/base/src/implementation.rs": implementation,
        "crates/app/src/lib.rs": caller,
    }
    repository(root, binary, sources, rules=(*CRATE_RULES, FORBID))
    base = root / "libbase_crate.rlib"
    for command in (
        [
            "rustc",
            "--edition=2021",
            "--crate-type=lib",
            "--crate-name=base_crate",
            "crates/base/src/lib.rs",
            "-o",
            str(base),
        ],
        [
            "rustc",
            "--edition=2021",
            "--crate-type=lib",
            "--crate-name=app",
            "crates/app/src/lib.rs",
            "--extern",
            f"base_crate={base}",
            "-o",
            str(root / "libapp.rlib"),
        ],
    ):
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    return validate(root)


def test_a_path_to_an_inherent_member_is_an_edge(tmp_path: Path, release_core: Path) -> None:
    result = _plant(tmp_path, release_core, "use base_crate::S;\npub fn run() -> u8 { S::m() }\n")
    assert statuses(result).get("NO-APP-TO-IMPL") == "FAIL", claims(result)


def test_a_generic_parameter_can_shadow_an_import(tmp_path: Path, release_core: Path) -> None:
    caller = (
        "use base_crate::S;\npub trait T { fn m() -> u8; }\npub fn run<S: T>() -> u8 { S::m() }\n"
    )
    result = _plant(tmp_path, release_core, caller)
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


def test_a_conditional_inherent_member_can_leave_a_trait_call(
    tmp_path: Path, release_core: Path
) -> None:
    base = (
        "pub struct S;\npub trait T { fn m() -> u8; }\n"
        "impl T for S { fn m() -> u8 { 1 } }\nmod implementation;\n"
    )
    impl = "impl crate::S { #[cfg(any())] pub fn m() -> u8 { 2 } }\n"
    result = _plant(
        tmp_path,
        release_core,
        "use base_crate::{S, T};\npub fn run() -> u8 { S::m() }\n",
        base,
        impl,
    )
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


@pytest.mark.parametrize(
    "caller",
    [
        pytest.param("use base_crate::*;\npub fn run() -> u8 { S::m() }\n", id="glob"),
        pytest.param(
            "pub fn run() -> u8 { type Alias = base_crate::S; Alias::m() }\n",
            id="type-alias",
        ),
        pytest.param(
            "use base_crate::S;\npub fn run() -> u8 { "
            "struct S; impl S { fn m() -> u8 { 1 } } S::m() }\n",
            id="local-type",
        ),
        pytest.param(
            "use base_crate::S;\nmacro_rules! hide { () => { "
            "struct S; impl S { fn m() -> u8 { 1 } } }; }\n"
            "pub fn run() -> u8 { hide!(); S::m() }\n",
            id="macro-defines-type",
        ),
        pytest.param(
            "#[cfg(unix)] use base_crate::S;\n#[cfg(unix)] pub fn run() -> u8 { S::m() }\n",
            id="conditional-use",
        ),
        pytest.param(
            "use base_crate::S;\npub fn run() -> Vec<u8> { vec![S::m()] }\n",
            id="call-in-macro",
        ),
        pytest.param(
            "use base_crate::S;\npub fn run() -> u8 { <S>::m() }\n",
            id="qualified-self",
        ),
    ],
)
def test_an_unproved_path_keeps_its_gap(tmp_path: Path, release_core: Path, caller: str) -> None:
    result = _plant(tmp_path, release_core, caller)
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


def test_a_trait_with_the_same_member_is_refused(tmp_path: Path, release_core: Path) -> None:
    base = (
        "pub struct S;\npub trait T { fn m() -> u8; }\n"
        "impl T for S { fn m() -> u8 { 1 } }\nmod implementation;\n"
    )
    result = _plant(
        tmp_path, release_core, "use base_crate::{S, T};\npub fn run() -> u8 { S::m() }\n", base
    )
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


def test_a_generic_parameter_cannot_prove_a_same_crate_path(
    tmp_path: Path, release_core: Path
) -> None:
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    files = {
        "crates/app/src/lib.rs": "mod a; mod b; mod c;\n",
        "crates/app/src/a.rs": (
            "use crate::c::S;\npub trait T { fn m() -> u8; }\npub fn run<S: T>() -> u8 { S::m() }\n"
        ),
        "crates/app/src/b.rs": "impl crate::c::S { pub fn m() -> u8 { 2 } }\n",
        "crates/app/src/c.rs": "pub struct S;\n",
    }
    repository(tmp_path, release_core, files, rules=(*CRATE_RULES, forbidden))
    built = subprocess.run(
        ["rustc", "--edition=2021", "--crate-type=lib", "crates/app/src/lib.rs"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    result = validate(tmp_path)
    assert statuses(result).get("NO-A-TO-B") == "UNKNOWN", claims(result)
