# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1196: a method that a macro call defines gives a pair gap, never a silent PASS.

Consumer: `archkeel validate` with the native Rust collector. `c` holds the type `S`; `a` calls
`m` on an `S`. In each plant the live `m` comes from a macro call in `d` (an `impl` block that the
scan does not see), and a plain `m` in `b` is removed by `cfg` or is absent. rustc accepts each
plant, and it calls the `m` of `d`, so `NO-A-TO-D` is UNKNOWN or FAIL, never PASS. A
`macro_rules!` body makes no new identifier: a `fn $name` takes one of the call tokens, so the twin
whose call names another method keeps its PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, claims, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts
from test_collector_false_pass_rust_extern_self import SRC

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "mod a;\nmod b;\nmod c;\nmod d;\n"
TYPE = "pub struct S;\n"
NAMED = (
    "macro_rules! mk {\n    ($n:ident) => {\n"
    "        impl crate::c::S {\n            pub fn $n(&self) {}\n        }\n    };\n}\n"
)
LITERAL = (
    "macro_rules! mk {\n    () => {\n"
    "        impl crate::c::S {\n            pub fn m(&self) {}\n        }\n    };\n}\nmk!();\n"
)
# The receiver is bound twice, so the scan cannot prove its type (AD-524).
REBOUND = "pub fn f(s: &crate::c::S) {\n    let s = s;\n    s.m();\n}\n"
TYPED = "pub fn f(s: &crate::c::S) {\n    s.m();\n}\n"
DEAD_MODULE = (
    "#[cfg(any())]\nmod inner {\n    impl crate::c::S {\n        pub fn m(&self) {}\n    }\n}\n"
)
DEAD_MEMBER = (
    "impl crate::c::S {\n    #[cfg_attr(all(), cfg(any()))]\n    pub fn m(&self) {}\n"
    "    pub fn n(&self) {}\n}\n"
)
# #1374: a call expands one arm, so the type of one arm anchors no impl of another arm.
ARMS = (
    "use crate::c::S;\nmacro_rules! mk {\n    (type_arm) => {\n        pub struct S;\n    };\n"
    "    (method_arm) => {\n        impl S {\n            pub fn m(&self) {}\n        }\n"
    "    };\n}\n"
    "mk!(method_arm);\n"
)
# A struct that `cfg` removes declares no name: the `use` binds `S`.
DEAD_ANCHOR = (
    "use crate::c::S;\n#[cfg(any())]\npub struct S;\nmacro_rules! mk {\n    () => {\n"
    "        impl S {\n            pub fn m(&self) {}\n        }\n    };\n}\nmk!();\n"
)
CONSTANT = (
    "macro_rules! mk {\n    () => {\n        impl crate::c::S {\n"
    "            pub const C: u8 = 1;\n        }\n    };\n}\nmk!();\n"
)
HELD = {"UNKNOWN", "FAIL"}
# name: (b.rs, d.rs, a.rs, the verdicts of NO-A-TO-D)
PLANTS = {
    "inner cfg-dead module, macro with a named method": (
        DEAD_MODULE,
        NAMED + "mk!(m);\n",
        REBOUND,
        HELD,
    ),
    "cfg_attr on the member, macro with a named method": (
        DEAD_MEMBER,
        NAMED + "mk!(m);\n",
        REBOUND,
        HELD,
    ),
    "a macro with a literal method name": ("", LITERAL, REBOUND, HELD),
    "a receiver of a written type": ("", NAMED + "mk!(m);\n", TYPED, HELD),
    "a type of another arm (#1374)": ("", ARMS, REBOUND, HELD),
    "a struct that cfg removes, beside a use of the type": ("", DEAD_ANCHOR, REBOUND, HELD),
    "a path to a constant that a macro defines": (
        "",
        CONSTANT,
        "pub fn f() -> u8 {\n    crate::c::S::C\n}\n",
        HELD,
    ),
    # The twin: the call of the macro names `n`, and `a` calls the live plain `m` of `b`.
    "the macro defines another name": (
        "impl crate::c::S {\n    pub fn m(&self) {}\n}\n",
        NAMED + "mk!(n);\n",
        REBOUND,
        {"PASS"},
    ),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_method_that_a_macro_defines_gives_a_pair_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    b, d, a, expected = PLANTS[name]
    files = {"lib.rs": LIB, "c.rs": TYPE, "b.rs": b, "d.rs": d, "a.rs": a}
    rules = (
        *CRATE_RULES,
        rule(
            "NO-A-TO-D",
            "forbidden_dependency",
            source="native.app.a",
            target="native.app.d",
            include_type_checking=True,
        ),
    )
    root = repository(tmp_path, core_binary, {SRC + k: v for k, v in files.items()}, rules=rules)
    _rustc_accepts(root)
    result = validate(root, capsys)

    assert statuses(result).get("NO-A-TO-D") in expected, (name, claims(result))
