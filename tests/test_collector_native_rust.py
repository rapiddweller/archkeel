# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the native Rust collector gives crate edges, and what it cannot read is UNKNOWN.

Consumer: `archkeel validate` with `[scan] language = "rust"`. Each test writes a small Cargo
workspace and a contract (`rust_repository.py`) and reads the verdict of the whole product: the
host starts the binary, validates the reply and evaluates the rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rust_repository import (
    APP,
    BASE,
    CRATE_RULES,
    component,
    report,
    repository,
    rule,
    statuses,
    validate,
)

Capsys = pytest.CaptureFixture[str]


def _verdict(
    tmp_path: Path,
    binary: Path,
    capsys: Capsys,
    files: dict[str, str] | None = None,
    *,
    keep_gaps: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    root = repository(tmp_path, binary, files, **kwargs)
    return (report if keep_gaps else validate)(root, capsys)


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
    (
        "#[macro_export]\nmacro_rules! m { () => { x::y() }; }",
        "The macro_rules! definition m is exported: it expands in other crates",
    ),
    ('include!("other.rs");', "The macro include! adds code that the scan does not read"),
    ("#[cfg(unix)]\nmod unix;", "A cfg condition gates a module: cfg(unix)"),
    ("#[cfg(windows)]\nuse std::os::windows::fs;", "A cfg condition gates a use: cfg(windows)"),
    ('#[cfg_attr(unix, path = "x.rs")]\nmod x;', "A cfg_attr gates a module"),
    ('#[path = concat!("a", ".rs")]\nmod x;', "A path attribute is not a string literal"),
    ("#[tool::rewrite]\nmod x { }", "The attribute macro tool::rewrite can add code"),
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


def test_an_attribute_expansion_with_an_unseen_target_is_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    """P8b of #1120: the compiled macro emits a call that is not in the function source."""
    files = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "mac"]\n',
        "crates/app/Cargo.toml": APP + 'mac = { path = "../mac" }\n',
        "crates/app/src/lib.rs": "mod a; mod b;\n",
        "crates/app/src/a.rs": "pub fn x() {}\n",
        "crates/app/src/b.rs": "#[mac::hide] pub fn y() {}\n",
        "crates/mac/Cargo.toml": '[package]\nname = "mac"\nversion = "0.0.0"\n'
        'edition = "2021"\n[lib]\nproc-macro = true\n',
        "crates/mac/src/lib.rs": "extern crate proc_macro;\n#[proc_macro_attribute]\n"
        "pub fn hide(_: proc_macro::TokenStream, _: proc_macro::TokenStream) "
        '-> proc_macro::TokenStream { "pub fn y() { crate::a::x(); }".parse().unwrap() }\n',
    }
    forbidden = rule(
        "NO-HIDDEN",
        "forbidden_dependency",
        source="native.app.b",
        target="native.app.a",
        include_type_checking=True,
    )
    root = repository(tmp_path, rust_binary, files, rules=(forbidden,))
    result = report(root, capsys)
    assert statuses(result).get("NO-HIDDEN") == "UNKNOWN", _claims(result)
    gaps = result["coverage"]["failures"]
    [gap] = [g for g in gaps if "attribute macro mac::hide" in g["title"]]
    assert gap["data"]["source_module"] == "native.app.b"
    assert gap["data"]["module"] == ""


def test_invalid_utf8_has_a_named_gap(tmp_path: Path, rust_binary: Path, capsys: Capsys) -> None:
    root = repository(tmp_path, rust_binary)
    (root / "crates/app/src/lib.rs").write_bytes(b"pub fn run() {} //\xff")
    result = validate(root, capsys)
    assert result["observation_complete"] == "UNKNOWN"
    assert any("File is not valid UTF-8: crates/app/src/lib.rs" in c for c in _claims(result))


def test_a_proven_serde_helper_edge_fails_the_forbidden_rule(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    forbidden = rule(
        "NO-HELPER",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    root = repository(
        tmp_path,
        rust_binary,
        {
            "crates/app/Cargo.toml": APP + 'serde = { version = "1.0", features = ["derive"] }\n',
            "crates/Cargo.lock": Path(__file__).with_name("rust_known_derives.lock").read_text(),
            "crates/app/src/lib.rs": "mod a; mod b;",
            "crates/app/src/a.rs": 'use serde::Serialize; #[derive(Serialize)] struct S { #[serde(with = "crate::b::helper")] x: u8 }',
            "crates/app/src/b.rs": "pub mod helper {}",
        },
        rules=(forbidden,),
    )
    result = report(root, capsys)
    assert statuses(result)["NO-HELPER"] == "FAIL", _claims(result)
    assert result["coverage"]["failures"] == []


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
        keep_gaps=True,
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any(
        "app imports base without requiring it" in item["title"] for item in result["findings"]
    )


APP_MODULES = {
    "crates/app/src/lib.rs": "mod a;\nmod b;\n",
    "crates/app/src/a.rs": "use crate::b;\n",
    "crates/app/src/b.rs": "pub fn f() {}\n",
}


def test_sibling_isolation_of_two_modules_fails_for_the_module_edge_between_them(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    # `a` uses `b` inside one crate: the collector writes that edge (slice 5b-2c), so the rule is
    # decided, and it fails.
    parts = (component("a", "app.a"), component("b", "app.b"))
    isolation = rule("SIBLINGS", "sibling_isolation", members=["native.app.a", "native.app.b"])
    result = _verdict(
        tmp_path, rust_binary, capsys, APP_MODULES, components=parts, rules=(isolation,)
    )

    assert statuses(result)["SIBLINGS"] == "FAIL"
    assert result["declared_rules"] == "FAIL"


def test_a_forbidden_module_edge_fails_and_the_opposite_direction_passes(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    forbidden = [
        rule("NO-A-TO-B", "forbidden_dependency", source="native.app.a", target="native.app.b"),
        rule("NO-B-TO-A", "forbidden_dependency", source="native.app.b", target="native.app.a"),
    ]
    for item in forbidden:
        item["include_type_checking"] = True
    result = _verdict(tmp_path, rust_binary, capsys, APP_MODULES, rules=(*CRATE_RULES, *forbidden))

    assert statuses(result)["NO-A-TO-B"] == "FAIL"
    assert statuses(result)["NO-B-TO-A"] == "PASS"


def test_a_module_cycle_fails_and_modules_without_one_pass(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    clean = _verdict(tmp_path / "clean", rust_binary, capsys, APP_MODULES, rules=(cycles,))
    looped = {**APP_MODULES, "crates/app/src/b.rs": "use crate::a;\n"}
    result = _verdict(tmp_path / "loop", rust_binary, capsys, looped, rules=(cycles,))

    assert statuses(clean)["MODULE-CYCLES"] == "PASS"
    assert statuses(result)["MODULE-CYCLES"] == "FAIL"


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


SHADOWED = [
    # The four repros of the review, and a function, a constant and a static.
    "pub mod base_crate {}\n#[cfg(test)]\nmod tests { fn t() { base_crate::make(); } }\n",
    "pub struct base_crate;\nmod m { fn t() { base_crate::make(); } }\n",
    "pub type base_crate = u8;\nmod m { fn t() { base_crate::make(); } }\n",
    "use self::inner::base_crate;\nmod m { fn t() { base_crate::make(); } }\nmod inner {}\n",
    "use crate::util::base_crate;\nfn t() { base_crate::make(); }\n",
    "fn base_crate() {}\npub fn run() { base_crate::make(); }\n",
    "const base_crate: u8 = 0;\npub fn run() { base_crate::make(); }\n",
    "static base_crate: u8 = 0;\npub fn run() { base_crate::make(); }\n",
]


@pytest.mark.parametrize("source", SHADOWED, ids=range(len(SHADOWED)))
def test_a_local_name_equal_to_a_crate_name_is_unknown_never_pass(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result).get("REQUIRES") != "PASS"
    assert result["declared_rules"] == "UNKNOWN"
    assert any("A local name equals a crate name: base_crate" in c for c in _claims(result))


def test_a_crate_name_that_the_file_does_not_declare_is_an_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    source = "pub fn run() { base_crate::make(); }\n"
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("app imports base without requiring it" in claim for claim in _claims(result))


@pytest.mark.parametrize(
    "attribute",
    [
        '#[serde(getter = "base_crate::get")]',
        '#[serde_as(as = "base_crate::X")]',
        '#[schemars(schema_with = "base_crate::schema")]',
        '#[validate(custom(function = "base_crate::check"))]',
        '#[derivative(Debug(format_with = "base_crate::fmt"))]',
        '#[educe(Debug(method = "base_crate::fmt"))]',
    ],
)
def test_a_path_under_a_key_of_another_crate_is_an_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, attribute: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path,
        rust_binary,
        capsys,
        {"crates/app/src/lib.rs": f"{attribute}\npub struct S;\n"},
        components=parts,
        keep_gaps=True,
    )

    assert statuses(result)["REQUIRES"] == "FAIL"


def test_a_path_in_a_bound_string_is_an_edge_and_one_that_does_not_read_is_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    bound = '#[serde(bound = "T: base_crate::Make")]\npub struct S<T>(T);\n'
    result = _verdict(
        tmp_path,
        rust_binary,
        capsys,
        {"crates/app/src/lib.rs": bound},
        components=parts,
        keep_gaps=True,
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


def test_a_contract_inside_a_component_is_decided_from_the_module_edges(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    app = component("app", "app", ("base",))
    app["inside"] = "docs/app-inside.json"
    inner = {
        "schema_version": "2.2.0",
        "components": [component("a", "app.a"), component("b", "app.b")],
        "rules": [rule("INNER-REQUIRES", "complete_requires")],
    }
    files = {**APP_MODULES, "docs/app-inside.json": json.dumps(inner)}
    parts = (component("base", "base_crate"), app)
    result = _verdict(tmp_path, rust_binary, capsys, files, components=parts)

    # `a` uses `b`, and the inside contract does not say so: a decided FAIL, not UNKNOWN.
    assert statuses(result)["app:INNER-REQUIRES"] == "FAIL"
    assert not any("below a crate root" in claim for claim in _claims(result))


def test_a_local_module_does_not_hide_a_path_that_starts_with_two_colons(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    source = "mod base_crate {}\nuse ::base_crate::make;\npub fn run() { make(); }\n"
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert any("app imports base without requiring it" in claim for claim in _claims(result))


def test_a_message_a_name_or_a_lint_is_no_edge_and_no_gap(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    source = (
        "use base_crate::make;\n"
        '#[deprecated(note = "use base_crate::make")]\npub fn old() {}\n'
        '#[should_panic(expected = "base_crate::make")]\nfn t() {}\n'
        "#[cfg_attr(test, allow(base_crate::lint))]\npub struct S;\n"
    )
    result = _verdict(tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source})

    assert result["observation_complete"] == "PASS"
    assert statuses(result)["REQUIRES"] == "PASS"
