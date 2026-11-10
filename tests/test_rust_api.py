# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-327: a Rust library crate keeps a counted API and denies `unreachable_pub`."""

from __future__ import annotations

import importlib.util
import json
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

LAYERS = """
[crates.lib-one]
role = "library"
dir = "one"
[crates.lib-later]
role = "library"
dir = "later"
planned = true
"""


def scratch(tmp_path: Path, lib: str) -> Path:
    native = tmp_path / "native"
    (native / "one/src").mkdir(parents=True)
    (native / "layers.toml").write_text(LAYERS, encoding="utf-8")
    (native / "one/src/lib.rs").write_text(lib, encoding="utf-8")
    (native / "one/src/lib_tests.rs").write_text("pub fn only_a_test() {}\n", encoding="utf-8")
    return native


COUNTS = [
    ("pub fn a() {}", 1),
    ("pub(crate) fn a() {}", 0),
    ("pub(super) struct A;", 0),
    ("fn a() {} struct B;", 0),
    ("pub use a::{b, c, d};", 3),
    ("pub use a::{b, c::{d, e}};", 3),
    ("pub use a::*;", 1),
    ("pub use a::b as c;", 1),
    ("pub struct S { pub a: u8, b: u8, pub c: u8 }", 3),
    ("pub struct T(pub u8, u8);", 2),
    ("pub enum E { A, B(u8), C { x: u8 }, #[x] D }", 5),
    ("enum E { A, B }", 0),
    ('pub extern "C" fn f() {}', 1),
    ("pub const fn f() {}", 1),
    ("pub const X: u8 = 1;", 1),
    ("pub unsafe fn f() {}", 1),
    ("pub extern crate x;", 1),
    ("pub mod m;", 1),
    ("pub fn a() { let q = '\"'; } pub fn b() {}", 2),
    ("// pub fn a() {}\n/* pub fn b() {} */ pub fn c() {}", 1),
    ('pub fn a() { let s = "pub fn b() {}"; }', 1),
]


@pytest.mark.parametrize(("text", "expected"), COUNTS, ids=[case[0] for case in COUNTS])
def test_counts_the_public_api(tmp_path: Path, text: str, expected: int) -> None:
    assert api.count_public(scratch(tmp_path, text) / "one/src") == expected


def test_a_test_file_and_a_cfg_test_module_do_not_count(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#[cfg(test)]\nmod checks;\npub fn a() {}\n")
    (native / "one/src/checks.rs").write_text("pub fn b() {}\n", encoding="utf-8")
    assert api.count_public(native / "one/src") == 1


def test_a_missing_deny_fails(tmp_path: Path) -> None:
    native = scratch(tmp_path, "pub fn a() {}\n")
    assert any("unreachable_pub" in line for line in api.problems(native, {"lib-one": 1}))


def test_a_grown_and_a_shrunk_count_fail_and_the_right_count_passes(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\npub fn b() {}\n")
    assert api.problems(native, {"lib-one": 2}) == []
    assert "grew from 1" in api.problems(native, {"lib-one": 1})[0]
    assert "shrank from 3" in api.problems(native, {"lib-one": 3})[0]
    assert "no entry" in api.problems(native, {})[0]
    assert "no library" in api.problems(native, {"lib-one": 2, "ghost": 1})[0]


def test_the_real_libraries_match_their_baseline() -> None:
    native = ROOT / "native"
    baseline = json.loads((native / "api_baseline.json").read_text(encoding="utf-8"))
    assert api.problems(native, baseline) == []


def test_an_inline_test_module_adds_nothing_and_production_code_after_it_counts(
    tmp_path: Path,
) -> None:
    text = (
        "pub fn before() {}\n"
        '#[cfg(test)]\nmod tests {\n    pub fn a() { let _ = "}"; } // }\n'
        "    pub struct S { pub f: u8 }\n    mod inner { pub fn b() {} }\n}\n"
        "pub fn after() {}\n"
    )
    assert api.count_public(scratch(tmp_path, text) / "one/src") == 2
