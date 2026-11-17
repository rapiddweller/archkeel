# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1276: two older forms of the Rust receiver proof gave a false FAIL.

Consumer: `archkeel validate` with the native Rust collector. Each program prints the module of the
method that it calls, so rustc gives the truth; `b` is never called, and `NO-A-TO-B` must not FAIL.

- P1: `use mac::rewrite as derive;` binds `derive` to an attribute macro, which rewrites the field
  type of `S` to `crate::e::E`. `self.x.m()` calls the `m` of `e`, not the `m` of `T` in `b`.
- P2: a same-crate path `crate::c::S::n()`. The `n` of `b` is removed by `cfg` (on the member or on
  its block); the live `n` is in `d`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, claims, repository, rule, statuses, validate
from test_collector_false_pass_rust_extern_self import SRC

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\npub fn run() -> &'static str {\n    a::run()\n}\n"
MAIN = 'fn main() {\n    print!("{}", app::run());\n}\n'
STR = "&'static str"
REWRITE = (
    "extern crate proc_macro;\nuse proc_macro::TokenStream;\n#[proc_macro_attribute]\n"
    "pub fn rewrite(_: TokenStream, _: TokenStream) -> TokenStream {\n"
    '    "pub struct S { pub x: crate::e::E }".parse().unwrap()\n}\n'
)
MAC = {
    "vendor/mac/Cargo.toml": '[package]\nname = "mac"\nversion = "0.0.0"\nedition = "2021"\n'
    "[lib]\nproc-macro = true\n",
    "vendor/mac/src/lib.rs": REWRITE,
}


def member(module: str, ty: str, name: str, form: str = "&self", attrs: str = "") -> str:
    head = f"pub fn {name}({form})" if form else f"pub fn {name}()"
    return f'impl {ty} {{\n    {attrs}{head} -> {STR} {{\n        "{module}"\n    }}\n}}\n'


PLANTS = {
    "P1 a derive that a use binds to an attribute macro": {
        "c.rs": "use mac::rewrite as derive;\n#[derive(Debug)]\npub struct S {\n    pub x: T,\n}\n"
        "pub struct T;\n",
        "b.rs": member("b", "crate::c::T", "m"),
        "e.rs": "pub struct E;\n" + member("e", "E", "m"),
        "d.rs": "",
        "a.rs": f"impl crate::c::S {{\n    pub fn f(&self) -> {STR} {{\n"
        "        self.x.m()\n    }\n}\n"
        f"pub fn run() -> {STR} {{\n    crate::c::S {{ x: crate::e::E }}.f()\n}}\n",
    },
    "P2 a path to a member that cfg removes": {
        "c.rs": "pub struct S;\n",
        "b.rs": member("b", "crate::c::S", "n", "", "#[cfg(any())]\n    "),
        "d.rs": member("d", "crate::c::S", "n", ""),
        "e.rs": "",
        "a.rs": f"pub fn run() -> {STR} {{\n    crate::c::S::n()\n}}\n",
    },
    "P2 a path to a member of a block that cfg removes": {
        "c.rs": "pub struct S;\n",
        "b.rs": "#[cfg(any())]\n" + member("b", "crate::c::S", "n", ""),
        "d.rs": member("d", "crate::c::S", "n", ""),
        "e.rs": "",
        "a.rs": f"pub fn run() -> {STR} {{\n    crate::c::S::n()\n}}\n",
    },
}


def _run(root: Path) -> str:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root / "target")}
    manifest = root / "crates/app/Cargo.toml"
    command = ["cargo", "run", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_receiver_that_the_scan_cannot_prove_gives_no_false_fail(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    sources = {SRC + file: text for file, text in PLANTS[name].items()}
    files = {
        "crates/app/Cargo.toml": APP + 'mac = { path = "../../vendor/mac" }\n',
        **MAC,
        SRC + "lib.rs": LIB,
        SRC + "main.rs": MAIN,
        **sources,
    }
    rules = (
        *CRATE_RULES,
        rule(
            "NO-A-TO-B",
            "forbidden_dependency",
            source="native.app.a",
            target="native.app.b",
            include_type_checking=True,
        ),
    )
    root = repository(tmp_path, core_binary, files, rules=rules)
    assert _run(root) in {"d", "e"}, name
    result = validate(root, capsys)

    assert statuses(result).get("NO-A-TO-B") in {"PASS", "UNKNOWN"}, (name, claims(result))
