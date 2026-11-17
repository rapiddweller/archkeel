# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1450, AD-718: the Rust collector states each public module-level item, or names the one that
it cannot read, so `unused_public` can PASS on Rust and never passes a missing item.

Consumer: `archkeel validate`. `base` publishes items, `app` uses `used`. rustc accepts each plant.
An item of an `extern` block and an item that a macro call writes with a literal name are stated:
FAIL without a user. An item whose name the macro call gives is not read: UNKNOWN. A visibility
that the call gives as `pub(crate)` is no public item. A crate whose public items all have a user
is PASS.
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

USED = "pub fn used() {}\n"
APP = "pub fn run() {\n    base_crate::used();\n}\n"
MACRO = (
    "macro_rules! mk {\n    ($v:vis, $n:ident) => {\n"
    "        $v fn $n() {}\n        pub fn made() {}\n    };\n}\n"
)
NAMED = "macro_rules! mk {\n    ($n:ident) => {\n        pub fn $n() {}\n    };\n}\n"
VIS = "macro_rules! mk {\n    ($v:vis) => {\n        $v fn hidden() {}\n    };\n}\n"
# name: (base lib.rs, app lib.rs, the verdict, the FAIL rows)
PLANTS = {
    "each public item has a user": (USED, APP, "PASS", []),
    "an unused function of an extern block": (
        USED + 'extern "C" {\n    pub fn ext();\n}\n',
        APP,
        "FAIL",
        ["native.base_crate:ext"],
    ),
    "a used function of an extern block": (
        USED + 'extern "C" {\n    pub fn ext();\n}\n',
        "pub fn run() {\n    base_crate::used();\n    unsafe { base_crate::ext() }\n}\n",
        "PASS",
        [],
    ),
    "a macro call that writes an unused item with a literal name": (
        USED + MACRO + "mk!(pub(crate), kept);\nfn call() {\n    kept();\n}\n",
        APP,
        "FAIL",
        ["native.base_crate:made"],
    ),
    "a macro call that gives the name of a public item": (
        USED + NAMED + "mk!(made);\n",
        APP,
        "UNKNOWN",
        [],
    ),
    "a macro call that gives the visibility pub(crate)": (
        USED + VIS + "mk!(pub(crate));\nfn call() {\n    hidden();\n}\n",
        APP,
        "PASS",
        [],
    ),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_each_public_item_is_stated_or_named_as_unread(
    core_binary: Path, tmp_path: Path, name: str
) -> None:
    base, app, verdict, rows = PLANTS[name]
    unused = rule("UNUSED", "unused_public", source="native.base_crate")
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    files = {"crates/base/src/lib.rs": base, "crates/app/src/lib.rs": app}
    root = repository(tmp_path, core_binary, files, parts, (unused,))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.16.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(root)
    _rustc_accepts(root)
    result = validate(root)
    found = sorted(row["target"] for row in result["frame"].get("details", {}).get("UNUSED", []))

    assert (statuses(result)["UNUSED"], found) == (verdict, rows), name
