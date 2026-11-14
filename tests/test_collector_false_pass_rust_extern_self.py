# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: `extern crate self as name;` names the own crate, and the collector reads that edge.

Consumer: `archkeel validate`. `extern crate self as me;` in the crate root adds `me` to the
extern prelude, so `me::b::g` and `::me::b::g` in any module of the crate are an edge to `b`. A
rule that forbids the edge must FAIL, never PASS. A form that the collector does not resolve is a
named gap, never a missing edge.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import (
    APP,
    BASE,
    CRATE_RULES,
    claims,
    component,
    repository,
    rule,
    statuses,
    validate,
)

NO_REQUIRES = (component("base", "base_crate"), component("app", "app"))
SRC = "crates/app/src/"
B = "pub fn g() {}\n"
ROOT_ALIAS = "extern crate self as me;\nmod b;\nmod x;\n"
USE = "use me::b::g;\npub fn f() { g(); }\n"


def forbid(source: str, target: str, name: str = "NO-X-TO-B") -> dict[str, object]:
    return rule(
        name, "forbidden_dependency", source=source, target=target, include_type_checking=True
    )


# name -> (files below crates/app/src, the module that holds the edge, whether the edge is real).
# FAIL: the module imports `b`, so the rule that forbids it must FAIL.
FORMS = {
    "use path": ({"lib.rs": ROOT_ALIAS, "x.rs": USE}, "x"),
    "use of the module": ({"lib.rs": ROOT_ALIAS, "x.rs": "use me::b;\npub fn f() { b::g(); }\n"}, "x"),
    "use group": ({"lib.rs": ROOT_ALIAS, "x.rs": "use me::{b::g};\npub fn f() { g(); }\n"}, "x"),
    "use glob": ({"lib.rs": ROOT_ALIAS, "x.rs": "use me::b::*;\npub fn f() { g(); }\n"}, "x"),
    "use renamed": ({"lib.rs": ROOT_ALIAS, "x.rs": "use me::b::g as h;\npub fn f() { h(); }\n"}, "x"),
    "use in a function": (
        {"lib.rs": ROOT_ALIAS, "x.rs": "pub fn f() { use me::b::g; g(); }\n"},
        "x",
    ),
    "expression path": ({"lib.rs": ROOT_ALIAS, "x.rs": "pub fn f() { me::b::g(); }\n"}, "x"),
    "absolute use": (
        {"lib.rs": ROOT_ALIAS, "x.rs": "use ::me::b::g;\npub fn f() { g(); }\n"},
        "x",
    ),
    "absolute expression": (
        {"lib.rs": ROOT_ALIAS, "x.rs": "pub fn f() { ::me::b::g(); }\n"},
        "x",
    ),
    "own crate name": (
        {
            "lib.rs": ROOT_ALIAS.replace("me", "app"),
            "x.rs": "pub fn f() { ::app::b::g(); }\n",
        },
        "x",
    ),
    "own crate name in a use": (
        {
            "lib.rs": ROOT_ALIAS.replace("me", "app"),
            "x.rs": "use ::app::b::g;\npub fn f() { g(); }\n",
        },
        "x",
    ),
    "a deeper module": (
        {"lib.rs": ROOT_ALIAS, "x.rs": "mod y;\n", "x/y.rs": USE},
        "x.y",
    ),
    "an inline module": (
        {"lib.rs": ROOT_ALIAS, "x.rs": "mod inner { use me::b::g; pub fn f() { g(); } }\n"},
        "x",
    ),
    "alias in the module": (
        {"lib.rs": "mod b;\nmod x;\n", "x.rs": "extern crate self as me;\n" + USE},
        "x",
    ),
    "alias re-exported, crate path": (
        {
            "lib.rs": "pub extern crate self as me;\nmod b;\nmod x;\n",
            "x.rs": "use crate::me::b::g;\npub fn f() { g(); }\n",
        },
        "x",
    ),
    "alias re-exported, super path": (
        {
            "lib.rs": "pub extern crate self as me;\nmod b;\nmod x;\n",
            "x.rs": "use super::me::b::g;\npub fn f() { g(); }\n",
        },
        "x",
    ),
    "alias re-exported, expression path": (
        {
            "lib.rs": "pub extern crate self as me;\nmod b;\nmod x;\n",
            "x.rs": "pub fn f() { crate::me::b::g(); }\n",
        },
        "x",
    ),
}


@pytest.mark.parametrize(("files", "holder"), FORMS.values(), ids=FORMS.keys())
def test_a_rule_that_forbids_an_edge_through_the_alias_of_the_own_crate_fails(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    holder: str,
) -> None:
    sources = {SRC + name: text for name, text in files.items()}
    sources[SRC + "b.rs"] = B
    rules = (*CRATE_RULES, forbid(f"native.app.{holder}", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") == "FAIL", claims(result)


# A local name wins over the alias of the extern prelude: the edge is not the one to `b`. A run
# may resolve it (PASS) or hold it (UNKNOWN); it is never a FAIL for an edge that is not there.
SHADOWS = {
    "an inline module": "mod me { pub mod b { pub fn g() {} } }\npub fn f() { me::b::g(); }\n",
    "a use binding": "use crate::c as me;\npub fn f() -> me::S { me::S }\n",
}


@pytest.mark.parametrize("text", SHADOWS.values(), ids=SHADOWS.keys())
def test_a_local_name_that_shadows_the_alias_gives_no_edge_to_the_crate_module(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    sources = {
        SRC + "lib.rs": ROOT_ALIAS + "mod c;\n",
        SRC + "b.rs": B,
        SRC + "c.rs": "pub struct S;\n",
        SRC + "x.rs": text,
    }
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") in {"PASS", "UNKNOWN"}, claims(result)


def test_an_alias_in_a_workspace_of_two_crates_names_only_its_own_crate(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    both = {"lib.rs": ROOT_ALIAS, "b.rs": B, "x.rs": USE}
    sources = {f"crates/{crate}/src/{name}": text for crate in ("app", "base") for name, text in both.items()}
    sources["crates/app/src/x.rs"] = USE
    sources["crates/base/src/x.rs"] = "pub fn f() {}\n"
    rules = (
        *CRATE_RULES,
        forbid("native.app.x", "native.app.b", "NO-APP-X-TO-B"),
        forbid("native.app.x", "native.base_crate.b", "NO-APP-X-TO-BASE-B"),
        forbid("native.base_crate.x", "native.base_crate.b", "NO-BASE-X-TO-B"),
    )
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    found = statuses(result)
    assert found.get("NO-APP-X-TO-B") == "FAIL", claims(result)
    assert found.get("NO-APP-X-TO-BASE-B") == "PASS", claims(result)
    assert found.get("NO-BASE-X-TO-B") == "PASS", claims(result)


def test_a_manifest_edition_2015_alias_is_an_edge(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = {
        "crates/app/Cargo.toml": APP.replace("2021", "2015"),
        "crates/base/Cargo.toml": BASE,
        SRC + "lib.rs": ROOT_ALIAS,
        SRC + "b.rs": B,
        SRC + "x.rs": USE,
    }
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") == "FAIL", claims(result)
