# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2028, #2050: code that the scan does not read is dropped only when it is proven foreign.

The tests run `cargo run` as the oracle: the code that the scan does not read runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rust_repository import repository, validate
from test_cli_native_rust_non_member_crate import (
    FOREIGN_X,
    MARKED_MAIN,
    PARTS,
    _app,
    _forbid,
    _reasons,
    _recommit,
    _run_marker,
    pytestmark,
)

__all__ = ["pytestmark"]


def test_a_path_dependency_outside_the_scan_roots_does_not_hide_an_edge(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["app", "base"]\n',
        "crates/app/Cargo.toml": _app('x = { path = "../../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "vendor/x/Cargo.toml": FOREIGN_X
        + '[dependencies]\nbase-crate = { path = "../../crates/base" }\n',
        "vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=PARTS, rules=_forbid(True)
    )
    _recommit(root)
    assert _run_marker(root, "crates/app/Cargo.toml") == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]
    assert any(
        "not a workspace member" in r or "no workspace member" in r for r in _reasons(result)
    )


def _broken_cargo(root: Path) -> None:
    """A manifest that Cargo cannot load: `cargo metadata` fails and proves no membership."""
    app = root / "crates/app/Cargo.toml"
    app.write_text(app.read_text() + 'missing = { path = "../does-not-exist" }\n')
    _recommit(root)


def test_a_failed_cargo_metadata_names_each_crate_it_cannot_prove_foreign(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app"]\nexclude = ["vendor/erdep"]\n',
        "crates/vendor/erdep/Cargo.toml": FOREIGN_X.replace('"x"', '"erdep"'),
        "crates/vendor/erdep/src/lib.rs": "pub fn f() {}\n",
    }
    root = repository(tmp_path / "repo", release_core, files=layout, components=PARTS)
    _broken_cargo(root)
    result = validate(root)
    reasons: list[Any] = _reasons(result)
    assert any("crates/vendor/erdep" in r for r in reasons), reasons
    assert result["frame"]["rules"]["ASSIGNED"][1] != "PASS", result["frame"]["rules"]
