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


def test_rust_uses_an_inherent_function_before_a_trait_function(tmp_path: Path) -> None:
    source = tmp_path / "precedence.rs"
    source.write_text(
        "struct S; trait T { fn m() -> u8; } "
        "impl T for S { fn m() -> u8 { 1 } } "
        "impl S { fn m() -> u8 { 2 } } "
        "fn main() { assert_eq!(S::m(), 2); assert_eq!(<S as T>::m(), 1); }\n"
    )
    binary = tmp_path / "precedence"
    built = subprocess.run(
        ["rustc", "--edition=2021", str(source), "-o", str(binary)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert ran.returncode == 0, ran.stderr


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


def test_a_gated_file_can_call_an_ungated_external_member(
    tmp_path: Path, release_core: Path
) -> None:
    sources = {
        "crates/base/src/lib.rs": "pub struct S; mod implementation;\n",
        "crates/base/src/implementation.rs": "impl crate::S { pub fn m() -> u8 { 2 } }\n",
        "crates/app/src/lib.rs": "#[cfg(not(any()))] mod caller;\n",
        "crates/app/src/caller.rs": "use base_crate::S; pub fn run() -> u8 { S::m() }\n",
    }
    repository(tmp_path, release_core, sources, rules=(*CRATE_RULES, FORBID))
    base = tmp_path / "libbase_crate.rlib"
    for args in (
        ["--crate-name=base_crate", "crates/base/src/lib.rs", "-o", str(base)],
        ["--crate-name=app", "crates/app/src/lib.rs", "--extern", f"base_crate={base}"],
    ):
        result = subprocess.run(
            ["rustc", "--edition=2021", "--crate-type=lib", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    result = validate(tmp_path)
    assert statuses(result).get("NO-APP-TO-IMPL") == "FAIL", claims(result)


def test_an_opaque_module_attribute_keeps_the_path_gap(tmp_path: Path, release_core: Path) -> None:
    repository(
        tmp_path,
        release_core,
        {
            "crates/base/src/lib.rs": "pub struct S; mod implementation;\n",
            "crates/base/src/implementation.rs": "impl crate::S { pub fn m() -> u8 { 2 } }\n",
            "crates/app/src/lib.rs": "#[cfg_attr(any(), mac::rewrite)] mod caller;\n",
            "crates/app/src/caller.rs": "use base_crate::S; pub fn run() -> u8 { S::m() }\n",
        },
        rules=(*CRATE_RULES, FORBID),
    )
    result = validate(tmp_path)
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


def test_a_gated_external_member_keeps_the_path_gap(tmp_path: Path, release_core: Path) -> None:
    repository(
        tmp_path,
        release_core,
        {
            "crates/base/src/lib.rs": (
                'pub struct S; #[cfg(feature = "other")] mod implementation;\n'
            ),
            "crates/base/src/implementation.rs": "impl crate::S { pub fn m() -> u8 { 2 } }\n",
            "crates/app/src/lib.rs": '#[cfg(feature = "dump")] mod caller;\n',
            "crates/app/src/caller.rs": "use base_crate::S; pub fn run() -> u8 { S::m() }\n",
        },
        rules=(*CRATE_RULES, FORBID),
    )
    result = validate(tmp_path)
    assert statuses(result).get("NO-APP-TO-IMPL") == "UNKNOWN", claims(result)


def test_a_path_in_a_silent_macro_of_std_is_an_edge(tmp_path: Path, release_core: Path) -> None:
    caller = "use base_crate::S;\npub fn run() -> Vec<u8> { vec![S::m()] }\n"
    result = _plant(tmp_path, release_core, caller)
    assert statuses(result).get("NO-APP-TO-IMPL") == "FAIL", claims(result)


def test_a_typed_receiver_from_another_crate_is_an_edge(tmp_path: Path, release_core: Path) -> None:
    result = _plant(
        tmp_path,
        release_core,
        "use base_crate::S;\npub fn run(s: &S) -> u8 { s.m() }\n",
        implementation="impl crate::S { pub fn m(&self) -> u8 { 2 } }\n",
    )
    assert statuses(result).get("NO-APP-TO-IMPL") == "FAIL", claims(result)


def test_a_direct_cross_crate_module_path_is_an_edge(tmp_path: Path, release_core: Path) -> None:
    result = _plant(
        tmp_path,
        release_core,
        "pub fn run(s: &base_crate::model::S) -> u8 { s.m() }\n",
        base_source="pub mod model { pub struct S; } mod implementation;\n",
        implementation="impl crate::model::S { pub fn m(&self) -> u8 { 2 } }\n",
    )
    assert statuses(result).get("NO-APP-TO-IMPL") == "FAIL", claims(result)


def test_a_typed_receiver_through_a_reexport_is_an_edge(tmp_path: Path, release_core: Path) -> None:
    sources = {
        "crates/base/src/lib.rs": "mod model; pub use model::S; mod implementation;\n",
        "crates/base/src/model.rs": "pub struct S;\n",
        "crates/base/src/implementation.rs": (
            "impl crate::model::S { pub fn m(&self) -> u8 { 2 } }\n"
        ),
        "crates/app/src/lib.rs": "use base_crate::S; pub fn run(s: &S) -> u8 { s.m() }\n",
    }
    repository(tmp_path, release_core, sources, rules=(*CRATE_RULES, FORBID))
    base = tmp_path / "libbase_crate.rlib"
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
            str(tmp_path / "libapp.rlib"),
        ],
    ):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    result = validate(tmp_path)
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
            "macro_rules! id { ($e:expr) => { $e }; }\n"
            "use base_crate::S;\npub fn run() -> u8 { id!(S::m()) }\n",
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


def test_a_conditional_import_cannot_place_a_receiver_type(
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
        "crates/app/src/lib.rs": "mod a; mod b; mod c; mod d;\n",
        "crates/app/src/a.rs": (
            "#[cfg(any())] use crate::c::S;\nuse crate::d::*;\npub fn run(s: &S) -> u8 { s.m() }\n"
        ),
        "crates/app/src/b.rs": "impl crate::c::S { pub fn m(&self) -> u8 { 2 } }\n",
        "crates/app/src/c.rs": "pub struct S;\n",
        "crates/app/src/d.rs": "pub struct S; impl S { pub fn m(&self) -> u8 { 1 } }\n",
    }
    repository(tmp_path, release_core, files, rules=(*CRATE_RULES, forbidden))
    command = ["rustc", "--edition=2021", "--crate-type=lib", "crates/app/src/lib.rs"]
    built = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    (tmp_path / "crates/app/src/b.rs").write_text("impl crate::c::S { pub fn m(&self) {} }\n")
    poisoned = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert poisoned.returncode == 0, poisoned.stderr
    (tmp_path / "crates/app/src/b.rs").write_text(files["crates/app/src/b.rs"])
    result = validate(tmp_path)
    assert statuses(result).get("NO-A-TO-B") == "UNKNOWN", claims(result)
