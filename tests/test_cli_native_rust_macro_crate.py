# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-614: a call of an exported macro takes the `$crate` edges of its body.

`$crate` names the crate that defines the macro wherever the macro expands, so the call of a
portable body (only `$crate` paths and `std` expression macros) in another crate names the same
modules. The rule then judges each name of the expansion. A body with a bare `crate` path names the
crate of the call: the scan cannot place it, and the run stays UNKNOWN. rustc accepts each plant.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import component
from test_cli_native_rust_interface import _run

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

HEAD = "#[macro_export]\nmacro_rules! circle {\n    () => {\n"
PORTABLE = HEAD + "        $crate::shapes::Circle\n    };\n}\n"
BARE = HEAD + "        crate::shapes::Circle\n    };\n}\n"
LIB = "pub mod shapes;\n"
SHAPES = "pub struct Circle;\n"
EXPANDED = (
    "BOUNDARY: native.app -> native.base_crate.shapes:Circle: import outside the public interface"
)
# (name, macro, call in app, public of base, status of the rule)
PLANTS = [
    (
        "portable call",
        PORTABLE,
        "pub fn run() {\n    let _ = base_crate::circle!();\n}\n",
        [],
        "FAIL",
    ),
    (
        "portable call through a use",
        PORTABLE,
        "use base_crate::circle;\npub fn run() {\n    let _ = circle!();\n}\n",
        [],
        "FAIL",
    ),
    (
        "portable call of a public name",
        PORTABLE,
        "pub fn run() {\n    let _ = base_crate::circle!();\n}\n",
        ["native.base_crate.shapes:Circle"],
        "PASS",
    ),
    ("bare crate path", BARE, "pub fn run() {}\n", [], "UNKNOWN"),
]


@pytest.mark.parametrize(("name", "macro", "call", "more", "status"), PLANTS)
def test_a_portable_exported_macro_gives_its_edges_to_each_call(
    core_binary: Path,
    tmp_path: Path,
    name: str,
    macro: str,
    call: str,
    more: list[str],
    status: str,
) -> None:
    base = {**component("base", "base_crate"), "public": ["native.base_crate:circle", *more]}
    app = component("app", "app", ("base",))
    files = {
        "crates/base/src/lib.rs": LIB + macro,
        "crates/base/src/shapes.rs": SHAPES,
        "crates/app/src/lib.rs": call,
    }
    found_status, found = _run(tmp_path, core_binary, files, (base, app))
    assert found_status == status, (name, found)
    assert (EXPANDED in found) == (status == "FAIL"), (name, found)
