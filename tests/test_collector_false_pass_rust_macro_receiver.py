# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""Keep receiver gaps when a workspace macro can add a binding (#1215)."""

from pathlib import Path

import pytest
from rust_repository import claims
from test_collector_false_pass_rust_param_receiver import _check, _plant

ITEMS = "macro_rules! items { ($($t:tt)*) => { $($t)* }; }\n"
HIDE = "macro_rules! hide { () => { use crate::c::S; }; }\n"


@pytest.mark.parametrize(
    "tokens",
    [
        "#[mac::rebind_attr] struct X;",
        "mod nested { #[mac::rebind_attr] struct X; }",
        "#[derive(mac::Rebind)] struct X;",
    ],
)
def test_a_passed_attribute_keeps_the_receiver_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], tokens: str
) -> None:
    files = _plant(ITEMS + f"pub fn f(s: &crate::c::S) -> u8 {{ items! {{ {tokens} }} s.m(1) }}\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize("form", ["local", "local-after", "closure", "field"])
def test_a_macro_can_hide_a_written_type(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], form: str
) -> None:
    setup = "use crate::c::S;\n" + HIDE
    cases = {
        "local": "hide!(); let s: &S = input; s.m(1)",
        "local-after": "let s: &S = input; hide!(); s.m(1)",
        "closure": "hide!(); let call = |s: &S| s.m(1); call(input)",
        "field": "hide!(); let w: &W = input; w.s.m(1)",
    }
    if form == "field":
        setup += "struct W { s: &'static S }\n"
        param = "input: &W"
    else:
        param = "input: &S"
    files = _plant(setup + f"pub fn f({param}) -> u8 {{ {cases[form]} }}\n")
    result, verdict = _check(tmp_path, core_binary, capsys, files)
    assert verdict == "UNKNOWN", claims(result)


@pytest.mark.parametrize(
    "source",
    [
        ITEMS + "pub fn f(s: &crate::c::S) -> u8 { items! { let _x = 1; } s.m(1) }\n",
        HIDE
        + "pub fn f(input: &crate::c::S) -> u8 { hide!(); let s: &crate::c::S = input; s.m(1) }\n",
        'use crate::c::S;\npub fn f(input: &S) -> u8 { println!("ok"); '
        "let s: &S = input; s.m(1) }\n",
    ],
)
def test_a_safe_macro_keeps_the_receiver_proof(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, _plant(source))
    assert verdict == "FAIL", claims(result)
