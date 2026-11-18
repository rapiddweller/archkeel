# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-543: a written local type, closure parameter type or field type proves a Rust receiver.

Consumer: `archkeel validate` with the native Rust collector. The plants and the rule are those of
`test_collector_false_pass_rust_param_receiver.py`: module `a` calls `s.m(1)` and must not use `b`.
A form that the scan cannot prove keeps the pair gap: UNKNOWN.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import claims
from test_collector_false_pass_rust_param_receiver import TYPES, UNIQUE, _check, _plant


@pytest.mark.parametrize(
    "binding",
    ["let s: &crate::c::S = input;", "let mut s: &crate::c::S = input;"],
)
def test_a_written_local_type_proves_a_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], binding: str
) -> None:
    files = _plant(f"pub fn f(input: &crate::c::S) -> u8 {{\n    {binding}\n    s.m(1)\n}}\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


def test_a_written_unique_local_type_proves_a_unique_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = _plant(
        "pub fn f(input: &mut crate::c::S) -> u8 {\n"
        "    let s: &mut crate::c::S = input;\n    s.m(1)\n}\n",
        b=UNIQUE,
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


@pytest.mark.parametrize(
    "body",
    [
        "let s: &crate::c::S = input; let s = s; s.m(1)",
        "let s: &crate::c::S = input; let f = |s: &crate::c::S| s.m(1); f(s)",
        "let s: &crate::c::S = input; assert!(s.m(1) > 0); 1",
        "let s: &&crate::c::S = &input; s.m(1)",
        "let s: &crate::c::S = input; #[cfg(unix)] let _n = 1; s.m(1)",
        "{ let s: &crate::c::S = input; s.m(1) }",
        "let _ = s.m(1); let s: &crate::c::S = input; 1",
        "let s: &crate::c::S = { let _ = s.m(1); input }; 1",
    ],
)
def test_a_local_binding_decides_only_a_proven_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], body: str
) -> None:
    files = _plant(f"pub fn f(input: &crate::c::S) -> u8 {{\n    {body}\n}}\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    # AD-804 follows the written type through a shadowed let and a nested block.
    proven = {
        "let s: &crate::c::S = input; let s = s; s.m(1)",
        "{ let s: &crate::c::S = input; s.m(1) }",
    }
    assert verdict == ("FAIL" if body in proven else "UNKNOWN"), claims(result)


@pytest.mark.parametrize(
    "files",
    [
        _plant(
            "type Alias = crate::c::S;\npub fn f(input: &Alias) -> u8 {\n"
            "    let s: &Alias = input; s.m(1)\n}\n"
        ),
        _plant(
            "use crate::c::S;\npub fn f<S: crate::c::Tr>(input: &S) -> u8 {\n"
            "    let s: &S = input; s.m(1)\n}\n"
        ),
        _plant(
            "pub fn f(input: &mut crate::c::S) -> u8 {\n"
            "    let s: &mut crate::c::S = input; s.m(1)\n}\n"
        ),
        _plant(
            "pub fn f(input: &crate::c::S) -> u8 {\n    let s: &crate::c::S = input; s.m(1)\n}\n",
            c=TYPES + "impl std::ops::Deref for S { type Target = u8; "
            "fn deref(&self) -> &u8 { &1 } }\n",
        ),
    ],
    ids=["alias", "generic", "receiver-form", "deref"],
)
def test_a_local_with_an_unproved_type_keeps_the_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize("body", ["s.m(1)", "s.m(1).saturating_add(1)"])
def test_a_written_closure_type_proves_a_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], body: str
) -> None:
    files = _plant(
        f"pub fn f(input: &crate::c::S) -> u8 {{\n"
        f"    let call = |s: &crate::c::S| {body};\n    call(input)\n}}\n"
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


@pytest.mark.parametrize(
    "closure",
    [
        "|s| s.m(1)",
        "|s: &crate::c::S| { let s = s; s.m(1) }",
        "|s: &&crate::c::S| s.m(1)",
        "|s: &crate::c::S| { #[cfg(unix)] let _n = 1; s.m(1) }",
        "|s: &crate::c::S| { fn inner() -> u8 { s.m(1) } 1 }",
    ],
)
def test_an_unproved_closure_receiver_keeps_the_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], closure: str
) -> None:
    files = _plant(f"pub fn f() {{\n    let _call = {closure};\n}}\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize(
    "caller",
    [
        "impl W { pub fn f(&self) -> u8 { self.s.m(1) } }",
        "pub fn f(w: &W) -> u8 { w.s.m(1) }",
    ],
)
def test_a_written_field_type_proves_a_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], caller: str
) -> None:
    files = _plant("pub struct W { pub s: &'static crate::c::S }\n" + caller + "\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


def test_a_field_type_with_a_renamed_import_proves_a_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = _plant(
        "use crate::c::S as Renamed;\npub struct W { pub s: &'static Renamed }\n"
        "pub fn f(w: &W) -> u8 { w.s.m(1) }\n"
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


def test_two_written_field_types_prove_a_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = _plant(
        "pub struct W { pub inner: V }\npub struct V { pub s: &'static crate::c::S }\n"
        "pub fn f(w: &W) -> u8 { w.inner.s.m(1) }\n"
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


def test_a_typed_closure_receiver_proves_a_field(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = _plant(
        "pub struct W { pub s: &'static crate::c::S }\n"
        "pub fn f(w: &W) -> u8 { let call = |value: &W| value.s.m(1); call(w) }\n"
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)


@pytest.mark.parametrize(
    "source",
    [
        "pub struct W<T> { pub s: T }\npub fn f(w: &W<&crate::c::S>) -> u8 { w.s.m(1) }\n",
        (
            "pub struct W<T = ()> { pub s: &'static crate::c::S, p: std::marker::PhantomData<T> }\n"
            "pub fn f(w: &W) -> u8 { w.s.m(1) }\n"
        ),
        (
            "type A = crate::c::S;\npub struct W { pub s: &'static A }\n"
            "pub fn f(w: &W) -> u8 { w.s.m(1) }\n"
        ),
        (
            "pub struct W { #[cfg(unix)] pub s: &'static crate::c::S }\n"
            "pub fn f(w: &W) -> u8 { w.s.m(1) }\n"
        ),
        (
            "pub struct W { pub s: &'static mut crate::c::S }\n"
            "pub fn f(w: &mut W) -> u8 { w.s.m(1) }\n"
        ),
        (
            "macro_rules! make { () => { pub struct W { pub s: &'static crate::c::S } }; }\n"
            "make!();\npub fn f(w: &W) -> u8 { w.s.m(1) }\n"
        ),
        (
            "pub struct W { pub s: &'static crate::c::S }\n"
            "impl std::ops::Deref for W { type Target = u8; fn deref(&self) -> &u8 { &1 } }\n"
            "impl W { pub fn f(&self) -> u8 { self.s.m(1) } }\n"
        ),
    ],
    ids=[
        "generic",
        "generic-default",
        "alias",
        "cfg-field",
        "receiver-form",
        "macro-struct",
        "deref-base",
    ],
)
def test_an_unproved_field_keeps_the_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, _plant(source))
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize("case", ["private-field", "deref-field"])
def test_a_hidden_or_deref_field_keeps_the_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    if case == "private-field":
        files = _plant(
            "pub fn f(w: &crate::c::W) -> u8 { w.s.m(1) }\n",
            c=TYPES + "pub struct W { s: &'static S }\n",
        )
    else:
        files = _plant(
            "pub struct W { pub s: &'static crate::c::S }\npub fn f(w: &W) -> u8 { w.s.m(1) }\n",
            c=TYPES + "impl std::ops::Deref for S { type Target = u8; "
            "fn deref(&self) -> &u8 { &1 } }\n",
        )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize("shared_intermediate", [False, True])
def test_a_unique_field_behind_a_shared_projection_keeps_the_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], shared_intermediate: bool
) -> None:
    inner, param = ("&'static V", "&mut W") if shared_intermediate else ("V", "&W")
    files = _plant(
        f"pub struct W {{ pub inner: {inner} }}\n"
        "pub struct V { pub s: &'static mut crate::c::S }\n"
        f"pub fn f(w: {param}) -> u8 {{ w.inner.s.m(1) }}\n",
        b=UNIQUE,
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


def test_a_chain_of_exact_fields_proves_the_receiver(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-804: three exact fields, the last one `&S`: the first step finds `S::m(&self)`."""
    files = _plant(
        "pub struct W { pub inner: V }\npub struct V { pub inner: X }\n"
        "pub struct X { pub s: &'static crate::c::S }\n"
        "pub fn f(w: &W) -> u8 { w.inner.inner.s.m(1) }\n"
    )
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "FAIL", claims(result)
