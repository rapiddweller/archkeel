# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#953: a method of an `impl` in another module, or of a trait from a glob, gives no false PASS.

Consumer: the host (`archkeel validate`) with the native Rust collector. Module `a` uses module
`b` only through a method: `b` holds `impl crate::c::S { pub fn m() }` for the type `S` of `c`, or
the crate root binds the trait `T` of `b` and `a` reads it through `use super::*`. Cargo fails in
`a` when `mod b;` is deleted (E0599), so the edge `a -> b` is real.

- A path `crate::c::S::m()` names the method exactly: the edge `a -> b` is a fact (FAIL).
- A method call `s.m()` does not tell the type of `s`: the collector writes a gap for the pair
  `a -> b` (UNKNOWN). The host drops that gap when the contract lets `a` use `b` (PASS).
- A private member is visible only in `b` and below: no gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, PROVENANCE, component, repository, rule, statuses, validate

LIB = "mod a;\nmod b;\nmod c;\n"
TYPE = "pub struct S;\n"
NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
IMPL_PATH = {
    "lib.rs": LIB,
    "c.rs": TYPE,
    "b.rs": "impl crate::c::S {\n    pub fn m() {}\n}\n",
    "a.rs": "pub fn f() {\n    crate::c::S::m();\n}\n",
}
IMPL_METHOD = {
    "lib.rs": LIB,
    "c.rs": TYPE,
    "b.rs": "impl crate::c::S {\n    pub fn m(&self) {}\n}\n",
    "a.rs": "pub fn f(s: &crate::c::S) {\n    s.m();\n}\n",
}
GLOB_TRAIT = {
    "lib.rs": "mod a;\nmod b;\nmod c;\nuse b::T;\n",
    "c.rs": TYPE,
    "b.rs": "pub trait T {\n    fn m(&self);\n}\nimpl T for u8 {\n    fn m(&self) {}\n}\n",
    "a.rs": "use super::*;\npub fn f() {\n    5u8.m();\n}\n",
}
PRIVATE_MEMBER = {**IMPL_METHOD, "b.rs": "impl crate::c::S {\n    fn m(&self) {}\n}\n"}


def _sources(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


def _modules(requires_of_a: tuple[str, ...], files: dict[str, str]) -> tuple[dict[str, Any], ...]:
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
            for name in ("b", "base")
        ],
        "decided_by": "architect",
    }
    return (
        component("base", "base_crate"),
        root,
        component("a", "app.a", ("root", *requires_of_a)),
        component("b", "app.b", ("c",) if "crate::c" in files["b.rs"] else ()),
        component("c", "app.c"),
    )


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param(IMPL_PATH, "FAIL", id="FP-29 a path names the method of an impl in b"),
        pytest.param(IMPL_METHOD, "UNKNOWN", id="FP-29 a method call may reach an impl in b"),
        pytest.param(GLOB_TRAIT, "UNKNOWN", id="FP-30 a trait of b comes in through a glob"),
        pytest.param(PRIVATE_MEMBER, "PASS", id="a private member of b is no use of b"),
    ],
)
def test_a_method_of_another_module_gives_no_false_pass(
    tmp_path: Path,
    rust_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    expected: str,
) -> None:
    rules = (*CRATE_RULES, NO_A_TO_B)
    root = repository(tmp_path, rust_binary, _sources(files), rules=rules)
    result = validate(root, capsys)

    assert statuses(result).get("NO-A-TO-B") == expected, result["diagnostics"]


@pytest.mark.parametrize(
    ("files", "requires", "expected"),
    [
        pytest.param(IMPL_METHOD, ("c",), "UNKNOWN", id="FP-29 the contract forbids a -> b"),
        pytest.param(IMPL_METHOD, ("b", "c"), "PASS", id="FP-29 the contract allows a -> b"),
        pytest.param(GLOB_TRAIT, (), "UNKNOWN", id="FP-30 the contract forbids a -> b"),
        pytest.param(GLOB_TRAIT, ("b",), "PASS", id="FP-30 the contract allows a -> b"),
    ],
)
def test_the_gap_of_a_pair_is_dropped_only_when_the_contract_allows_the_pair(
    tmp_path: Path,
    rust_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    requires: tuple[str, ...],
    expected: str,
) -> None:
    sources = _sources(files)
    components = _modules(requires, files)
    result = validate(repository(tmp_path, rust_binary, sources, components=components), capsys)

    assert statuses(result).get("REQUIRES") == expected, result["diagnostics"]
    assert set(statuses(result).values()) == {expected}, statuses(result)
