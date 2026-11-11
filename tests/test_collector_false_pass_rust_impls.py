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


def _verdict(result: dict[str, Any], identifier: str) -> str:
    """The status of the rule. A scan with a gap decides no rule: the verdict is UNKNOWN then."""
    status = statuses(result).get(identifier)
    if status is None and result["declared_rules"] == "UNKNOWN":
        return "UNKNOWN"
    return str(status)


def _sources(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


def _modules(
    requires_of_a: tuple[str, ...], files: dict[str, str], requires_of_b: tuple[str, ...] = ()
) -> tuple[dict[str, Any], ...]:
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
        component("b", "app.b", (*requires_of_b, *(("c",) if "crate::c" in files["b.rs"] else ()))),
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

    assert _verdict(result, "NO-A-TO-B") == expected, result["diagnostics"]


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

    assert _verdict(result, "REQUIRES") == expected, result["diagnostics"]
    assert result["declared_rules"] == expected, statuses(result)


def test_the_gap_of_an_allowed_pair_stays_when_the_edge_closes_a_cycle(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `b` uses `a`, so the hidden edge `a -> b` closes a cycle that NO-CYCLES must see.
    files = {**IMPL_METHOD, "b.rs": "pub fn g() {\n    crate::a::f;\n}\n" + IMPL_METHOD["b.rs"]}
    components = _modules(("b", "c"), files, requires_of_b=("a",))
    result = validate(
        repository(tmp_path, rust_binary, _sources(files), components=components), capsys
    )

    assert _verdict(result, "NO-CYCLES") == "UNKNOWN", result["diagnostics"]


def test_a_cycle_rule_sees_a_path_through_a_pub_use_re_export(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # AD-357 (FP-31): a rule on a module pair reads direct imports; `a -> c -> b` through the
    # `pub use` of `c` is two edges, and a cycle or layer rule reads the path.
    files = {
        "lib.rs": LIB,
        "b.rs": "pub fn make() {}\npub fn g() {\n    crate::a::f();\n}\n",
        "c.rs": "pub use crate::b::make;\n",
        "a.rs": "use crate::c::make;\npub fn f() {\n    make();\n}\n",
    }
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    rules = (*CRATE_RULES, NO_A_TO_B, cycles)
    result = validate(repository(tmp_path, rust_binary, _sources(files), rules=rules), capsys)

    assert statuses(result).get("NO-A-TO-B") == "PASS", result["diagnostics"]
    assert statuses(result).get("MODULE-CYCLES") == "FAIL", result["diagnostics"]


def _calls(name: str, impl: str) -> str:
    """A module that calls `s.name(1)` and holds `impl crate::c::S { pub fn impl(&self, x) }`."""
    return (
        f"pub fn call_{name}(s: &crate::c::S) {{\n    s.{name}(1);\n}}\n"
        f"impl crate::c::S {{\n    pub fn {impl}(&self, x: u8) {{}}\n}}\n"
    )


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(
            {"lib.rs": LIB, "c.rs": TYPE, "a.rs": _calls("m", "n"), "b.rs": _calls("n", "m")},
            id="two pair gaps a -> b and b -> a",
        ),
        pytest.param(
            {
                "lib.rs": LIB + "mod d;\n",
                "c.rs": TYPE,
                "a.rs": _calls("m", "k"),
                "b.rs": _calls("n", "m"),
                "d.rs": _calls("k", "n"),
            },
            id="a chain of three pair gaps a -> b -> d -> a",
        ),
    ],
)
def test_pair_gaps_that_may_form_a_cycle_give_no_pass_for_a_cycle_rule(
    tmp_path: Path,
    rust_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
) -> None:
    # One component holds every module, so the contract allows each pair alone. Together the
    # hidden edges may close a module cycle, so the gaps stay and the cycle rule is never PASS.
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    rules = (*CRATE_RULES, cycles)
    result = validate(repository(tmp_path, rust_binary, _sources(files), rules=rules), capsys)

    assert _verdict(result, "MODULE-CYCLES") == "UNKNOWN", result["diagnostics"]


def test_pair_gaps_that_may_form_a_component_cycle_give_no_pass(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The contract allows a -> b and b -> a; the two hidden edges together close a component cycle.
    files = {"lib.rs": LIB, "c.rs": TYPE, "a.rs": _calls("m", "n"), "b.rs": _calls("n", "m")}
    components = _modules(("b", "c"), files, requires_of_b=("a",))
    result = validate(
        repository(tmp_path, rust_binary, _sources(files), components=components), capsys
    )

    assert _verdict(result, "NO-CYCLES") == "UNKNOWN", result["diagnostics"]


def test_a_known_edge_from_another_module_of_the_component_closes_the_cycle(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Review of #1017: A = {a}, B = {b, e}; each requires the other. The gap a -> b and the known
    # edge e -> a close a component cycle, although b itself does not reach a.
    files = {
        "lib.rs": LIB + "mod e;\n",
        "c.rs": TYPE,
        "b.rs": IMPL_METHOD["b.rs"],
        "a.rs": IMPL_METHOD["a.rs"],
        "e.rs": "pub fn g(s: &crate::c::S) {\n    crate::a::f(s);\n}\n",
    }
    base, root, part_a, _, part_c = _modules(("b", "c"), files)
    part_b = component("b", "app.b", ("a", "c"))
    part_b["packages"] = ["native.app.b", "native.app.e"]
    components = (base, root, part_a, part_b, part_c)
    result = validate(
        repository(tmp_path, rust_binary, _sources(files), components=components), capsys
    )

    assert _verdict(result, "NO-CYCLES") != "PASS", result["diagnostics"]
    assert result["declared_rules"] != "PASS"


IMPL_PATHS = {
    **IMPL_METHOD,
    "b.rs": "impl crate::c::S {\n    pub fn m(&self) {}\n    pub fn new() {}\n}\n",
}


@pytest.mark.parametrize(
    "caller",
    [
        pytest.param(
            "pub fn f(s: &crate::c::S) {\n    <crate::c::S>::m(s);\n}\n", id="qualified self"
        ),
        pytest.param(
            "use crate::c::S as Q;\npub fn f(s: &Q) {\n    Q::m(s);\n}\n", id="renamed use"
        ),
        pytest.param(
            "type Al = crate::c::S;\npub fn f(s: &Al) {\n    Al::m(s);\n}\n", id="type alias"
        ),
        pytest.param("use crate::c::*;\npub fn f() {\n    S::new();\n}\n", id="glob-imported type"),
    ],
)
def test_a_path_call_that_the_scan_cannot_resolve_exactly_gives_no_pass(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str], caller: str
) -> None:
    # Review of #1017: cargo gives E0599 in a for each form when `mod b;` is deleted.
    files = {**IMPL_PATHS, "a.rs": caller}
    rules = (*CRATE_RULES, NO_A_TO_B)
    result = validate(repository(tmp_path, rust_binary, _sources(files), rules=rules), capsys)

    assert _verdict(result, "NO-A-TO-B") in {"FAIL", "UNKNOWN"}, result["diagnostics"]
