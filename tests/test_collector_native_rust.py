# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the native Rust collector gives crate edges, and what it cannot read is UNKNOWN.

Consumer: `archkeel validate` with `[scan] language = "rust"`. Each test writes a small Cargo
workspace and a contract (`rust_repository.py`) and reads the verdict of the whole product: the
host starts the binary, validates the reply and evaluates the rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rust_repository import (
    APP,
    BASE,
    CRATE_RULES,
    component,
    repository,
    rule,
    statuses,
    validate,
)

Capsys = pytest.CaptureFixture[str]


def _verdict(
    tmp_path: Path, binary: Path, capsys: Capsys, files: dict[str, str] | None = None, **kwargs: Any
) -> dict[str, Any]:
    return validate(repository(tmp_path, binary, files, **kwargs), capsys)


def _claims(result: dict[str, Any]) -> list[str]:
    return [item["unknown_claim"] for item in result["diagnostics"]]


def test_a_declared_crate_edge_passes(tmp_path: Path, rust_binary: Path, capsys: Capsys) -> None:
    result = _verdict(tmp_path, rust_binary, capsys)

    assert statuses(result) == {"ASSIGNED": "PASS", "REQUIRES": "PASS", "NO-CYCLES": "PASS"}
    assert result["diagnostics"] == []
    assert result["exit_code"] == 0


def test_an_edge_that_the_contract_does_not_declare_fails(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    files = {
        "crates/base/src/lib.rs": "use app::run;\npub fn make() {}\n",
        "crates/base/Cargo.toml": BASE + '[dependencies]\napp = { path = "../app" }\n',
    }
    result = _verdict(tmp_path, rust_binary, capsys, files)

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("base imports app without requiring it" in claim for claim in _claims(result))


def test_a_rename_in_cargo_toml_does_not_hide_an_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    # `renamed` is the package `app` under another name. The path of the source names the rename.
    files = {
        "crates/base/src/lib.rs": "use renamed::run;\npub fn make() {}\n",
        "crates/base/Cargo.toml": BASE
        + '[dependencies]\nrenamed = { path = "../app", package = "app" }\n',
    }
    result = _verdict(tmp_path, rust_binary, capsys, files)

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("base imports app without requiring it" in claim for claim in _claims(result))


def test_a_crate_that_no_component_owns_fails(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    files = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "extra"]\n',
        "crates/extra/Cargo.toml": '[package]\nname = "extra"\nversion = "0.0.0"\n',
        "crates/extra/src/lib.rs": "pub fn f() {}\n",
    }
    result = _verdict(tmp_path, rust_binary, capsys, files)

    assert statuses(result)["ASSIGNED"] == "FAIL"
    assert any("native.extra" in claim for claim in _claims(result))


def test_a_crate_cycle_fails(tmp_path: Path, rust_binary: Path, capsys: Capsys) -> None:
    files = {
        "crates/base/src/lib.rs": "use app::run;\npub fn make() {}\n",
        "crates/base/Cargo.toml": BASE + '[dependencies]\napp = { path = "../app" }\n',
    }
    parts = (component("base", "base_crate", ("app",)), component("app", "app", ("base",)))
    result = _verdict(tmp_path, rust_binary, capsys, files, components=parts)

    assert statuses(result)["NO-CYCLES"] == "FAIL"


def test_only_the_allowed_crate_uses_a_parser(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    scope = rule(
        "SYN-ONLY-BASE",
        "external_dependency_scope",
        dependency="syn",
        allowed_sources=["native.base_crate"],
    )
    files = {
        "crates/app/src/lib.rs": "use base_crate::make;\nuse syn::parse_file;\n",
        "crates/app/Cargo.toml": APP + 'syn = "3"\n',
    }
    result = _verdict(tmp_path, rust_binary, capsys, files, rules=(*CRATE_RULES, scope))

    assert statuses(result)["SYN-ONLY-BASE"] == "FAIL"


def test_a_rule_that_needs_symbols_or_calls_is_unknown_and_never_pass(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    constructs = rule(
        "NO-DYNAMIC", "forbidden_construct", source="native", constructs=["getattr", "eval"]
    )
    symbols = rule(
        "ENUMS-IN-BASE",
        "symbol_placement",
        source="native",
        class_kinds=["enum"],
        allowed_sources=["native.base_crate"],
    )
    result = _verdict(tmp_path, rust_binary, capsys, rules=(*CRATE_RULES, constructs, symbols))

    # The contract is valid. Each rule that needs more than crate edges says why it is UNKNOWN.
    assert not [item for item in result["diagnostics"] if item["kind"] == "contract_invalid"]
    claims = _claims(result)
    assert any("ENUMS-IN-BASE: rule kind symbol_placement is not supported" in c for c in claims)
    assert any("NO-DYNAMIC: constructs getattr, eval is not supported" in c for c in claims)
    assert "PASS" not in statuses(result).values()
    assert result["declared_rules"] == "UNKNOWN"


UNKNOWN = [
    ("fn g() { lazy::m!(a::b); }", "The macro m! holds a path that the scan cannot read"),
    ("macro_rules! m { () => { x::y() }; }", "The macro_rules! definition m is not expanded"),
    ('include!("other.rs");', "The macro include! adds code that the scan does not read"),
    ("#[cfg(unix)]\nmod unix;", "A cfg condition gates a module: cfg(unix)"),
    ("#[cfg(windows)]\nuse std::os::windows::fs;", "A cfg condition gates a use: cfg(windows)"),
    ('#[cfg_attr(unix, path = "x.rs")]\nmod x;', "A cfg_attr gates a module"),
    ('#[path = concat!("a", ".rs")]\nmod x;', "A path attribute is not a string literal"),
    ("#[tool::rewrite]\nmod x { }", "An attribute macro is applied to a module"),
    ("mod missing;", "Module file not found: mod missing in crates/app/src/lib.rs"),
    ("fn broken( {", "Syntax error in crates/app/src/lib.rs: unparseable construct at line 1"),
]


@pytest.mark.parametrize(("source", "reason"), UNKNOWN, ids=[reason[:28] for _, reason in UNKNOWN])
def test_what_the_scan_cannot_read_is_unknown_with_its_reason(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str, reason: str
) -> None:
    result = _verdict(tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source})

    assert result["observation_complete"] == "UNKNOWN"
    assert statuses(result) == {}
    assert any(reason in claim for claim in _claims(result)), _claims(result)


def test_a_derive_and_a_feature_gate_do_not_hide_anything(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    source = (
        "use base_crate::make;\n"
        "#[derive(Debug, Clone)]\npub struct S;\n"
        '#[cfg(feature = "dump")]\nmod dump;\n'
        "#[cfg(test)]\nmod tests { use super::*; }\n"
    )
    files = {
        "crates/app/src/lib.rs": source,
        "crates/app/src/dump.rs": "",
        "crates/app/Cargo.toml": APP + "[features]\ndump = []\n",
    }
    result = _verdict(tmp_path, rust_binary, capsys, files)

    assert statuses(result)["REQUIRES"] == "PASS"
    assert result["observation_complete"] == "PASS"


def test_a_path_inside_an_attribute_is_an_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    source = '#[serde(with = "base_crate::codec")]\npub struct S;\n'
    result = _verdict(
        tmp_path,
        rust_binary,
        capsys,
        {"crates/app/src/lib.rs": source},
        components=(
            component("base", "base_crate"),
            component("app", "app"),
        ),
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("app imports base without requiring it" in claim for claim in _claims(result))


def test_a_component_below_a_crate_root_is_unknown_never_pass(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    # `a` uses `b` inside one crate. The collector writes no edge inside a crate (slice 5b-2), so
    # sibling_isolation of the two modules must not read "no edge" as "no import".
    files = {"crates/app/src/lib.rs": "mod a;\nmod b;\n", "crates/app/src/a.rs": "use crate::b;\n"}
    files["crates/app/src/b.rs"] = "pub fn f() {}\n"
    parts = (
        component("a", "app.a"),
        component("b", "app.b"),
    )
    isolation = rule("SIBLINGS", "sibling_isolation", members=["native.app.a", "native.app.b"])
    result = _verdict(tmp_path, rust_binary, capsys, files, components=parts, rules=(isolation,))

    assert "PASS" not in statuses(result).values()
    assert result["declared_rules"] == "UNKNOWN"
    assert any("below a crate root is not supported" in claim for claim in _claims(result))


def test_a_rule_on_modules_below_a_crate_root_is_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    result = _verdict(tmp_path, rust_binary, capsys, rules=(*CRATE_RULES, forbidden, cycles))

    claims = _claims(result)
    assert any("NO-A-TO-B: rule forbidden_dependency below a crate root" in c for c in claims)
    assert any("MODULE-CYCLES: module cycles is not supported" in c for c in claims)
    assert result["declared_rules"] == "UNKNOWN"


def test_interface_boundary_is_unknown_because_every_local_target_is_a_crate_root(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    base = component("base", "base_crate")
    base["public"] = ["native.base_crate"]
    parts = (base, component("app", "app", ("base",)))
    boundary = rule("INTERFACE", "interface_boundary")
    result = _verdict(
        tmp_path, rust_binary, capsys, components=parts, rules=(*CRATE_RULES, boundary)
    )

    assert "INTERFACE: rule kind interface_boundary is not supported" in " ".join(_claims(result))
    assert statuses(result).get("INTERFACE") != "PASS"
    assert result["declared_rules"] == "UNKNOWN"


@pytest.mark.parametrize(
    "source",
    [
        "fn base_crate() {}\npub fn run() { base_crate::make(); }\n",
        "fn log() {}\nconst base_crate: u8 = 0;\n"
        'pub fn run() { log::info!("x"); base_crate::make(); }\n',
        "static base_crate: u8 = 0;\npub fn run() { base_crate::make(); }\n",
    ],
    ids=["fn", "fn-and-const", "static"],
)
def test_a_function_constant_or_static_does_not_hide_an_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("app imports base without requiring it" in claim for claim in _claims(result))


def test_a_path_in_a_bound_string_is_an_edge_and_one_that_does_not_read_is_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    bound = '#[serde(bound = "T: base_crate::Make")]\npub struct S<T>(T);\n'
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": bound}, components=parts
    )
    assert statuses(result)["REQUIRES"] == "FAIL"

    broken = '#[serde(bound = "T: (base_crate::Make")]\npub struct S<T>(T);\n'
    result = _verdict(tmp_path / "b", rust_binary, capsys, {"crates/app/src/lib.rs": broken})
    assert result["observation_complete"] == "UNKNOWN"
    assert any("holds a path that the scan cannot read" in claim for claim in _claims(result))


@pytest.mark.parametrize(
    "source",
    [
        "fn f() { let x = " + "(" * 2000 + "1" + ")" * 2000 + "; }\n",
        "mod a {" * 2000 + "}" * 2000 + "\n",
    ],
    ids=["parentheses", "inline-modules"],
)
def test_a_file_nested_beyond_the_stack_is_unknown_and_never_ends_the_scan(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    # Without the nesting check and the large stack, the binary aborts (signal 6) at this depth.
    result = _verdict(tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source})

    assert result["observation_complete"] == "UNKNOWN"
    assert any("Brackets nest deeper than 256" in claim for claim in _claims(result))
    assert not [d for d in result["diagnostics"] if d["kind"] == "execution_error"]


def test_a_module_chain_deeper_than_the_limit_is_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    files = {"crates/app/src/lib.rs": '#[path = "c0.rs"]\nmod c0;\n'}
    for i in range(66):
        files[f"crates/app/src/c{i}.rs"] = f'#[path = "c{i + 1}.rs"]\nmod c{i + 1};\n'
    result = _verdict(tmp_path, rust_binary, capsys, files)

    assert any("Modules nest deeper than 64 levels" in claim for claim in _claims(result))
