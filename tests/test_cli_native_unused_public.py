# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-670: `unused_public` names each public item that no other component uses.

Rust (rustc accepts each plant): `base` publishes items, `app` uses some of them. A function or a
constant with no user in `app` is FAIL. A use through a re-export, a use by the binary of the
package (AD-622) and an item listed in `external_users` are no violation. A type with no user and
an item of a module that `app` takes by a glob are undecided. The Rust collector does not state
every public symbol, so a run without a violation is UNKNOWN and never PASS.

Python (python3.12 runs each plant): its collector states every public symbol, so a run where
each public function has a user is PASS, and an unused one is FAIL.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from rust_repository import component, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts

from archkeel.cli import core_only

BASE = """mod inner;
pub mod globbed;
pub use inner::reexported;
pub fn used() {}
pub fn unused_fn() {}
pub const UNUSED: u8 = 1;
pub struct UnusedType;
pub fn only_in_base() {}
pub(crate) fn hidden() {}
pub fn bin_only() {}
pub fn external() {}
pub fn twice() {
    only_in_base();
    hidden();
}
"""
INNER = "pub fn reexported() {}\n"
GLOBBED = "pub fn taken_by_glob() {}\n"
APP = """use base_crate::globbed::*;
pub fn run() {
    base_crate::used();
    base_crate::reexported();
    taken_by_glob();
}
"""
MAIN = "fn main() {\n    base_crate::bin_only();\n}\n"
USER = {
    "symbol": "native.base_crate:external",
    "consumer": "a plugin that loads the library",
    "rationale": "The plugin is not in the scan.",
}


def _rust(root: Path, binary: Path, files: dict[str, str], **fields: Any) -> dict[str, Any]:
    sources = {
        "crates/base/src/lib.rs": BASE,
        "crates/base/src/inner.rs": INNER,
        "crates/base/src/globbed.rs": GLOBBED,
        "crates/base/src/main.rs": MAIN,
        "crates/app/src/lib.rs": APP,
        **files,
    }
    unused = rule("UNUSED", "unused_public", source="native.base_crate", **fields)
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    repository(root, binary, sources, parts, (unused,))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.16.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(root)
    _rustc_accepts(root)
    return validate(root)


def _targets(result: dict[str, Any]) -> list[str]:
    return sorted(row["target"] for row in result["frame"].get("details", {}).get("UNUSED", []))


pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")


def test_each_unused_function_and_constant_fails_and_each_proven_use_passes(
    core_binary: Path, tmp_path: Path
) -> None:
    result = _rust(tmp_path, core_binary, {}, external_users=[USER])
    assert statuses(result)["UNUSED"] == "FAIL"
    assert _targets(result) == [
        "native.base_crate:UNUSED",
        "native.base_crate:only_in_base",
        "native.base_crate:unused_fn",
    ]


def test_item_kinds_limit_the_rule_and_an_unlisted_external_user_fails(
    core_binary: Path, tmp_path: Path
) -> None:
    result = _rust(tmp_path, core_binary, {}, item_kinds=["function"])
    assert _targets(result) == [
        "native.base_crate:external",
        "native.base_crate:only_in_base",
        "native.base_crate:unused_fn",
    ]


def test_a_rust_run_without_a_violation_is_unknown_and_never_passes(
    core_binary: Path, tmp_path: Path
) -> None:
    files = {
        "crates/base/src/lib.rs": "pub mod globbed;\npub fn used() {}\npub struct UnusedType;\n",
        "crates/base/src/main.rs": "fn main() {}\n",
        "crates/app/src/lib.rs": "use base_crate::globbed::*;\n"
        "pub fn run() {\n    base_crate::used();\n    taken_by_glob();\n}\n",
    }
    result = _rust(tmp_path, core_binary, files)
    assert statuses(result)["UNUSED"] == "UNKNOWN"
    assert _targets(result) == []


def test_a_malformed_external_user_refuses_the_contract(core_binary: Path, tmp_path: Path) -> None:
    bad = {**USER, "symbol": "native.base_crate.external"}
    result = _rust(tmp_path, core_binary, {}, external_users=[bad])
    assert "module:Name" in json.dumps(result), result


PY_BASE = (
    "def used():\n    return 1\n\n\ndef unused():\n    return 2\n\n\n"
    "def _private():\n    return 3\n"
)
PY_APP_ALL = "from pkg.base import unused, used\n\nX = used() + unused()\n"
PY_APP_ONE = "from pkg.base import used\n\nX = used()\n"


def _python(root: Path, binary: Path, app: str) -> dict[str, Any]:
    files = {
        "pkg/__init__.py": "",
        "pkg/base/__init__.py": PY_BASE,
        "pkg/app/__init__.py": app,
        "docs/target.md": "# Target\n",
        "archkeel.toml": '[scan]\nlanguage = "python"\nroots = ["pkg"]\nnamespace = "pkg"\n'
        'python = "3.12"\ncontract = "architecture-contract.json"\n',
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    parts = [
        {**component(label, label), "packages": [f"pkg.{label}"], "requires": []}
        for label in ("base", "app")
    ]
    unused = rule("UNUSED", "unused_public", source="pkg.base", item_kinds=["function"])
    unused["provenance"] = ["docs/target.md"]
    for part in parts:
        part["provenance"] = ["docs/target.md"]
    contract = {"schema_version": "3.16.0", "components": parts, "rules": [unused]}
    (root / "architecture-contract.json").write_text(json.dumps(contract, indent=2))
    commit_tree(root)
    truth = subprocess.run(
        ["python3.12", "-I", "-c", "import sys; sys.path.insert(0, '.'); import pkg.app"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert truth.returncode == 0, truth.stderr
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        return run("validate", "--root", str(root))[1]


@pytest.mark.skipif(shutil.which("python3.12") is None, reason="python3.12 is the oracle")
@pytest.mark.parametrize(
    ("app", "status", "targets"),
    [(PY_APP_ALL, "PASS", []), (PY_APP_ONE, "FAIL", ["pkg.base:unused"])],
    ids=["each function has a user", "one function has no user"],
)
def test_python_states_every_public_symbol_so_a_run_can_pass(
    core_binary: Path, tmp_path: Path, app: str, status: str, targets: list[str]
) -> None:
    result = _python(tmp_path, core_binary, app)
    assert result["frame"]["rules"]["UNUSED"][1] == status, result["frame"].get("explained")
    assert _targets(result) == targets
