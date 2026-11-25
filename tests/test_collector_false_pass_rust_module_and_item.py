# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1405: a path that ends at a module may name an item of the same name, so it never passes.

`base` declares `pub mod reply;` and an item `reply` in two namespaces (written, or taken by a
glob). `app` calls the function. rustc accepts each plant. Before #1405 the Rust collector wrote an
import of the module only, so a `target_symbol` rule on `reply` and an `interface_boundary` that
lists only the module gave PASS. Now such a path is a gap (UNKNOWN). A path into the module, and a
module without a same-named item, keep their verdicts.
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

WRITTEN = "pub mod reply;\npub fn reply() {}\n"
GLOBBED = "pub mod reply;\nmod other;\npub use other::*;\n"
ALONE = "pub mod reply;\n"
USE_FN = "use base_crate::reply;\npub fn f() {\n    reply();\n}\n"
PATH_FN = "pub fn f() {\n    base_crate::reply();\n}\n"
INTO_MODULE = "pub fn f() {\n    base_crate::reply::inner();\n}\n"
USE_MODULE = "use base_crate::reply;\npub fn f() {\n    reply::inner();\n}\n"
# (name, root of base, app, status of both rules)
PLANTS = [
    ("use of the function beside a module", WRITTEN, USE_FN, "UNKNOWN"),
    ("path to the function beside a module", WRITTEN, PATH_FN, "UNKNOWN"),
    ("path to a globbed function beside a module", GLOBBED, PATH_FN, "UNKNOWN"),
    ("path into the module", WRITTEN, INTO_MODULE, "PASS"),
    ("use of a module without a same-named item", ALONE, USE_MODULE, "PASS"),
]
RULES = (
    rule(
        "NO-REPLY-FN",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate",
        target_symbol="reply",
        include_type_checking=True,
    ),
    rule("BOUNDARY", "interface_boundary"),
)


@pytest.mark.parametrize(("name", "base", "app", "status"), PLANTS, ids=[p[0] for p in PLANTS])
def test_a_path_that_ends_at_a_module_never_hides_the_item_of_its_name(
    core_binary: Path, tmp_path: Path, name: str, base: str, app: str, status: str
) -> None:
    files = {
        "crates/base/src/lib.rs": base,
        "crates/base/src/reply.rs": "pub fn inner() {}\n",
        "crates/app/src/lib.rs": app,
    }
    if "mod other;" in base:
        files["crates/base/src/other.rs"] = "pub fn reply() {}\n"
    # The interface lists the module only: the function `reply` is not public.
    owner = {**component("base", "base_crate"), "public": ["native.base_crate.reply"]}
    repository(tmp_path, core_binary, files, (owner, component("app", "app", ("base",))), RULES)
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    if "declarations" not in contract:  # a contract with the type-reach premise needs 3.22.0
        contract["schema_version"] = "3.14.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(tmp_path)
    _rustc_accepts(tmp_path)
    found = statuses(validate(tmp_path))
    # AD-1048: no function `reply` exists in `base`, so the symbol rule examined nothing.
    symbol = "UNKNOWN" if name.startswith("use of a module without") else status
    assert (found["NO-REPLY-FN"], found["BOUNDARY"]) == (symbol, status), name
