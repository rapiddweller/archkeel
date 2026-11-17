# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1276: two older forms of the Rust receiver proof gave a false FAIL.

Consumer: `archkeel validate`. Each plant is a crate `app` with the modules `a` to `e` and a
procedural macro crate `mac`. rustc compiles each plant, and the program prints the module of the
member that Rust really calls; that module is never `b`. So the core must not prove an edge
`a -> b`: `NO-A-TO-B` is PASS or UNKNOWN (a gap), never FAIL.

- P1 (AD-383, #1081): `use mac::add_variant as derive;` makes `#[derive(Debug)]` an attribute macro
  that adds the variant `N` to the enum `S`. A derive keeps the type as written only when `derive`
  is the macro of the prelude; else the type is not exact and the path `crate::c::S::N` reaches no
  member of `b`. The receiver forms of P1 (a field that the shadowed derive retypes, of `self`, of
  a typed parameter, and a type of another crate) already keep their gap on main; they stay here
  so that no later change proves them.
- P2 (#953): a same-crate path `crate::c::S::n` reaches a foreign block of `b` only when the type
  is exact and the member of the block is in every configuration. A cfg on the member, or an
  attribute macro on the type that adds a variant of the name, takes the path elsewhere.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, repository, rule, statuses, validate
from rust_repository import BASE as BASE_MANIFEST
from test_cli_native_rust_interface import _rustc_accepts

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

SRC = "crates/app/src/"
STR = "&'static str"
MAC = (
    "extern crate proc_macro;\nuse proc_macro::TokenStream;\n"
    "#[proc_macro_attribute]\n"
    "pub fn retype(_: TokenStream, _: TokenStream) -> TokenStream {\n"
    '    "pub struct W { pub s: crate::e::U }".parse().unwrap()\n}\n'
    "#[proc_macro_attribute]\n"
    "pub fn add_variant(_: TokenStream, _: TokenStream) -> TokenStream {\n"
    '    "pub enum S { A, N(u8) }".parse().unwrap()\n}\n'
)
BASE = {
    "crates/app/Cargo.toml": APP + 'mac = { path = "../../vendor/mac" }\n',
    "vendor/mac/Cargo.toml": '[package]\nname = "mac"\nversion = "0.0.0"\nedition = "2021"\n'
    "[lib]\nproc-macro = true\n",
    "vendor/mac/src/lib.rs": MAC,
    SRC + "lib.rs": "pub mod a;\nmod b;\nmod c;\nmod d;\nmod e;\n",
    SRC + "d.rs": "",
    SRC + "e.rs": "",
}
IN_B = f'impl crate::c::S {{\n    pub fn m(&self) -> {STR} {{\n        "b"\n    }}\n}}\n'
IN_E = f'pub struct U;\nimpl U {{\n    pub fn m(&self) -> {STR} {{\n        "e"\n    }}\n}}\n'
SHADOWED = (
    "use mac::retype as derive;\n#[derive(Debug)]\npub struct W {\n    pub s: crate::c::S,\n}\n"
)
ON_SELF = (
    f"{SHADOWED}impl W {{\n    pub fn f(&self) -> {STR} {{\n        self.s.m()\n    }}\n}}\n"
    f"pub fn run() -> {STR} {{\n    W {{ s: crate::e::U }}.f()\n}}\n"
)
ON_PARAM = (
    f"pub fn g(w: &crate::d::W) -> {STR} {{\n    w.s.m()\n}}\n"
    f"pub fn run() -> {STR} {{\n    g(&crate::d::W {{ s: crate::e::U }})\n}}\n"
)


def _gated_n(module: str, gate: str) -> str:
    """An `impl S` with a member `n` behind `gate` that returns `module` (P2)."""
    return (
        f"impl crate::c::S {{\n    #[cfg({gate})]\n"
        f'    pub fn n() -> {STR} {{\n        "{module}"\n    }}\n}}\n'
    )


CFG_MEMBER = {
    SRC + "c.rs": "pub struct S;\n",
    SRC + "b.rs": _gated_n("b", "any()"),
    SRC + "e.rs": _gated_n("e", "not(any())"),
    SRC + "a.rs": f"pub fn run() -> {STR} {{\n    crate::c::S::n()\n}}\n",
}
VARIANT_IN_B = (
    f"impl crate::c::S {{\n    #[allow(non_snake_case)]\n    pub fn N(_x: u8) -> {STR} {{\n"
    '        "b"\n    }\n}\n'
)
VARIANT_CALL = (
    f"pub fn run() -> {STR} {{\n    match crate::c::S::N(1) {{\n"
    '        crate::c::S::N(_) => "c",\n        crate::c::S::A => "a",\n    }\n}\n'
)


def _enum(head: str) -> dict[str, str]:
    """`S` is an enum `A` with an attribute that may add the variant `N` (P2)."""
    return {
        SRC + "c.rs": f"{head}pub enum S {{\n    A,\n}}\n",
        SRC + "b.rs": VARIANT_IN_B,
        SRC + "a.rs": VARIANT_CALL,
    }


PLANTS: dict[str, dict[str, str]] = {
    "P1 a derive shadowed by a use rewrites the field of the self receiver": {
        SRC + "c.rs": "pub struct S;\n",
        SRC + "b.rs": IN_B,
        SRC + "e.rs": IN_E,
        SRC + "a.rs": ON_SELF,
    },
    "P1 a derive shadowed by a use rewrites the field of a typed parameter": {
        SRC + "c.rs": "pub struct S;\n",
        SRC + "b.rs": IN_B,
        SRC + "d.rs": SHADOWED,
        SRC + "e.rs": IN_E,
        SRC + "a.rs": ON_PARAM,
    },
    "P2 a cfg on the member of the foreign block": CFG_MEMBER,
    "P2 an attribute macro on the enum": _enum("#[mac::add_variant]\n"),
    "P2 a cfg_attr macro on the enum": _enum("#[cfg_attr(not(any()), mac::add_variant)]\n"),
    "P1 a derive shadowed by a use adds a variant to the enum": _enum(
        "use mac::add_variant as derive;\n#[derive(Debug)]\n"
    ),
}


def _real_target(root: Path) -> str:
    """The module of the member that Rust calls: the output of `app::run()`."""
    out = root / "out"
    out.mkdir()
    common = ["rustc", "--edition", "2021", "-A", "warnings", "--out-dir", str(out)]
    macro = [*common, "--crate-type", "proc-macro", "--crate-name", "mac", "--extern"]
    done = subprocess.run(
        [*macro, "proc_macro", str(root / "vendor/mac/src/lib.rs")], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    (mac,) = [path for path in out.iterdir() if path.name.startswith("libmac.")]
    library = [*common, "--crate-type", "lib", "--crate-name", "app", "--extern", f"mac={mac}"]
    done = subprocess.run([*library, str(root / SRC / "lib.rs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    main = root / "main.rs"
    main.write_text('fn main() {\n    print!("{}", app::a::run());\n}\n')
    program = [*common, "-L", str(out), "--extern", f"app={out / 'libapp.rlib'}", str(main)]
    done = subprocess.run(program, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return subprocess.run([str(out / "main")], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_receiver_proof_gives_no_false_fail(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    to_b = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, {**BASE, **PLANTS[name]}, rules=(*CRATE_RULES, to_b))
    _rustc_accepts(root)
    assert _real_target(root) != "b"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-B") in {"PASS", "UNKNOWN"}, (name, found)


CROSS = {
    "crates/base/Cargo.toml": BASE_MANIFEST
    + '[dependencies]\nmac = { path = "../../vendor/mac" }\n',
    "vendor/mac/Cargo.toml": BASE["vendor/mac/Cargo.toml"],
    "vendor/mac/src/lib.rs": MAC,
    "crates/base/src/lib.rs": "use mac::add_variant as derive;\n#[derive(Debug)]\npub enum S {\n"
    "    A,\n}\nmod implementation;\n",
    "crates/base/src/implementation.rs": "impl crate::S {\n    #[allow(non_snake_case)]\n"
    "    pub fn N(_x: u8) -> u8 {\n        2\n    }\n}\n",
    # The match compiles only when `S::N(1)` is the variant: `fn N` gives a `u8`.
    "crates/app/src/lib.rs": "pub fn run() -> u8 {\n    match base_crate::S::N(1) {\n"
    "        base_crate::S::N(_) => 1,\n        base_crate::S::A => 0,\n    }\n}\n",
}


def test_a_shadowed_derive_on_a_type_of_another_crate_gives_no_false_fail(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1 through the type of another crate (AD-544): the derive of `base` is `mac::add_variant`,
    which adds the variant `N`; the path of `app` names the variant, not the `fn N` of
    `base::implementation`."""
    to_impl = rule(
        "NO-APP-TO-IMPL",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate.implementation",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, CROSS, rules=(*CRATE_RULES, to_impl))
    _rustc_accepts(root)
    found = statuses(validate(root, capsys))
    assert found.get("NO-APP-TO-IMPL") in {"PASS", "UNKNOWN"}, found
