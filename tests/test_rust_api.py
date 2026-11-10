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


def scratch(tmp_path: Path, lib: str) -> Path:
    native = tmp_path / "native"
    (native / "one/src").mkdir(parents=True)
    (native / "one/Cargo.toml").write_text('[package]\nname = "lib-one"\n', encoding="utf-8")
    (native / "one/src/lib.rs").write_text(lib, encoding="utf-8")
    (native / "one/src/lib_tests.rs").write_text("pub fn only_a_test() {}\n", encoding="utf-8")
    return native


def measure(tmp_path: Path, label: str, lib: str) -> tuple[int, int]:
    """Return the (items, members) of a crate that holds `lib`, in its own directory."""
    return api.count_public(scratch(tmp_path / label, lib) / "one/src")


# Each case: the source text, then (items, members).
COUNTS = [
    ("pub fn a() {}", (1, 0)),
    ("pub(crate) fn a() {}", (0, 0)),
    ("pub(super) struct A;", (0, 0)),
    ("fn a() {} struct B;", (0, 0)),
    ("pub use a::{b, c, d};", (3, 0)),
    ("pub use a::{b, c::{d, e}};", (3, 0)),
    ("pub use a::*;", (1, 0)),
    ("pub use a::b as c;", (1, 0)),
    ("pub struct S { pub a: u8, b: u8, pub c: u8 }", (1, 2)),
    ("pub struct T(pub u8, u8);", (1, 1)),
    ("pub struct U;", (1, 0)),
    ("pub struct G<T: Fn(u8)>(pub T);", (1, 1)),
    ("pub struct G<T: Fn(u8) -> u8>(pub T);", (1, 1)),
    ("pub struct G<T> where T: Fn(u8) { pub a: u8 }", (1, 1)),
    ("pub struct G<T> where T: Fn(u8) -> u8 { pub a: u8 }", (1, 1)),
    ("pub struct T(pub u8) where u8: Copy;", (1, 1)),
    ("pub struct S { pub a: u8 } impl S { pub fn f() {} pub const C: u8 = 1; fn g() {} }", (3, 1)),
    ("macro_rules! m { () => { pub struct X { pub a: u8 } } }", (1, 1)),
    ("pub union V { pub a: u8, b: u8 }", (1, 1)),
    ("struct S { pub a: u8 }", (0, 0)),
    ("pub(crate) struct S { pub a: u8 }", (0, 0)),
    ("pub enum E { A, B(u8), C { x: u8 }, #[x] D }", (1, 4)),
    ("enum E { A, B }", (0, 0)),
    ('pub extern "C" fn f() {}', (1, 0)),
    ("pub const fn f() {}", (1, 0)),
    ("pub const X: u8 = 1;", (1, 0)),
    ("pub unsafe fn f() {}", (1, 0)),
    ("pub extern crate x;", (1, 0)),
    ("pub mod m;", (1, 0)),
    ("pub fn a() { let q = '\"'; } pub fn b() {}", (2, 0)),
    ("// pub fn a() {}\n/* pub fn b() {} */ pub fn c() {}", (1, 0)),
    ('pub fn a() { let s = "pub fn b() {}"; }', (1, 0)),
]


@pytest.mark.parametrize(("text", "expected"), COUNTS, ids=[case[0] for case in COUNTS])
def test_counts_the_public_api(tmp_path: Path, text: str, expected: tuple[int, int]) -> None:
    assert measure(tmp_path, "case", text) == expected


def test_a_test_file_and_a_cfg_test_module_do_not_count(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#[cfg(test)]\nmod checks;\npub fn a() {}\n")
    (native / "one/src/checks.rs").write_text("pub fn b() {}\n", encoding="utf-8")
    assert api.count_public(native / "one/src") == (1, 0)


def test_a_cfg_test_item_that_is_not_a_module_does_not_count(tmp_path: Path) -> None:
    text = (
        "#[cfg(test)]\npub fn only_in_tests() {}\n"
        "#[cfg(test)]\npub struct S { pub a: u8 }\n"
        "#[cfg(test)]\nuse a::{b, c};\n"
        "#[cfg(test)]\nconst X: u8 = { 1 };\n"
        "#[cfg(test)]\nimpl S { pub fn f() {} }\n"
        "pub fn kept() {}\n"
    )
    assert measure(tmp_path, "masked", text) == (1, 0)


def test_a_planted_pub_fn_raises_items_only(tmp_path: Path) -> None:
    before = measure(tmp_path, "before", "#![deny(unreachable_pub)]\npub struct S { pub a: u8 }\n")
    after = measure(
        tmp_path,
        "after",
        "#![deny(unreachable_pub)]\npub struct S { pub a: u8 }\npub fn planted() {}\n",
    )
    assert (after[0] - before[0], after[1] - before[1]) == (1, 0)


def test_a_planted_pub_field_raises_members_only(tmp_path: Path) -> None:
    before = measure(tmp_path, "before", "#![deny(unreachable_pub)]\npub struct S { pub a: u8 }\n")
    after = measure(
        tmp_path,
        "after",
        "#![deny(unreachable_pub)]\npub struct S { pub a: u8, pub planted: u8 }\n",
    )
    assert (after[0] - before[0], after[1] - before[1]) == (0, 1)


def test_a_removed_item_lowers_items_and_fails_the_check_until_the_baseline_changes(
    tmp_path: Path,
) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\n")
    baseline = {"lib-one": {"items": 2, "members": 0}}
    found = api.problems(native, baseline)
    assert found == [
        "lib-one has 1 public items and shrank from 2. "
        "Set lib-one items to 1 in native/api_baseline.json and name the change in the PR."
    ]
    assert api.problems(native, {"lib-one": {"items": 1, "members": 0}}) == []


def test_a_missing_deny_fails(tmp_path: Path) -> None:
    native = scratch(tmp_path, "pub fn a() {}\n")
    baseline = {"lib-one": {"items": 1, "members": 0}}
    assert any("unreachable_pub" in line for line in api.problems(native, baseline))


def test_a_grown_count_fails_per_kind_and_the_right_counts_pass(tmp_path: Path) -> None:
    native = scratch(
        tmp_path, "#![deny(unreachable_pub)]\npub struct S { pub a: u8 }\npub fn b() {}\n"
    )
    right = {"lib-one": {"items": 2, "members": 1}}
    assert api.problems(native, right) == []
    grown_members = api.problems(native, {"lib-one": {"items": 2, "members": 0}})
    assert grown_members == [
        "lib-one has 1 public members and grew from 0. "
        "Set lib-one members to 1 in native/api_baseline.json and name the change in the PR."
    ]
    assert (
        "public items and grew" in api.problems(native, {"lib-one": {"items": 1, "members": 1}})[0]
    )


def test_a_missing_or_old_format_entry_fails(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\n")
    assert "no entry with items and members" in api.problems(native, {})[0]
    assert "no entry with items and members" in api.problems(native, {"lib-one": 1})[0]
    assert "no members count" in api.problems(native, {"lib-one": {"items": 1}})[0]
    assert (
        "no library"
        in api.problems(native, {"lib-one": {"items": 1, "members": 0}, "ghost": {}})[0]
    )


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
    assert api.count_public(scratch(tmp_path, text) / "one/src") == (2, 0)
