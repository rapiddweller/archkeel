# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1048: the API list of a Rust crate counts the items that `macro_rules!` calls build.

Each plant is a crate that `cargo check` accepts, so the case is real Rust and not a text that
only the tool reads. The expected lines are exact: a count that is smaller or larger fails.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("rust_api", ROOT / "tools/rust_api.py")
assert spec and spec.loader
api = importlib.util.module_from_spec(spec)
sys.modules["rust_api"] = api
spec.loader.exec_module(api)

CARGO = shutil.which("cargo")
MAKER = (
    "macro_rules! make {\n"
    "    ($v:vis $name:ident { $($f:ident: $t:ty),* $(,)? }) => {\n"
    "        $v struct $name { $($v $f: $t),* }\n"
    "        impl $name { $($v fn $f(&self) -> &$t { &self.$f })* }\n"
    "    };\n"
    "}\n"
)
# A macro that calls itself once for each field, as the macros of `archkeel-facts` do.
MUNCHER = (
    "macro_rules! chain {\n"
    "    (@go $name:ident [$($done:tt)*]) => { pub struct $name { $($done)* } };\n"
    "    (@go $name:ident [$($done:tt)*] $f:ident : $t:ty, $($rest:tt)*) => {\n"
    "        chain!(@go $name [$($done)* pub $f: $t,] $($rest)*);\n"
    "    };\n"
    "    ($name:ident { $($f:ident : $t:ty,)* }) => { chain!(@go $name [] $($f: $t,)*); };\n"
    "}\n"
)
DEEP = 140
RECURSION = (
    '#![recursion_limit = "512"]\n'
    "macro_rules! count {\n"
    "    ($name:ident) => { pub struct $name; };\n"
    "    ($name:ident $head:tt $($rest:tt)*) => { count!($name $($rest)*); };\n"
    "}\n"
    f"count!(Deep {'x ' * DEEP});\n"
)

# name: (files by name, exact lines of the list).
PLANTS: dict[str, tuple[dict[str, str], list[str]]] = {
    "each call counts": (
        {"lib.rs": MAKER + "make!(pub A { x: u8 });\nmake!(pub B { y: u8, z: String });\n"},
        [
            "field B.y: u8",
            "field A.x: u8",
            "field B.z: String",
            "fn x(&self)->&u8",
            "fn y(&self)->&u8",
            "fn z(&self)->&String",
            "struct A",
            "struct B",
        ],
    ),
    "a passed visibility counts as written": (
        {"lib.rs": MAKER + "make!(pub(crate) Hidden { x: u8 });\nmake!(Private { y: u8 });\n"},
        [],
    ),
    "an uncalled macro adds nothing": (
        {"lib.rs": MAKER + "macro_rules! loud { () => { pub struct Loud; }; }\npub fn kept() {}\n"},
        ["fn kept()"],
    ),
    "a call counts in the module of the call": (
        {
            "macros.rs": MAKER,
            "lib.rs": "#[macro_use]\nmod macros;\npub mod shapes;\n",
            "shapes.rs": "make!(pub Round { r: u8 });\n",
        },
        [
            "field shapes::Round.r: u8",
            "fn shapes::r(&self)->&u8",
            "mod shapes",
            "struct shapes::Round",
        ],
    ),
    "a macro that calls a macro": (
        {
            "lib.rs": MAKER
            + "macro_rules! two { ($a:ident, $b:ident) => { make!(pub $a { v: u8 }); "
            "make!(pub $b { w: u8 }); }; }\ntwo!(P, Q);\n"
        },
        [
            "field P.v: u8",
            "field Q.w: u8",
            "fn v(&self)->&u8",
            "fn w(&self)->&u8",
            "struct P",
            "struct Q",
        ],
    ),
    "a macro that builds its output one field at a time": (
        {"lib.rs": MUNCHER + "chain!(R { a: u8, b: bool, });\n"},
        ["field R.a: u8", "field R.b: bool", "struct R"],
    ),
    "an enum with a repeated list": (
        {
            "lib.rs": "macro_rules! words {\n"
            "    ($n:ident { $($v:ident),+ $(,)? }) => { pub enum $n { $($v),+ } };\n}\n"
            "words!(Color { Red, Green, Blue });\n"
        },
        ["enum Color", "variant Color::Blue", "variant Color::Green", "variant Color::Red"],
    ),
    "a fragment that is not read is a gap": (
        {"lib.rs": "macro_rules! keep { ($p:pat) => { pub fn f() {} }; }\nkeep!(Some(_));\n"},
        ["unexpanded keep!: the fragment pat is not read"],
    ),
    "an exported macro is a gap": (
        {"lib.rs": "#[macro_export]\nmacro_rules! out { () => { pub struct Out; }; }\n"},
        ["unexpanded out!: an exported macro expands in other crates"],
    ),
    "two definitions of a name are a gap": (
        {
            "lib.rs": "fn a() { macro_rules! m { () => { pub struct One; } } m!(); }\n"
            "fn b() { macro_rules! m { () => { pub struct Two; } } m!(); }\n"
        },
        ["unexpanded m!: two different definitions share the name"],
    ),
    "a call nested too deep is a gap": (
        {"lib.rs": RECURSION},
        ["unexpanded count!: the call is nested too deep"],
    ),
}


PATHS = (
    "mod {m} {{\n    macro_rules! m {{ ($n:ident) => {{ pub fn $n() {{}} }} }}\n"
    "    pub(crate) use m;\n}}\n"
)
PLANTS |= {
    "a call by the path of a module": (
        {"lib.rs": PATHS.format(m="a") + "a::m!(viapath);\n"},
        ["fn viapath()"],
    ),
    "a call by a path from crate": (
        {"lib.rs": PATHS.format(m="inner") + "crate::inner::m!(deep);\n"},
        ["fn deep()"],
    ),
    "a call by a path that the tool cannot prove is a gap": (
        {"lib.rs": PATHS.format(m="a") + "use a as b;\nb::m!(aliased);\n"},
        ["unexpanded m!: the path of the call is not proven to be a path of this crate"],
    ),
    "a macro that defines a macro counts the item once": (
        {
            "lib.rs": "macro_rules! outer {\n    () => {\n        macro_rules! inner {\n"
            "            () => { pub fn gen() {} };\n        }\n        inner!();\n    };\n}\n"
            "outer!();\n"
        },
        ["fn gen()"],
    ),
    "a variable of an inner definition is a gap": (
        {
            "lib.rs": "macro_rules! outer {\n    ($f:ident) => {\n        macro_rules! inner {\n"
            "            ($n:ident) => { pub fn $n() {} };\n        }\n        inner!($f);\n"
            "    };\n}\nouter!(g);\n"
        },
        ["unexpanded outer!: the variable n is not bound here"],
    ),
    "a test variant ends at its comma": (
        {
            "lib.rs": "pub enum E { A, #[cfg(test)] B(u8), #[cfg(test)] D { x: u8 }, C }\n"
            "impl E { pub fn after_variant() {} pub fn another() {} }\n"
        },
        [
            "enum E",
            "fn after_variant()",
            "fn another()",
            "variant E::A",
            "variant E::C",
        ],
    ),
    "a test field ends at its comma": (
        {
            "lib.rs": "pub struct S { pub a: u8, #[cfg(test)] pub b: Option<(u8, u8)>, pub c: u8 }\n"
            "pub struct T(pub u8, #[cfg(test)] pub u8, pub u8);\npub fn g() {}\n"
        },
        [
            "field S.a: u8",
            "field S.c: u8",
            "field T.0: u8",
            "field T.1: u8",
            "fn g()",
            "struct S",
            "struct T",
        ],
    ),
    "a test use in a body ends at its semicolon": (
        {"lib.rs": "pub fn f() { #[cfg(test)] use std::fmt::Debug; }\npub fn g() {}\n"},
        ["fn f()", "fn g()"],
    ),
}


def write(root: Path, files: dict[str, str]) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "Cargo.toml").write_text('[package]\nname = "plant"\nedition = "2021"\n')
    for name, text in files.items():
        (root / "src" / name).write_text(text)
    return root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_list_holds_what_the_macros_build(tmp_path: Path, name: str) -> None:
    files, expected = PLANTS[name]
    root = write(tmp_path / "plant", files)
    listed = api.public_api(root / "src")
    assert listed == sorted(expected)


@pytest.mark.skipif(CARGO is None, reason="cargo is needed to prove that the plants compile")
@pytest.mark.parametrize("name", sorted(PLANTS))
def test_each_plant_is_rust_that_cargo_accepts(tmp_path: Path, name: str) -> None:
    files, _ = PLANTS[name]
    root = write(tmp_path / "plant", files)
    done = subprocess.run(
        [str(CARGO), "check", "--offline", "--lib", "--manifest-path", str(root / "Cargo.toml")],
        capture_output=True,
        text=True,
        check=False,
        env={"CARGO_TARGET_DIR": str(tmp_path / "target"), "PATH": "/usr/bin:/bin"} | _home(),
    )
    assert done.returncode == 0, done.stderr[-600:]


def _home() -> dict[str, str]:
    return {
        key: os.environ[key] for key in ("HOME", "CARGO_HOME", "RUSTUP_HOME") if key in os.environ
    }


def test_the_baseline_of_the_contract_crate_holds_the_types_that_record_builds() -> None:
    baseline = json.loads((ROOT / "native/api_baseline.json").read_text(encoding="utf-8"))
    lines = baseline["archkeel-contract"]
    assert not [line for line in lines if "$" in line]
    assert len(lines) > 800
