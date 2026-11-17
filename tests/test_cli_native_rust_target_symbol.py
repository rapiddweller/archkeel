# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-668: a `target_symbol` rule sees each Rust form that names the item.

The crate `base` defines `enum Profile`; the rule forbids `app` to name it. rustc accepts each
plant.
Each form that names the item (by its name, by a `use ... as` alias, by a variant path, by a glob of
the enum, or by a re-export under another name) gives FAIL. A glob of a whole crate of the workspace
is read as a glob of its root module and gives FAIL too (AD-802). A route that the scan does not
prove beside a rename of the item gives UNKNOWN, never PASS. A type alias is an
item of its own, as a function that returns the type: a use of the alias names no `Profile`.
Such a use, and a call of `make` alone, still reach `base.vocab`, where the derived `PartialEq` of
`Profile` runs: the value flow cannot prove that `app` holds no `Profile`, so the rule is UNKNOWN
with the trait-dispatch gap `app -> base.vocab` (AD-806), never PASS.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from corpus_support import commit_tree
from rust_repository import component, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

VOCAB = "#[derive(PartialEq)]\npub enum Profile {\n    Python,\n    Dart,\n}\n"
BASE = "mod vocab;\npub use vocab::Profile;\npub type Alias = vocab::Profile;\npub fn make() {}\n"
RENAMED = "mod vocab;\npub use vocab::Profile as Lang;\npub fn make() {}\n"
# An item-place macro call: the scan does not prove a route through this root to its end.
OPAQUE = "macro_rules! nothing {\n    () => {};\n}\nnothing!();\n"
# (name, root of base, source of app, status)
PLANTS = [
    (
        "use",
        BASE,
        "use base_crate::Profile;\npub fn f(p: Profile) -> bool {\n    p == Profile::Dart\n}\n",
        "FAIL",
    ),
    ("path", BASE, "pub fn f() {\n    let _x = base_crate::Profile::Dart;\n}\n", "FAIL"),
    (
        "use alias",
        BASE,
        "use base_crate::Profile as P;\npub fn f() {\n    let _x = P::Dart;\n}\n",
        "FAIL",
    ),
    (
        "variant",
        BASE,
        "use base_crate::Profile::Dart;\npub fn f() {\n    let _x = Dart;\n}\n",
        "FAIL",
    ),
    (
        "glob of the enum",
        BASE,
        "use base_crate::Profile::*;\npub fn f() {\n    let _x = Dart;\n}\n",
        "FAIL",
    ),
    (
        "local type alias",
        BASE,
        "type L = base_crate::Profile;\npub fn f() {\n    let _x = L::Dart;\n}\n",
        "FAIL",
    ),
    (
        "macro body",
        BASE,
        "macro_rules! d {\n    () => {\n        base_crate::Profile::Dart\n    };\n}\n"
        "pub fn f() {\n    let _x = d!();\n}\n",
        "FAIL",
    ),
    (
        "re-export under another name",
        RENAMED,
        "pub fn f() {\n    let _x = base_crate::Lang::Dart;\n}\n",
        "FAIL",
    ),
    (
        "glob of the crate",
        BASE,
        "use base_crate::*;\npub fn f() {\n    let _x = Profile::Dart;\n    make();\n}\n",
        "FAIL",
    ),
    (
        "unproven route beside a rename",
        OPAQUE + RENAMED,
        "pub fn f() {\n    let _x = base_crate::Lang::Dart;\n}\n",
        "UNKNOWN",
    ),
    (
        "unproven route and no rename",
        OPAQUE + BASE,
        "pub fn f() {\n    base_crate::make();\n}\n",
        "UNKNOWN",
    ),
    (
        "type alias of base",
        BASE,
        "pub fn f() {\n    let _x = base_crate::Alias::Dart;\n}\n",
        "UNKNOWN",
    ),
    ("no use of the item", BASE, "pub fn f() {\n    base_crate::make();\n}\n", "UNKNOWN"),
]
RULE = rule(
    "NO-PROFILE",
    "forbidden_dependency",
    source="native.app",
    target="native",
    target_symbol="Profile",
    include_type_checking=True,
)


@pytest.mark.parametrize(("name", "base", "app", "status"), PLANTS, ids=[p[0] for p in PLANTS])
def test_each_rust_form_that_names_the_item_never_passes(
    core_binary: Path, tmp_path: Path, name: str, base: str, app: str, status: str
) -> None:
    files = {
        "crates/base/src/lib.rs": base,
        "crates/base/src/vocab.rs": VOCAB,
        "crates/app/src/lib.rs": app,
    }
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    repository(tmp_path, core_binary, files, parts, (RULE,))
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.14.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(tmp_path)
    _rustc_accepts(tmp_path)
    result = validate(tmp_path)
    assert statuses(result)["NO-PROFILE"] == status, (name, result["frame"].get("details"))
