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


def test_a_removed_item_fails_by_name_until_the_baseline_changes(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\n")
    baseline = {"lib-one": ["fn a()", "fn b()"]}
    assert api.problems(native, baseline) == [
        "lib-one removes public fn b().",
        "Run `python tools/rust_api.py --write` and name each change of the API in the PR.",
    ]
    assert api.problems(native, {"lib-one": ["fn a()"]}) == []


def test_a_missing_deny_fails(tmp_path: Path) -> None:
    native = scratch(tmp_path, "pub fn a() {}\n")
    assert any("unreachable_pub" in line for line in api.problems(native, {"lib-one": ["fn a()"]}))


def test_a_swap_of_two_parts_with_the_same_counts_fails(tmp_path: Path) -> None:
    """AD-382: the counts stay equal when one part replaces another, the names do not."""
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub struct S { pub planted: u8 }\n")
    (native / "one/src/verdict.rs").write_text("pub fn planted_pass() {}\n", encoding="utf-8")
    baseline = {"lib-one": ["field S.kept: u8", "fn verdict::fail()", "struct S"]}
    assert api.count_public(native / "one/src") == (2, 1)
    assert api.problems(native, baseline)[:4] == [
        "lib-one adds public field S.planted: u8.",
        "lib-one adds public fn verdict::planted_pass().",
        "lib-one removes public field S.kept: u8.",
        "lib-one removes public fn verdict::fail().",
    ]


def test_a_changed_signature_or_field_type_with_the_same_name_fails(tmp_path: Path) -> None:
    """AD-382: the list holds the signature of a `fn` and the type of a field."""
    native = scratch(
        tmp_path, "#![deny(unreachable_pub)]\npub struct S { pub a: u16 }\npub fn f(x: u16) {}\n"
    )
    baseline = {"lib-one": ["field S.a: u8", "fn f(x:u8)", "struct S"]}
    assert api.problems(native, baseline)[:4] == [
        "lib-one adds public field S.a: u16.",
        "lib-one adds public fn f(x:u16).",
        "lib-one removes public field S.a: u8.",
        "lib-one removes public fn f(x:u8).",
    ]


def test_each_part_has_its_kind_its_module_and_its_name(tmp_path: Path) -> None:
    text = (
        "#![deny(unreachable_pub)]\npub mod m;\npub use a::{b as c, d::*};\n"
        "pub struct T(u8, pub Box<dyn Fn() -> u8>, pub u8);\npub static mut X: u8 = 0;\n"
    )
    native = scratch(tmp_path, text)
    (native / "one/src/m").mkdir()
    (native / "one/src/m/mod.rs").write_text("pub enum E { A, B }\n", encoding="utf-8")
    assert api.public_api(native / "one/src") == sorted(
        ["field T.1: Box<dyn Fn()->u8>", "field T.2: u8", "mod m", "static X", "struct T"]
        + ["use *", "use c"]
        + ["enum m::E", "variant m::E::A", "variant m::E::B"]
    )


def test_write_gives_a_baseline_that_passes(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\n")
    (native / "api_baseline.json").write_text("{}", encoding="utf-8")
    assert api.main(["--native", str(native), "--write"]) == 0
    assert json.loads((native / "api_baseline.json").read_text()) == {"lib-one": ["fn a()"]}
    assert api.main(["--native", str(native), "--check"]) == 0


def test_a_missing_or_old_format_entry_fails(tmp_path: Path) -> None:
    native = scratch(tmp_path, "#![deny(unreachable_pub)]\npub fn a() {}\n")
    assert "no list of public parts" in api.problems(native, {})[0]
    assert "no list of public parts" in api.problems(native, {"lib-one": 1})[0]
    old = {"lib-one": {"items": 1, "members": 0}}
    assert "no list of public parts" in api.problems(native, old)[0]
    assert "no library" in api.problems(native, {"lib-one": ["fn a()"], "ghost": []})[0]


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
