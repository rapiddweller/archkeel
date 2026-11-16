# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-622: a binary target that uses its library is a use of a public entry.

The library root publishes `make` for the binary of its own package (AD-608), and the contract
lists it. The binary is a crate of its own in the component of the library. Its import crosses the
crate boundary, so the usage check counts it. A use in the library itself crosses no crate and
counts not, and an entry that nothing uses keeps `interface.usage_unknown`. rustc accepts each
plant.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from corpus_support import commit_tree
from rust_repository import component, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "mod inner;\npub use inner::make;\n"
INNER = "pub fn make() {}\n"
BINARY = "fn main() {\n    base_crate::make();\n}\n"
INTERNAL = "mod inner;\npub use inner::make;\npub fn twice() {\n    crate::make();\n}\n"
ENTRY = "native.base_crate:make"
# (name, library root, binary, the entry has a usage gap)
PLANTS = [
    ("a binary of the package uses the entry", LIB, BINARY, False),
    ("nothing uses the entry", LIB, None, True),
    ("only the library itself uses the entry", INTERNAL, None, True),
]


def _result(root: Path, binary: Path, files: dict[str, str]) -> dict[str, Any]:
    base = {**component("base", "base_crate"), "public": [ENTRY]}
    rules = (rule("BOUNDARY", "interface_boundary"),)
    repository(root, binary, files, (base, component("app", "app", ("base",))), rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.14.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(root)
    _rustc_accepts(root)
    return validate(root)


@pytest.mark.parametrize(("name", "lib", "main", "gap"), PLANTS)
def test_a_binary_of_the_package_is_a_use_of_the_entry(
    core_binary: Path, tmp_path: Path, name: str, lib: str, main: str | None, gap: bool
) -> None:
    files = {
        "crates/base/src/lib.rs": lib,
        "crates/base/src/inner.rs": INNER,
        "crates/app/src/lib.rs": "pub fn run() {}\n",
    }
    if main is not None:
        files["crates/base/src/main.rs"] = main
    result = _result(tmp_path, core_binary, files)
    usage = [g for g in result["gaps"] if g["kind"] == "interface.usage_unknown"]
    assert bool(usage) == gap, (name, usage)
    assert not usage or ENTRY in usage[0]["subject"] + usage[0]["reason"], usage
    # No import crosses the components: the rule has no violation, the entry only a usage gap.
    assert statuses(result)["BOUNDARY"] == "PASS", (name, result["gaps"])
