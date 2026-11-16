# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1215: the two false proofs of the Rust receiver proof (AD-524) stay closed.

Consumer: `archkeel validate`. `b` holds `impl crate::c::S { fn m }`, `d` holds `U` (or `S`) with
its own `m`. rustc accepts each plant and calls the `m` of `d`:

- (a) a `use` behind `cfg(any())` names `crate::c::S`; the glob of `d` gives the live `S`. The
  core must not prove the edge `a -> b` (no FAIL); `a -> d` is a fact.
- (b) a workspace macro passes its tokens to a procedural macro that writes `let s = &crate::d::U;`.
  The core must not prove the call on the parameter `s`: `NO-A-TO-D` is never PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts
from test_collector_false_pass_rust_extern_self import SRC

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

BASE = {
    SRC + "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
    SRC + "c.rs": "pub struct S;\n",
    SRC + "b.rs": "impl crate::c::S {\n    pub fn m(&self) {}\n}\n",
}
CFG_USE = {
    SRC + "d.rs": "pub struct S;\nimpl S {\n    pub fn m(&self) {}\n}\n",
    SRC + "a.rs": "#[cfg(any())]\nuse crate::c::S;\nuse crate::d::*;\n"
    "pub fn f(s: &S) {\n    s.m();\n}\n",
}
PROC = {
    "crates/app/Cargo.toml": APP + 'mac = { path = "../../vendor/mac" }\n',
    "vendor/mac/Cargo.toml": '[package]\nname = "mac"\nversion = "0.0.0"\nedition = "2021"\n'
    "[lib]\nproc-macro = true\n",
    "vendor/mac/src/lib.rs": "extern crate proc_macro;\nuse proc_macro::TokenStream;\n"
    '#[proc_macro]\npub fn rebind(_: TokenStream) -> TokenStream {\n    "let s = &crate::d::U;"'
    ".parse().unwrap()\n}\n",
    SRC + "d.rs": "pub struct U;\nimpl U {\n    pub fn m(&self) {}\n}\n",
    SRC + "a.rs": "macro_rules! items {\n    ($($t:tt)*) => { $($t)* };\n}\n"
    "pub fn f(s: &crate::c::S) {\n    items! { mac::rebind!(1, 2); }\n    s.m();\n}\n",
}
# name: (files, the verdicts of NO-A-TO-B, the verdicts of NO-A-TO-D)
PLANTS = {
    "(a) a use behind cfg and a glob": (CFG_USE, {"UNKNOWN", "PASS"}, {"FAIL"}),
    "(b) a workspace macro that passes its tokens to a procedural macro": (
        PROC,
        {"UNKNOWN", "PASS"},
        {"UNKNOWN", "FAIL"},
    ),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_receiver_proof_gives_no_false_proof(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    files, to_b, to_d = PLANTS[name]
    rules = (
        *CRATE_RULES,
        rule(
            "NO-A-TO-B",
            "forbidden_dependency",
            source="native.app.a",
            target="native.app.b",
            include_type_checking=True,
        ),
        rule(
            "NO-A-TO-D",
            "forbidden_dependency",
            source="native.app.a",
            target="native.app.d",
            include_type_checking=True,
        ),
    )
    root = repository(tmp_path, core_binary, {**BASE, **files}, rules=rules)
    _rustc_accepts(root)
    found = statuses(validate(root, capsys))

    assert found.get("NO-A-TO-B") in to_b, (name, found)
    assert found.get("NO-A-TO-D") in to_d, (name, found)
