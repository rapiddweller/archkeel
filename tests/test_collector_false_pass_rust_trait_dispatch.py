# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A trait impl runs in a module that reaches its module, without a name (#1515, #1516, AD-806).

`b` defines `Y` and a trait impl for it; `c` gives `a` a value of `Y` (`c::make()`). `a` runs the
impl by a form that writes no name of `b`: a format macro, `*` through `Deref`, an index, a method
of a foreign trait that a glob brings in. `a` reaches `b` over `c`, so the rule that forbids
`a -> b` is never PASS. The 17 forms of `rust_orphan_plants` (`OPEN_VALUE_FORMS`,
`OPEN_TRAIT_FORMS`) are checked in `test_collector_false_pass_rust_orphan_impl.py`; here `cargo
check` accepts each of them too. Controls: a module that does not reach `b`, and an impl that
holds only an associated type, keep PASS.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_orphan_plants import OPEN_TRAIT_FORMS, OPEN_VALUE_FORMS
from rust_repository import APP, BASE, CRATE_RULES, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
LIB = "mod a;\nmod b;\nmod c;\n"
MAKE = "pub fn make() -> crate::b::Y {\n    crate::b::Y\n}\n"


def _form(impl: str, caller: str) -> dict[str, str]:
    return {"lib.rs": LIB, "b.rs": f"pub struct Y;\n{impl}", "c.rs": MAKE, "a.rs": caller}


FORMS: dict[str, dict[str, str]] = {
    "Debug through a format macro": _form(
        "impl std::fmt::Debug for Y {\n    fn fmt(&self, _f: &mut std::fmt::Formatter) "
        "-> std::fmt::Result {\n        Ok(())\n    }\n}\n",
        'pub fn f() -> String {\n    format!("{:?}", crate::c::make())\n}\n',
    ),
    "Deref through *": _form(
        "impl std::ops::Deref for Y {\n    type Target = u8;\n"
        "    fn deref(&self) -> &u8 {\n        &1\n    }\n}\n",
        "pub fn f() -> u8 {\n    *crate::c::make()\n}\n",
    ),
    "Index through []": _form(
        "impl std::ops::Index<usize> for Y {\n    type Output = u8;\n"
        "    fn index(&self, _i: usize) -> &u8 {\n        &1\n    }\n}\n",
        "pub fn f() -> u8 {\n    crate::c::make()[0]\n}\n",
    ),
}
CONTROLS: dict[str, dict[str, str]] = {
    "a does not reach b": _form(
        "impl std::fmt::Display for Y {\n    fn fmt(&self, _f: &mut std::fmt::Formatter) "
        "-> std::fmt::Result {\n        Ok(())\n    }\n}\n",
        "pub fn f() -> u8 {\n    1\n}\n",
    ),
    "the impl holds only an associated type": {
        **_form(
            "pub trait K {\n    type T;\n}\nimpl K for Y {\n    type T = u8;\n}\n",
            "pub fn f() {\n    let _y = crate::c::make();\n}\n",
        ),
    },
}
VENDOR = {
    "vendor/trait-ext/Cargo.toml": '[package]\nname = "trait-ext"\nversion = "0.0.0"\n'
    'edition = "2021"\n[workspace]\n',
    "vendor/trait-ext/src/lib.rs": "pub trait T {\n    fn m(&self) -> u8;\n}\n",
}
GLOB = {
    "crates/app/Cargo.toml": APP + 'trait-ext = { path = "../../vendor/trait-ext" }\n',
    "crates/app/src/lib.rs": LIB,
    "crates/app/src/a.rs": "use trait_ext::*;\npub fn f() -> u8 {\n    crate::c::make().m()\n}\n",
    "crates/app/src/b.rs": "pub struct Y;\nimpl trait_ext::T for Y {\n"
    "    fn m(&self) -> u8 {\n        1\n    }\n}\n",
    "crates/app/src/c.rs": MAKE,
    **VENDOR,
}


def _rustc_accepts(root: Path) -> None:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "crates/Cargo.toml"
    command = ["cargo", "check", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr


def _verdict(tmp_path: Path, core: Path, files: dict[str, str]) -> str:
    root = repository(tmp_path / "repo", core, files, rules=(*CRATE_RULES, NO_A_TO_B))
    verdict = statuses(validate(root))["NO-A-TO-B"]
    _rustc_accepts(root)
    return verdict


def _app(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


@pytest.mark.parametrize("name", list(FORMS))
def test_an_implicit_call_through_another_module_never_passes(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(FORMS[name])) in {"FAIL", "UNKNOWN"}


def test_a_foreign_trait_that_a_glob_brings_in_never_passes(
    tmp_path: Path, release_core: Path
) -> None:
    assert _verdict(tmp_path, release_core, GLOB) in {"FAIL", "UNKNOWN"}


@pytest.mark.parametrize("name", list(CONTROLS))
def test_a_module_that_cannot_run_the_impl_keeps_its_verdict(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(CONTROLS[name])) == "PASS"


OPEN = {**OPEN_VALUE_FORMS, **OPEN_TRAIT_FORMS}


@pytest.mark.parametrize("name", list(OPEN))
def test_rustc_accepts_each_dispatch_form_of_the_audit(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(OPEN[name])) in {"FAIL", "UNKNOWN"}


def test_a_foreign_return_type_can_carry_a_private_impl(tmp_path: Path, release_core: Path) -> None:
    files = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "carrier"]\n',
        "crates/base/Cargo.toml": BASE + '[dependencies]\ncarrier = { path = "../carrier" }\n',
        "crates/base/src/lib.rs": (
            "mod hidden;\n"
            "pub fn make() -> carrier::Handle { carrier::Handle(Box::new(hidden::Y)) }\n"
        ),
        "crates/base/src/hidden.rs": ("#[derive(Debug)]\npub(super) struct Y;\n"),
        "crates/carrier/Cargo.toml": BASE.replace('"base-crate"', '"carrier"'),
        "crates/carrier/src/lib.rs": (
            "#[derive(Debug)]\npub struct Handle(pub Box<dyn std::fmt::Debug>);\n"
        ),
        "crates/app/src/lib.rs": (
            'pub fn run() -> String { format!("{:?}", base_crate::make()) }\n'
        ),
    }
    no_private_dispatch = rule(
        "NO-PRIVATE-DISPATCH",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate.hidden",
        include_type_checking=True,
    )
    root = repository(
        tmp_path / "repo",
        release_core,
        files,
        components=(
            component("base", "base_crate", ("carrier",)),
            component("app", "app", ("base",)),
            component("carrier", "carrier"),
        ),
        rules=(*CRATE_RULES, no_private_dispatch),
    )
    _rustc_accepts(root)
    assert statuses(validate(root))["NO-PRIVATE-DISPATCH"] in {"FAIL", "UNKNOWN"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "pub fn f() -> u8 { trait_ext::T::m(&crate::c::make()) }\n",
            {"FAIL"},
            id="direct",
        ),
        pytest.param(
            "macro_rules! to_u8 { ($path:path) => { $path(&crate::c::make()) }; }\n"
            "pub fn f() -> u8 { to_u8!(trait_ext::T::m) }\n",
            {"FAIL", "UNKNOWN"},
            id="opaque-macro",
        ),
    ],
)
def test_a_lexical_external_path_never_passes(
    tmp_path: Path, release_core: Path, source: str, expected: set[str]
) -> None:
    files = {**GLOB, "crates/app/src/a.rs": source}
    scope = rule(
        "NO-EXTERNAL-IN-A",
        "external_dependency_scope",
        dependency="trait_ext",
        exact_sources=["native.app.b", "native.app.cargo_toml"],
    )
    root = repository(tmp_path / "repo", release_core, files, rules=(*CRATE_RULES, scope))
    _rustc_accepts(root)
    assert statuses(validate(root))["NO-EXTERNAL-IN-A"] in expected


def test_an_internal_dispatch_does_not_add_a_lexical_external_path(
    tmp_path: Path, release_core: Path
) -> None:
    files = {
        **GLOB,
        "crates/app/src/a.rs": "pub fn f() { drop(crate::c::make()); }\n",
        "crates/app/src/b.rs": GLOB["crates/app/src/b.rs"]
        + "impl Drop for Y { fn drop(&mut self) {} }\n",
    }
    package = rule(
        "NO-EXTERNAL-IN-A",
        "external_dependency_scope",
        dependency="trait_ext",
        exact_sources=["native.app.b", "native.app.cargo_toml"],
    )
    complete = rule("EXTERNALS-DECLARED", "complete_external_scope", source="native")
    local = rule(
        "NO-LOCAL-IN-A",
        "external_dependency_scope",
        dependency="native.app.b",
        exact_sources=["native.app", "native.app.c", "native.app.b"],
    )
    root = repository(
        tmp_path / "repo", release_core, files, rules=(*CRATE_RULES, package, complete, local)
    )
    _rustc_accepts(root)
    verdicts = statuses(validate(root))
    assert verdicts["NO-EXTERNAL-IN-A"] == "PASS"
    assert verdicts["EXTERNALS-DECLARED"] == "PASS"
    assert verdicts["NO-LOCAL-IN-A"] == "UNKNOWN"
