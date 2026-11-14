# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: the alias of `extern crate self as name;` is read where Rust reads it, or held as a gap.

Consumer: `archkeel validate`. Review of #1173: a glob through the alias, a shadow that Rust scopes,
an alias that has the name of a sysroot crate or of a dependency, and an edition 2015 `use` path.
A rule that forbids the edge to `b` must FAIL where the edge is certain and may never PASS where
the scan cannot read the name (UNKNOWN).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import APP, BASE, CRATE_RULES, claims, repository, statuses, validate
from test_collector_false_pass_rust_extern_self import B, ROOT_ALIAS, SRC, forbid

PUB_ALIAS = "extern crate self as me;\npub mod b;\npub mod c;\nmod x;\nmod y;\n"
C = "pub struct S;\n"
MACRO_FILLED = "macro_rules! mk { () => { pub use crate::b; }; }\nmk!();\n"
USE_G = "pub fn f() -> u8 { b::g(); 1 }\n"

# name -> (files below crates/app/src, the module that holds the edge, the statuses that hold).
# FAIL: the edge is certain. HELD: the scan cannot read the name, so UNKNOWN (a FAIL is also safe).
FAIL, HELD = {"FAIL"}, {"UNKNOWN", "FAIL"}
CASES = {
    # S1: the glob goes through a module that a macro call fills.
    "S1 glob through the alias over a macro item": (
        {"lib.rs": PUB_ALIAS, "y.rs": MACRO_FILLED, "x.rs": "use me::y::*;\n" + USE_G},
        HELD,
    ),
    "S1 control glob through crate over a macro item": (
        {"lib.rs": PUB_ALIAS, "y.rs": MACRO_FILLED, "x.rs": "use crate::y::*;\n" + USE_G},
        HELD,
    ),
    # S2: a glob of the alias itself.
    "S2 use me::*": (
        {"lib.rs": PUB_ALIAS, "x.rs": "use me::*;\n" + USE_G},
        FAIL,
    ),
    # S3: a shadow is scoped, the alias is seen outside of it.
    "S3 use at the top, path in an inline module": (
        {
            "lib.rs": PUB_ALIAS,
            "x.rs": "use crate::c as me;\npub fn h() -> me::S { me::S }\n"
            "pub mod inner { pub fn f() -> u8 { me::b::g(); 1 } }\n",
        },
        HELD,
    ),
    "S3 use in an inline module, path at the top": (
        {
            "lib.rs": PUB_ALIAS,
            "x.rs": "pub mod inner { use crate::c as me; pub fn h() -> me::S { me::S } }\n"
            "pub fn f() -> u8 { me::b::g(); 1 }\n",
        },
        HELD,
    ),
    "S3 use in one function, path in another": (
        {
            "lib.rs": PUB_ALIAS,
            "x.rs": "pub fn h() -> me::S { use crate::c as me; me::S }\n"
            "pub fn f() -> u8 { me::b::g(); 1 }\n",
        },
        HELD,
    ),
    # S4: the alias wins over the name of a sysroot crate and over a dependency.
    "S4 alias named core": (
        {"lib.rs": ROOT_ALIAS.replace("me", "core"), "x.rs": "pub fn f() { core::b::g(); }\n"},
        FAIL,
    ),
    "S4 alias named alloc": (
        {"lib.rs": ROOT_ALIAS.replace("me", "alloc"), "x.rs": "pub fn f() { alloc::b::g(); }\n"},
        FAIL,
    ),
    "S4 alias named std, absolute": (
        {"lib.rs": ROOT_ALIAS.replace("me", "std"), "x.rs": "pub fn f() { ::std::b::g(); }\n"},
        FAIL,
    ),
    "S4 alias named like a dependency": (
        {
            "lib.rs": ROOT_ALIAS.replace("me", "base_crate"),
            "x.rs": "pub fn f() { base_crate::b::g(); }\n",
        },
        FAIL,
    ),
}


@pytest.mark.parametrize(("files", "expected"), CASES.values(), ids=CASES.keys())
def test_a_rule_that_forbids_the_edge_is_never_pass_where_rust_reads_it(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    expected: set[str],
) -> None:
    sources = {SRC + name: text for name, text in files.items()}
    sources[SRC + "b.rs"] = B
    sources[SRC + "c.rs"] = C
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") in expected, claims(result)


def test_an_alias_named_like_a_dependency_gives_no_edge_to_the_dependency(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "lib.rs": ROOT_ALIAS.replace("me", "base_crate"),
        "b.rs": B,
        "x.rs": "pub fn f() { base_crate::b::g(); }\n",
    }
    sources = {SRC + name: text for name, text in files.items()}
    rules = (*CRATE_RULES, forbid("native.app.x", "native.base_crate", "NO-X-TO-BASE"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-BASE") == "PASS", claims(result)


def test_an_edition_2015_use_path_starts_at_the_alias_of_the_root_not_at_a_local_module(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    local = "pub mod me { pub mod b { pub fn g() {} } }\nuse me::b::g;\npub fn f() { g(); }\n"
    sources = {
        "crates/app/Cargo.toml": APP.replace("2021", "2015"),
        "crates/base/Cargo.toml": BASE,
        SRC + "lib.rs": ROOT_ALIAS,
        SRC + "b.rs": B,
        SRC + "x.rs": local,
    }
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") == "FAIL", claims(result)


@pytest.mark.parametrize(
    "text",
    [
        "use crate::c as me;\npub fn f() -> me::S { me::S }\n",
        "mod me { pub mod b { pub fn g() {} } }\npub fn f() { me::b::g(); }\n",
        "pub fn f() { println!(\"{}\", 1); }\n",
    ],
    ids=["use in the same scope", "mod in the same scope", "an expression macro"],
)
def test_a_declaration_of_the_scope_that_holds_the_path_still_resolves_without_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    sources = {SRC + "lib.rs": PUB_ALIAS, SRC + "b.rs": B, SRC + "c.rs": C, SRC + "x.rs": text}
    sources[SRC + "y.rs"] = "pub fn p() { println!(\"y\"); }\n"
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    assert statuses(result).get("NO-X-TO-B") == "PASS", claims(result)
    assert result["status"] == "PASS", claims(result)
