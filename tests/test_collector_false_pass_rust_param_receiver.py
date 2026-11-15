# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1012: a call on a typed parameter is an edge; a call that the scan cannot prove keeps its gap.

Consumer: `archkeel validate` with the native Rust collector (AD-524). Module `b` holds
`impl crate::c::S { pub fn m(&self, x: u8) }` and module `a` calls `s.m(1)`; the rule says `a` must
not use `b`. Cargo fails in `a` when `mod b;` is deleted, so `a -> b` is real in every plant here.

- A parameter `s: &S`, `s: &mut S` or `s: S` that is bound once, with the `self` form of the
  member, is proven: the edge `a -> b` is a fact and the rule gives FAIL (UNKNOWN before AD-524).
- Every other form keeps the pair gap: UNKNOWN. Each is a refusal of the rule, in its own plant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rust_repository import (
    CRATE_RULES,
    PROVENANCE,
    claims,
    component,
    repository,
    rule,
    statuses,
    validate,
)

LIB = "mod a;\nmod b;\nmod c;\n"
NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
TYPES = "#[derive(Debug)]\npub struct S;\npub trait Tr {\n    fn m(&self, x: u8) -> u8;\n}\n"
SHARED = "impl crate::c::S {\n    pub fn m(&self, x: u8) -> u8 {\n        x\n    }\n}\n"
UNIQUE = SHARED.replace("&self", "&mut self")
VALUE = SHARED.replace("&self", "self")
USE = "use crate::c::S;\n"


def _plant(a: str, b: str = SHARED, c: str = TYPES) -> dict[str, str]:
    return {"lib.rs": LIB, "c.rs": c, "b.rs": b, "a.rs": a}


PROVEN: dict[str, dict[str, str]] = {
    "a shared reference": _plant("pub fn f(s: &crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a unique reference": _plant(
        "pub fn f(s: &mut crate::c::S) -> u8 {\n    s.m(1)\n}\n", b=UNIQUE
    ),
    "a value": _plant("pub fn f(s: crate::c::S) -> u8 {\n    s.m(1)\n}\n", b=VALUE),
    "a mut value": _plant("pub fn f(mut s: crate::c::S) -> u8 {\n    s.m(1)\n}\n", b=VALUE),
    "a type from a use": _plant(USE + "pub fn f(s: &S) -> u8 {\n    s.m(1)\n}\n"),
    "a lifetime argument": _plant("pub fn f<'a>(s: &'a crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a method of a type": _plant(
        "pub struct W;\nimpl W {\n"
        "    pub fn f(&self, s: &crate::c::S) -> u8 {\n        s.m(1)\n    }\n"
        "}\n"
    ),
    "a macro of std that binds nothing": _plant(
        'pub fn f(s: &crate::c::S) -> u8 {\n    println!("{}", 1);\n    s.m(1)\n}\n'
    ),
}


def _shadow(body: str, param: str = "s: &crate::c::S") -> dict[str, str]:
    return _plant(f"pub fn f(o: Option<&crate::c::S>, {param}) -> u8 {{\n{body}\n}}\n")


REFUSED: dict[str, dict[str, str]] = {
    "a let of the name": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    let s = s;\n    s.m(1)\n}\n"
    ),
    "a let in an inner block": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    {\n        let s = s;\n        s.m(1)\n    }\n}\n"
    ),
    "a closure parameter": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    let k = |s: &crate::c::S| s.m(1);\n    k(s)\n}\n"
    ),
    "a match arm": _shadow("    match o {\n        Some(s) => s.m(1),\n        None => 0,\n    }"),
    "an if let": _shadow("    if let Some(s) = o {\n        return s.m(1);\n    }\n    0"),
    "a for loop": _plant(
        "pub fn f(s: &crate::c::S, v: Vec<&crate::c::S>) -> u8 {\n    let mut n = 0;\n"
        "    for s in v {\n        n += s.m(1);\n    }\n    n\n}\n"
    ),
    "a generic parameter of the name": _plant(
        USE + "pub fn f<S: crate::c::Tr>(s: &S) -> u8 {\n    s.m(1)\n}\n",
    ),
    "a generic parameter of the impl": _plant(
        "use crate::c::S;\npub struct W<S>(S);\nimpl<S: crate::c::Tr> W<S> {\n"
        "    pub fn f(&self, s: &S) -> u8 {\n        s.m(1)\n    }\n}\n"
    ),
    "impl Trait": _plant("pub fn f(s: &impl crate::c::Tr) -> u8 {\n    s.m(1)\n}\n"),
    "dyn Trait": _plant("pub fn f(s: &dyn crate::c::Tr) -> u8 {\n    s.m(1)\n}\n"),
    "a type alias": _plant("type Al = crate::c::S;\npub fn f(s: &Al) -> u8 {\n    s.m(1)\n}\n"),
    "a struct of the same name in the body": _plant(
        USE + "pub fn f(s: &S) -> u8 {\n    #[allow(dead_code)]\n    struct S;\n    s.m(1)\n}\n"
    ),
    "a unique reference with a shared member": _plant(
        "pub fn f(s: &mut crate::c::S) -> u8 {\n    s.m(1)\n}\n"
    ),
    "a value with a shared member": _plant("pub fn f(s: crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a reference to a reference": _plant("pub fn f(s: &&crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a tuple pattern": _plant("pub fn f((s, _t): (&crate::c::S, u8)) -> u8 {\n    s.m(1)\n}\n"),
    "a ref pattern": _plant("pub fn f(ref s: crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a macro that rebinds the name": _plant(
        "macro_rules! rebind {\n    ($i:ident) => {\n        let $i = $i;\n    };\n}\n"
        "pub fn f(s: &crate::c::S) -> u8 {\n    rebind!(s);\n    s.m(1)\n}\n"
    ),
    "a call inside a macro": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    assert!(s.m(1) > 0);\n    1\n}\n"
    ),
    "a macro call that names the parameter": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    dbg!(&s);\n    s.m(1)\n}\n"
    ),
    "a use that binds the name": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    #[allow(unused_imports)]\n"
        "    use crate::c::S as s;\n    s.m(1)\n}\n"
    ),
    "a Deref impl of the type": _plant(
        "pub fn f(s: &crate::c::S) -> u8 {\n    s.m(1)\n}\n",
        c=TYPES + "impl std::ops::Deref for S {\n    type Target = u8;\n"
        "    fn deref(&self) -> &u8 {\n        &1\n    }\n}\n",
    ),
    "a macro of the workspace with the name of a macro of std": _plant(
        "macro_rules! println {\n    ($($t:tt)*) => {};\n}\n"
        "pub fn f(s: &crate::c::S) -> u8 {\n    s.m(1)\n}\n"
    ),
    "a cfg on the fn": _plant("#[cfg(unix)]\npub fn f(s: &crate::c::S) -> u8 {\n    s.m(1)\n}\n"),
    "a cfg on the parameter": _plant(
        "pub fn f(#[cfg(unix)] s: &crate::c::S) -> u8 {\n    s.m(1)\n}\n"
    ),
    "a nested fn": _plant(
        "pub fn f() {\n    fn g(s: &crate::c::S) -> u8 {\n        s.m(1)\n"
        "    }\n    g(&crate::c::S);\n}\n"
    ),
    "a gated module": _plant(
        "#[cfg(unix)]\nmod inner {\n    pub fn f(s: &crate::c::S) -> u8 {\n"
        "        s.m(1)\n    }\n}\n"
    ),
    "a field of the parameter": _plant(
        "pub struct W {\n    pub s: crate::c::S,\n}\npub fn f(w: &W) -> u8 {\n    w.s.m(1)\n}\n"
    ),
}


def _verdict(result: dict[str, Any], identifier: str) -> str:
    """The status of the rule. A scan with a gap decides no rule: the verdict is UNKNOWN then."""
    status = statuses(result).get(identifier)
    if status is None and result["status"] == "UNKNOWN":
        return "UNKNOWN"
    return str(status)


def _sources(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


def _check(
    tmp_path: Path, binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> tuple[dict[str, Any], str]:
    rules = (*CRATE_RULES, NO_A_TO_B)
    result = validate(repository(tmp_path, binary, _sources(files), rules=rules), capsys)
    return result, _verdict(result, "NO-A-TO-B")


@pytest.mark.parametrize("files", PROVEN.values(), ids=PROVEN.keys())
def test_a_call_on_a_typed_parameter_is_an_edge(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)

    assert verdict == "FAIL", claims(result)


@pytest.mark.parametrize("files", REFUSED.values(), ids=REFUSED.keys())
def test_a_call_that_the_scan_cannot_prove_keeps_its_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)

    assert verdict == "UNKNOWN", claims(result)


def _modules(requires_of_a: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    """A component for each module of `app`: the root (with the manifest), `a`, `b` and `c`."""
    root = {
        "id": "COMP-ROOT",
        "label": "root",
        "role": "component",
        "packages": [],
        "exact_modules": ["native.app", "native.app.cargo_toml"],
        "responsibilities": ["Own the crate root."],
        "forbidden_responsibilities": [],
        "provenance": PROVENANCE,
        "requires": [
            {"component": name, "rationale": "The root binds names of its modules."}
            for name in ("a", "b", "c", "base")
        ],
        "decided_by": "architect",
    }
    return (
        component("base", "base_crate"),
        root,
        component("a", "app.a", ("base", "c", *requires_of_a)),
        component("b", "app.b", ("c",)),
        component("c", "app.c"),
    )


@pytest.mark.parametrize(
    ("requires", "expected"),
    [
        pytest.param((), "FAIL", id="the contract forbids a -> b"),
        pytest.param(("b",), "PASS", id="the contract allows a -> b"),
    ],
)
def test_a_proven_edge_is_judged_by_the_contract(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    requires: tuple[str, ...],
    expected: str,
) -> None:
    sources = _sources(PROVEN["a shared reference"])
    drawn = None
    if expected == "PASS":
        drawn = "    a --> base\n    a --> b\n    a --> c\n    b --> c\n    root --> a\n"
        drawn += "    root --> b\n    root --> base\n    root --> c"
    root = repository(tmp_path, core_binary, sources, components=_modules(requires), drawn=drawn)
    result = validate(root, capsys)

    assert _verdict(result, "REQUIRES") == expected, claims(result)
