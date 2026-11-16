# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1371: a macro whose expansion the scan does not read gives a gap, never a silent PASS.

Consumer: `archkeel validate` with the native Rust collector. In each plant the code that names
module `d` comes from a macro expansion that the scan does not read: a procedural macro, a
`macro_rules!` of a crate outside the scan, or a `macro_rules!` that writes a trait impl outside
the file of its type. rustc is the oracle twice: it accepts the plant, and it rejects `a.rs` when
`mod d;` is deleted, so the edge `a -> d` is real. `NO-A-TO-D` is then UNKNOWN or FAIL, never PASS.
The twins call only macros of `std`, whose expansion names no module of the crate: they keep PASS.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts
from test_collector_false_pass_rust_extern_self import SRC

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "mod a;\nmod c;\nmod d;\n"
D = "pub struct U;\nimpl U {\n    pub fn m(&self) {}\n}\npub fn f() {}\n"
PROC_MANIFEST = (
    '[package]\nname = "mac"\nversion = "0.0.0"\nedition = "2021"\n[lib]\nproc-macro = true\n'
)
PROC_SOURCE = (
    "extern crate proc_macro;\nuse proc_macro::TokenStream;\n"
    "fn code(text: &str) -> TokenStream {\n    text.parse().unwrap()\n}\n"
    '#[proc_macro]\npub fn call_d(_: TokenStream) -> TokenStream {\n    code("crate::d::f()")\n}\n'
    "#[proc_macro]\npub fn item_d(_: TokenStream) -> TokenStream {\n"
    '    code("pub fn g() { crate::d::f() }")\n}\n'
    "#[proc_macro]\npub fn rebind(_: TokenStream) -> TokenStream {\n"
    '    code("let s = &crate::d::U;")\n}\n'
    '#[proc_macro]\npub fn ty_d(_: TokenStream) -> TokenStream {\n    code("crate::d::U")\n}\n'
)
# A crate outside the scan roots, as a registry crate is: its `macro_rules!` body writes a `crate::`
# path, which rustc resolves in the crate of the call.
DEP_SOURCE = (
    "#[macro_export]\nmacro_rules! call_d {\n    () => {\n        crate::d::f()\n    };\n}\n"
    "#[macro_export]\nmacro_rules! println {\n"
    "    ($($t:tt)*) => {\n        crate::d::f()\n    };\n}\n"
)
PROC = {
    "vendor/mac/Cargo.toml": PROC_MANIFEST,
    "vendor/mac/src/lib.rs": PROC_SOURCE,
}
DEP = {
    "vendor/dep/Cargo.toml": '[package]\nname = "dep"\nversion = "0.0.0"\nedition = "2021"\n',
    "vendor/dep/src/lib.rs": DEP_SOURCE,
}
DEPENDENCIES = 'mac = { path = "../../vendor/mac" }\ndep = { path = "../../vendor/dep" }\n'
DISPLAY = (
    "macro_rules! show {\n    () => {\n        impl core::fmt::Display for crate::c::S {\n"
    "            fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {\n"
    '                f.write_str("s")\n            }\n        }\n    };\n}\nshow!();\n'
)
PASS_THROUGH = (
    "macro_rules! items {\n    ($($t:tt)*) => {\n        $($t)*\n    };\n}\nitems! {\n"
    "    impl core::fmt::Display for crate::c::S {\n"
    "        fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {\n"
    '            f.write_str("s")\n        }\n    }\n}\n'
)
NAMED = (
    "macro_rules! mk {\n    ($n:ident) => {\n        impl crate::c::S {\n"
    "            pub fn $n(&self) {}\n        }\n    };\n}\nmk!(m);\n"
)
HELD = {"UNKNOWN", "FAIL"}
# name: (a.rs, d.rs, the verdicts of NO-A-TO-D)
PLANTS = {
    "a procedural macro in a fn body, by path": ("pub fn f() {\n    mac::call_d!();\n}\n", D, HELD),
    "a procedural macro in a fn body, by use": (
        "use mac::call_d;\npub fn f() {\n    call_d!();\n}\n",
        D,
        HELD,
    ),
    "a procedural macro at module level": ("mac::item_d!();\n", D, HELD),
    "a procedural macro in a type position": ("pub fn f(_: mac::ty_d!()) {}\n", D, HELD),
    "a procedural macro that rebinds the receiver": (
        "pub fn f(s: &crate::c::S) {\n    mac::rebind!();\n    s.m();\n}\n",
        D + "impl crate::c::S {\n    pub fn n(&self) {}\n}\n",
        HELD,
    ),
    "a macro_rules! of a crate outside the scan": (
        "pub fn f() {\n    dep::call_d!();\n}\n",
        D,
        HELD,
    ),
    "a macro_rules! that writes a trait impl outside the file of its type": (
        "pub fn f(s: &crate::c::S) -> String {\n    s.to_string()\n}\n",
        DISPLAY,
        HELD,
    ),
    "a std name that a use binds to a macro of another crate": (
        'use dep::println;\npub fn f() {\n    println!("{}", 1);\n}\n',
        D,
        HELD,
    ),
    "a workspace macro whose body calls a procedural macro": (
        "use mac::call_d;\nmacro_rules! w {\n    () => {\n        call_d!()\n    };\n}\n"
        "pub fn f() {\n    w!();\n}\n",
        D,
        HELD,
    ),
    "a procedural macro in the tokens of a std macro": (
        'pub fn f() -> String {\n    format!("{:?}", mac::call_d!())\n}\n',
        D,
        HELD,
    ),
    "an impl that a macro passes through from its call tokens": (
        "pub fn f(s: &crate::c::S) -> String {\n    s.to_string()\n}\n",
        PASS_THROUGH,
        HELD,
    ),
    "a path to a method that a macro defines outside the file of its type": (
        "pub fn f(s: &crate::c::S) {\n    crate::c::S::m(s);\n}\n",
        NAMED,
        HELD,
    ),
}
# The twins: `d` is not used by `a`; `a` calls only macros of `std`.
TWINS = {
    "std macros in a fn body": (
        'pub fn f() -> String {\n    println!("{}", 1);\n    format!("{:?}", vec![1])\n}\n'
    ),
    "std macros by path": (
        'pub fn f() {\n    std::println!("{}", 1);\n    core::assert!(true);\n}\n'
    ),
}


def _rustc_rejects_a_without_d(root: Path) -> None:
    lib = root / "crates/app/src/lib.rs"
    lib.write_text(lib.read_text().replace("mod d;\n", ""))
    manifest = root / "crates/Cargo.toml"
    env = {**os.environ, "CARGO_TARGET_DIR": str(root / "target")}
    done = subprocess.run(
        ["cargo", "check", "--quiet", "--offline", "--manifest-path", str(manifest)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode != 0 and "src/a.rs" in done.stderr, done.stderr
    lib.write_text(LIB)


def _files(a: str, d: str) -> dict[str, str]:
    source = {"lib.rs": LIB, "c.rs": "pub struct S;\n", "d.rs": d, "a.rs": a}
    return {
        "crates/app/Cargo.toml": APP + DEPENDENCIES,
        **PROC,
        **DEP,
        **{SRC + name: text for name, text in source.items()},
    }


def _verdict(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> tuple[str | None, Path]:
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
    root = repository(tmp_path, core_binary, files, rules=rules)
    _rustc_accepts(root)
    return statuses(validate(root, capsys)).get("NO-A-TO-D"), root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_an_unread_macro_expansion_gives_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    a, d, expected = PLANTS[name]
    found, root = _verdict(tmp_path, core_binary, capsys, _files(a, d))
    _rustc_rejects_a_without_d(root)

    assert found in expected, (name, found)


@pytest.mark.parametrize("name", sorted(TWINS))
def test_a_std_macro_keeps_the_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    found, _ = _verdict(tmp_path, core_binary, capsys, _files(TWINS[name], D))

    assert found == "PASS", (name, found)
