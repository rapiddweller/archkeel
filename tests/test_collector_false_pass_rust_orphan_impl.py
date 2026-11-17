# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1004: a trait impl in a third module gives no false PASS (AD-516).

Consumer: `archkeel validate` with the native Rust collector. Module `a` runs code of module `b`
without a `use`, a path or a method name that the scan can read: `b` holds an impl of a trait for a
type, and `b` defines neither. Cargo fails in `a` when `mod b;` is deleted (E0277, E0369, E0599),
so the edge `a -> b` is real. Each plant is one use form. On the code before AD-516 each plant
gave PASS for the rule `a` must not use `b`. Now each gives UNKNOWN: the pair gap `a -> b`.

- Control: an impl in the module of its type or of its trait keeps its verdict (PASS).
- Control: the contract allows `a -> b`: the core drops the gap (PASS).
- A value of a type of `b` that `a` gets from another module, and a trait of `b` that `a` reaches
  through a bound, a supertrait or a re-export: `a` reaches `b`, so it gets the pair gap (AD-806).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rust_orphan_plants import OPEN_TRAIT_FORMS, OPEN_VALUE_FORMS, SELF_TYPE_PLANTS
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
TYPE = "pub struct S;\n"
NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
S = "crate::c::S"
HEAD_DISPLAY = "fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {\n    Ok(())\n}"


def _case(head: str, body: str, caller: str, *, types: str = TYPE) -> dict[str, str]:
    """`b` holds `impl <head> for crate::c::S { <body> }` and `a` runs it by `caller`."""
    return {
        "lib.rs": LIB,
        "c.rs": types,
        "b.rs": f"impl {head} {{\n{body}\n}}\n",
        "a.rs": caller,
    }


# Y is the value that the impl takes: it is in `a`, so `b` names `a` and `a` never names `b`.
Y = "pub struct Y;\n"
FROM = "fn from(_: crate::a::Y) -> Self {\n    crate::c::S\n}"
ERROR = "pub struct E;\n"
ITER = (
    "type Item = u8;\ntype IntoIter = std::vec::IntoIter<u8>;\n"
    "fn into_iter(self) -> Self::IntoIter {\n    Vec::new().into_iter()\n}"
)
TRAIT = "pub struct S;\npub trait Tr {\n    fn m(&self) -> u8;\n}\n"
TR_BODY = "fn m(&self) -> u8 {\n    1\n}"

FROM_Y = (
    "pub struct Y;\nimpl From<Y> for String {\n"
    "    fn from(_: Y) -> String {\n        String::new()\n    }\n}\n"
)
PLANTS: dict[str, dict[str, str]] = {
    "From and into": _case(
        f"From<crate::a::Y> for {S}",
        FROM,
        Y + "pub fn f(y: Y) -> crate::c::S {\n    y.into()\n}\n",
    ),
    "From as a path": _case(
        f"From<crate::a::Y> for {S}",
        FROM,
        Y + "pub fn f(y: Y) -> crate::c::S {\n    crate::c::S::from(y)\n}\n",
    ),
    "the question mark": _case(
        "From<crate::a::Y> for crate::c::E",
        "fn from(_: crate::a::Y) -> Self {\n    crate::c::E\n}",
        Y + "fn h() -> Result<(), Y> {\n    Ok(())\n}\n"
        "pub fn f() -> Result<(), crate::c::E> {\n    h()?;\n    Ok(())\n}\n",
        types=ERROR,
    ),
    "an operator": _case(
        f"std::ops::Add<crate::a::Y> for {S}",
        "type Output = u8;\nfn add(self, _: crate::a::Y) -> u8 {\n    1\n}",
        Y + "pub fn f(s: crate::c::S, y: Y) -> u8 {\n    s + y\n}\n",
    ),
    "Deref": _case(
        f"std::ops::Deref for {S}",
        "type Target = u8;\nfn deref(&self) -> &u8 {\n    &1\n}",
        "pub fn f(s: &crate::c::S) -> u8 {\n    **s\n}\n",
    ),
    "Display and to_string": _case(
        f"std::fmt::Display for {S}",
        "fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {\n    Ok(())\n}",
        "pub fn f(s: &crate::c::S) -> String {\n    s.to_string()\n}\n",
    ),
    "IntoIterator in for": _case(
        f"IntoIterator for {S}",
        ITER,
        "pub fn f(s: crate::c::S) {\n    for _ in s {}\n}\n",
    ),
    "Iterator": _case(
        f"Iterator for {S}",
        "type Item = u8;\nfn next(&mut self) -> Option<u8> {\n    None\n}",
        "pub fn f(s: crate::c::S) -> usize {\n    s.count()\n}\n",
    ),
    "Default": _case(
        f"Default for {S}",
        "fn default() -> Self {\n    crate::c::S\n}",
        "pub fn f() -> crate::c::S {\n    Default::default()\n}\n",
    ),
    "PartialEq": _case(
        f"PartialEq for {S}",
        "fn eq(&self, _: &Self) -> bool {\n    true\n}",
        "pub fn f(s: &crate::c::S, t: &crate::c::S) -> bool {\n    s == t\n}\n",
    ),
    "Drop": _case(
        f"Drop for {S}",
        "fn drop(&mut self) {}",
        "pub fn f(_s: crate::c::S) {}\n",
    ),
    "AsRef": _case(
        f"AsRef<u8> for {S}",
        "fn as_ref(&self) -> &u8 {\n    &1\n}",
        "pub fn f(s: &crate::c::S) -> u8 {\n    *s.as_ref()\n}\n",
    ),
    "TryFrom": _case(
        f"TryFrom<crate::a::Y> for {S}",
        "type Error = ();\nfn try_from(_: crate::a::Y) -> Result<Self, ()> {\n"
        "    Ok(crate::c::S)\n}",
        Y + "pub fn f(y: Y) -> Result<crate::c::S, ()> {\n    y.try_into()\n}\n",
    ),
    "Index": _case(
        f"std::ops::Index<usize> for {S}",
        "type Output = u8;\nfn index(&self, _: usize) -> &u8 {\n    &1\n}",
        "pub fn f(s: &crate::c::S) -> u8 {\n    s[0]\n}\n",
    ),
    "a blanket impl for closures": _case(
        "<F: Fn()> crate::c::Tr for F",
        TR_BODY,
        "use crate::c::Tr;\npub fn f() -> u8 {\n    (|| {}).m()\n}\n",
        types=TRAIT,
    ),
    "generic dispatch": _case(
        "crate::c::Tr for u8",
        TR_BODY,
        "pub fn g<T: crate::c::Tr>(t: T) -> u8 {\n    t.m()\n}\n"
        "pub fn f() -> u8 {\n    g(1u8)\n}\n",
        types=TRAIT,
    ),
    "a local trait for a local type": _case(
        f"crate::c::Tr for {S}",
        TR_BODY,
        "use crate::c::Tr;\npub fn f(s: &crate::c::S) -> u8 {\n    s.m()\n}\n",
        types=TRAIT,
    ),
    "a type alias in b": {
        **_case(
            "std::fmt::Display for Q",
            HEAD_DISPLAY,
            "pub fn f(s: &crate::c::S) -> String {\n    s.to_string()\n}\n",
        ),
        "b.rs": f"type Q = crate::c::S;\nimpl std::fmt::Display for Q {{\n{HEAD_DISPLAY}\n}}\n",
    },
    "a type that a glob brings into b": {
        **_case(
            "std::fmt::Display for S",
            HEAD_DISPLAY,
            "pub fn f(s: &crate::c::S) -> String {\n    s.to_string()\n}\n",
        ),
        "b.rs": f"use crate::c::*;\nimpl std::fmt::Display for S {{\n{HEAD_DISPLAY}\n}}\n",
    },
}
PLANTS["a type argument of the trait is local"] = {
    **PLANTS["Display and to_string"],
    "b.rs": FROM_Y,
    "a.rs": "pub fn f() -> String {\n    String::new()\n}\n",
}
PLANTS.update(SELF_TYPE_PLANTS)

DISPLAY = PLANTS["Display and to_string"]
# AD-662 (#1371): a trait impl that a macro of `b` writes is an orphan of `b` too.
PLANTS["an impl that a macro of b generates"] = {
    **DISPLAY,
    "b.rs": "macro_rules! show {\n    () => {\n"
    "        impl std::fmt::Display for crate::c::S {\n"
    f"            {HEAD_DISPLAY}\n        }}\n    }};\n}}\nshow!();\n",
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


@pytest.mark.parametrize("files", PLANTS.values(), ids=PLANTS.keys())
def test_a_trait_impl_in_a_third_module_gives_a_pair_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)

    assert verdict == "UNKNOWN", claims(result)


CONTROLS: dict[str, dict[str, str]] = {
    "the impl is in the module of its type": {
        **DISPLAY,
        "c.rs": TYPE + PLANTS["Display and to_string"]["b.rs"],
        "b.rs": "pub fn unused() {}\n",
    },
    "the impl is in the module of its trait": {
        **PLANTS["a local trait for a local type"],
        "c.rs": "pub struct S;\n",
        "b.rs": f"pub trait Tr {{\n    fn m(&self) -> u8;\n}}\nimpl Tr for {S} {{\n{TR_BODY}\n}}\n",
        "a.rs": "pub fn f(_s: &crate::c::S) -> u8 {\n    1\n}\n",
    },
    "the type of the impl is a type that the block declares": {
        **DISPLAY,
        "a.rs": "pub fn f() {}\n",
        "b.rs": "pub fn g() {\n    struct Q;\n    impl Drop for Q {\n"
        "        fn drop(&mut self) {}\n    }\n}\n",
    },
    "the self type is a reference to a type of the module": {
        **DISPLAY,
        "b.rs": "pub struct Y;\nimpl std::fmt::Display for &Y {\n" + HEAD_DISPLAY + "\n}\n",
        "a.rs": "pub fn f() -> String {\n    String::new()\n}\n",
    },
}


@pytest.mark.parametrize("files", CONTROLS.values(), ids=CONTROLS.keys())
def test_an_impl_that_its_module_anchors_keeps_its_verdict(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)

    assert verdict == "PASS", claims(result)


def _modules(requires: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    """A component for each module of `app` and for `base`. `requires` is what `a` and `c` need."""
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
        component("a", "app.a", ("base", *requires)),
        component("b", "app.b", ("base",)),
        component("c", "app.c", requires),
    )


# `b` holds `impl From<Y> for base_crate::S`: a foreign trait and a foreign type with a local
# argument is valid Rust (no E0117). `b` defines `Y`, the argument, which anchors nothing.
BASE_TYPE = {
    "crates/base/src/lib.rs": "pub fn make() {}\npub struct S;\n",
    "crates/app/src/lib.rs": LIB,
    "crates/app/src/c.rs": "",
    "crates/app/src/b.rs": FROM_Y.replace("for String", "for base_crate::S")
    .replace("String::new()", "base_crate::S")
    .replace("-> String", "-> base_crate::S"),
    "crates/app/src/a.rs": "pub fn f(_s: base_crate::S) {}\n",
}
OBSERVED = "    a --> base\n    b --> base\n    root --> a\n    root --> b\n    root --> c"


@pytest.mark.parametrize(
    ("requires", "expected"),
    [
        pytest.param((), "UNKNOWN", id="the contract forbids a -> b and c -> b"),
        pytest.param(("b",), "PASS", id="the contract allows a -> b and c -> b"),
    ],
)
def test_the_gap_of_a_pair_is_dropped_only_when_the_contract_allows_the_pair(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    requires: tuple[str, ...],
    expected: str,
) -> None:
    drawn = OBSERVED if expected == "PASS" else None
    components = _modules(requires)
    root = repository(tmp_path, core_binary, BASE_TYPE, components=components, drawn=drawn)
    result = validate(root, capsys)

    assert _verdict(result, "REQUIRES") == expected, claims(result)


def test_a_trait_impl_in_a_module_of_a_crate_gives_a_pair_gap_to_a_crate_that_depends_on_it(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `app` depends on `base-crate`; `a` runs the Display impl of `base_crate::b` for its `S`.
    files = {
        "crates/base/src/lib.rs": "mod b;\npub struct S;\n",
        "crates/base/src/b.rs": f"impl std::fmt::Display for crate::S {{\n{HEAD_DISPLAY}\n}}\n",
        "crates/app/src/lib.rs": "mod a;\n",
        "crates/app/src/a.rs": "pub fn f(s: &base_crate::S) -> String {\n    s.to_string()\n}\n",
    }
    cross = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.base_crate.b",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, files, rules=(*CRATE_RULES, cross))
    result = validate(root, capsys)

    assert _verdict(result, "NO-A-TO-B") == "UNKNOWN", claims(result)


# #1515, #1516 (AD-806): `a` gets a value of a type of `b` from `c`, or reaches a trait of `b`
# through `c`. The impl is in the module of its type or trait, so no module is an orphan, and `a`
# never names `b`. Before AD-806 each form gave a false PASS. `a` reaches `b` over `c`, and `b`
# holds a trait impl that runs code: the pair gap `a -> b`.
OPEN: dict[str, dict[str, str]] = {
    **{f"a value of a type of b: {name}": files for name, files in OPEN_VALUE_FORMS.items()},
    **{f"the trait is defined in b: {name}": files for name, files in OPEN_TRAIT_FORMS.items()},
}


@pytest.mark.parametrize("files", OPEN.values(), ids=OPEN.keys())
def test_a_dispatch_through_another_module_never_passes(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result, verdict = _check(tmp_path, core_binary, capsys, files)

    assert verdict in {"FAIL", "UNKNOWN"}, claims(result)
