# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""A path `T::m` is an edge only when no other item can have the name (#880, AD-544).

Each plant builds with rustc, and rustc does not call the member of the forbidden module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, claims, repository, rule, statuses, validate

A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
APP_TO_IMPL = rule(
    "NO-APP-TO-IMPL",
    "forbidden_dependency",
    source="native.app",
    target="native.base_crate.implementation",
    include_type_checking=True,
)
MEMBER = "impl crate::c::S { pub fn n(x: u8) -> u8 { x } }\n"
OTHER = "pub struct U;\nimpl U { pub fn n(x: u8) -> u8 { x } }\n"
HIDE = "macro_rules! hide {\n    () => {\n        use crate::d::U as S;\n    };\n}\n"
ITEMS = "macro_rules! items {\n    ($($t:tt)*) => {\n        $($t)*\n    };\n}\n"
KEEP = "use crate::c::S;\npub fn keep(_k: &S) {}\n"
GENERIC = "impl crate::c::G<{}> {{ pub fn n(x: u8) -> u8 {{ x }} }}\n"
DEFAULT = "#[derive(Default)]\npub struct S;\n"
USE_DEFAULT = "use crate::c::S;\npub fn f() -> u8 { let _v: S = S::default(); 0 }\n"


def _same_crate(root: Path, binary: Path, files: dict[str, str]) -> tuple[str | None, object]:
    sources = {
        "crates/app/src/lib.rs": "pub mod a;\npub mod b;\npub mod c;\npub mod d;\n",
        "crates/app/src/b.rs": MEMBER,
        "crates/app/src/c.rs": "pub struct S;\n",
        "crates/app/src/d.rs": OTHER,
        **{f"crates/app/src/{name}.rs": text for name, text in files.items()},
    }
    repository(root, binary, sources, rules=(*CRATE_RULES, A_TO_B))
    built = subprocess.run(
        ["rustc", "--edition=2021", "--crate-type=lib", "crates/app/src/lib.rs"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    result = validate(root)
    return statuses(result).get("NO-A-TO-B"), claims(result)


def test_a_same_crate_path_to_a_foreign_member_is_an_edge(
    tmp_path: Path, release_core: Path
) -> None:
    files = {"a": "use crate::c::S;\npub fn f() -> u8 { S::n(1) }\n"}
    status, found = _same_crate(tmp_path, release_core, files)
    assert status == "FAIL", found


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(
            {"a": HIDE + KEEP + "pub fn f() -> u8 {\n    hide!();\n    S::n(1)\n}\n"},
            id="macro-in-the-body",
        ),
        pytest.param(
            {
                "a": HIDE
                + KEEP
                + "pub fn f() -> u8 {\n    let r = S::n(1);\n    hide!();\n    r\n}\n"
            },
            id="macro-after-the-path",
        ),
        pytest.param(
            {
                "a": ITEMS
                + KEEP
                + "pub fn f() -> u8 {\n    items! {\n        use crate::d::U as S;\n    }\n"
                "    S::n(1)\n}\n"
            },
            id="macro-that-passes-items",
        ),
        pytest.param(
            {
                "a": "use crate::c::S;\npub fn f() -> u8 { let _v: S = S::n(1); 0 }\n",
                "c": "#[allow(non_camel_case_types)]\npub enum S {\n    n(u8),\n}\n",
            },
            id="enum-variant-of-the-name",
        ),
        pytest.param(
            {
                "a": USE_DEFAULT,
                "b": "impl crate::c::S { #[allow(dead_code)] fn default() -> u8 { 2 } }\n",
                "c": DEFAULT,
            },
            id="private-member",
        ),
        pytest.param(
            {
                "a": USE_DEFAULT,
                "b": "impl crate::c::S { pub(in crate::b) fn default() -> u8 { 2 } }\n",
                "c": DEFAULT,
            },
            id="member-visible-in-its-module",
        ),
        pytest.param(
            {
                "a": "use crate::c::G;\npub fn f() -> u8 { G::<u16>::n(1) }\n",
                "b": GENERIC.format("u8"),
                "c": "pub struct G<T>(pub T);\n",
                "d": GENERIC.format("u16"),
            },
            id="generic-arguments-choose-the-block",
        ),
    ],
)
def test_a_same_crate_path_that_another_item_can_take_keeps_its_gap(
    tmp_path: Path, release_core: Path, files: dict[str, str]
) -> None:
    status, found = _same_crate(tmp_path, release_core, files)
    assert status == "UNKNOWN", found


def test_a_relative_reexport_starts_at_its_module(tmp_path: Path, release_core: Path) -> None:
    one = "pub struct S;\nimpl S {\n    pub fn m(&self) -> u8 {\n        1\n    }\n}\n"
    sources = {
        "crates/base/src/lib.rs": (
            "pub mod model;\nmod hop;\nmod implementation;\npub use hop::S;\n"
        ),
        "crates/base/src/model.rs": "pub struct S;\n",
        "crates/base/src/hop.rs": "mod model;\npub use model::S;\n",
        "crates/base/src/hop/model.rs": one,
        "crates/base/src/implementation.rs": (
            "impl crate::model::S {\n    pub fn m(&self) -> u8 {\n        2\n    }\n}\n"
        ),
        "crates/app/src/lib.rs": "use base_crate::S;\npub fn run(s: &S) -> u8 {\n    s.m()\n}\n",
    }
    repository(tmp_path, release_core, sources, rules=(*CRATE_RULES, APP_TO_IMPL))
    result = validate(tmp_path)
    # The type is `hop::model::S`: no edge goes to the block of `crate::model::S`.
    assert statuses(result).get("NO-APP-TO-IMPL") != "FAIL", claims(result)
