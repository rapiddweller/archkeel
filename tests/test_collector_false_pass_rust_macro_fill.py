# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a glob over a module that a macro call may fill, and a cfg alias of the own crate.

Consumer: `archkeel validate`. Second review of #1173. The scan reads a module-level macro call as
safe (no hidden `pub use`) only when no other macro of its name can apply: one `macro_rules!` of
that name in the crate, no `use`, glob or `#[macro_use] extern crate` that can bring another one,
and a plain name or a `crate::` path to a module that binds the name by `use m;`. In each plant
below, `cargo check` sees the edge from `x` to `b`; the rule that forbids it may never PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, claims, repository, statuses, validate
from test_collector_false_pass_rust_extern_self import ROOT_ALIAS, SRC, B, forbid

DEP = {
    "crates/app/Cargo.toml": APP + 'dep = { path = "../../vendor/dep" }\n',
    "vendor/dep/Cargo.toml": '[package]\nname = "dep"\nversion = "0.0.0"\nedition = "2021"\n',
    "vendor/dep/src/lib.rs": "#[macro_export]\nmacro_rules! mk { () => { pub use crate::b; }; }\n",
}
LIB = "pub mod b;\npub mod m;\npub mod w;\npub mod x;\npub mod y;\n"
FILLS = "macro_rules! mk { () => { pub use crate::b; }; }\n"
HARMLESS = "macro_rules! mk { () => { pub const K: u8 = 1; }; }\nmk!();\n"
GLOB_X = "use crate::y::*;\npub fn f() { b::g(); }\n"
FAIL, HELD = {"FAIL"}, {"UNKNOWN", "FAIL"}

# name -> (files below crates/app/src, the statuses that may hold for NO-X-TO-B).
CASES = {
    "B2 the crate defines json": (
        {"y.rs": "macro_rules! json { () => { pub use crate::b; }; }\njson!();\n"},
        HELD,
    ),
    "B2 the crate defines vec": (
        {"y.rs": "macro_rules! vec { () => { pub use crate::b; }; }\nvec!();\n"},
        HELD,
    ),
    "B2 the crate defines write": (
        {"y.rs": "macro_rules! write { () => { pub use crate::b; }; }\nwrite!();\n"},
        HELD,
    ),
    "B3 a used dependency macro of the name of a harmless crate macro": (
        {"y.rs": "use dep::mk;\nmk!();\n", "w.rs": HARMLESS},
        HELD,
    ),
    "B3 a dependency macro by its path": ({"y.rs": "dep::mk!();\n", "w.rs": HARMLESS}, HELD),
    "B3 a macro_use crate and a harmless crate macro": (
        {
            "lib.rs": "#[macro_use]\nextern crate dep as dd;\n" + LIB,
            "y.rs": "mk!();\n",
            "w.rs": HARMLESS,
        },
        HELD,
    ),
    "B3 a crate path to a module that re-exports a dependency macro": (
        {"m.rs": "pub(crate) use dep::mk;\n", "y.rs": "crate::m::mk!();\n", "w.rs": HARMLESS},
        HELD,
    ),
    "B3 a dependency macro by its path in the tokens of a pass-through macro": (
        {
            "y.rs": "macro_rules! wrap { ($($t:tt)*) => { $($t)* }; }\nwrap! { dep::mk!(); }\n",
            "w.rs": HARMLESS,
        },
        HELD,
    ),
    "B3 two crate macros of one name, the first harmless": (
        {"w.rs": HARMLESS, "y.rs": FILLS + "mk!();\n"},
        HELD,
    ),
    "B4 a one-name glob through a name that another glob brings in": (
        {
            "w.rs": "pub use crate::y as m2;\n",
            "y.rs": "pub use crate::b;\n",
            "x.rs": "use crate::w::*;\nuse m2::*;\npub fn f() { b::g(); }\n",
        },
        FAIL,
    ),
    "B4 a one-name glob to an inline module of the file": (
        {
            "y.rs": "pub use crate::b;\n",
            "x.rs": "pub mod yy { pub use crate::y::*; }\nuse yy::*;\npub fn f() { b::g(); }\n",
        },
        FAIL,
    ),
    "B4 a glob through a renamed module": (
        {
            "y.rs": "pub use crate::b;\n",
            "x.rs": "use crate::y as yy;\nuse yy::*;\npub fn f() { b::g(); }\n",
        },
        FAIL,
    ),
}


def run(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    rules: tuple[dict[str, object], ...],
) -> dict[str, object]:
    base = {"lib.rs": LIB, "b.rs": B, "m.rs": "", "w.rs": "", "x.rs": GLOB_X, "y.rs": ""}
    sources = {SRC + name: text for name, text in {**base, **files}.items()}
    return validate(repository(tmp_path, core_binary, {**DEP, **sources}, rules=rules), capsys)


@pytest.mark.parametrize(("files", "expected"), CASES.values(), ids=CASES.keys())
def test_a_glob_over_a_module_that_a_macro_may_fill_never_passes(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    expected: set[str],
) -> None:
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = run(tmp_path, core_binary, capsys, files, rules)

    assert statuses(result).get("NO-X-TO-B") in expected, claims(result)


def test_a_crate_path_to_the_one_use_of_a_harmless_crate_macro_keeps_the_verdict(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The pattern of `crate::syntax::value!` in the Dart collector: no gap, no edge.
    types = "macro_rules! mk { () => { pub struct T; impl T { pub fn make() {} } }; }\n"
    files = {
        "m.rs": types + "pub(crate) use mk;\n",
        "y.rs": "crate::m::mk!();\n",
        "x.rs": "use crate::y::*;\npub fn f() { T::make(); }\n",
    }
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    result = run(tmp_path, core_binary, capsys, files, rules)

    assert statuses(result).get("NO-X-TO-B") == "PASS", claims(result)
    assert result["status"] == "PASS", claims(result)


def test_a_cfg_alias_named_like_a_dependency_is_a_named_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # B1: with the cfg off, `base_crate::b::g()` names the dependency; with it on, the module b.
    lib = "#[cfg(any())]\n" + ROOT_ALIAS.replace("me", "base_crate")
    sources = {
        SRC + "lib.rs": lib,
        SRC + "b.rs": B,
        SRC + "x.rs": "pub fn f() { base_crate::b::g(); }\n",
    }
    rules = (
        *CRATE_RULES,
        forbid("native.app.x", "native.app.b"),
        forbid("native.app.x", "native.base_crate", "NO-X-TO-BASE"),
    )
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    found = statuses(result)
    assert found.get("NO-X-TO-BASE") in HELD and found.get("NO-X-TO-B") == "UNKNOWN", claims(result)
    assert "The alias base_crate of the crate has a cfg" in str(claims(result))
