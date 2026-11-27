# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2184: a baseline never takes one orphan file of a Rust crate for another.

The gap "Source file is in no module tree: <file>" names its file in the reason and has an empty
subject. Deleting one orphan file and adding another is a new finding: the baseline is drift with
one new entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from rust_repository import CRATE_RULES, repository

from archkeel.cli import core_only


def baseline(core: Path, root: Path, *flags: str) -> tuple[int, dict[str, Any]]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core)
        return run("validate", "--root", str(root), *flags)


def test_one_orphan_file_replaced_by_another_is_drift_with_one_new_entry(
    tmp_path: Path, release_core: Path
) -> None:
    root = repository(
        tmp_path / "repo",
        release_core,
        rules=CRATE_RULES,
        files={"crates/app/src/a.rs": "pub fn orphan() {}\n"},
    )
    baseline(release_core, root, "--write-baseline", "b.json")
    document = json.loads((root / "b.json").read_text(encoding="utf-8"))
    assert any("a.rs" in row["reason"] for row in document["unknowns"]), document["unknowns"]
    (root / "crates/app/src/a.rs").unlink()
    (root / "crates/app/src/c.rs").write_text("pub fn orphan() {}\n")
    _code, result = baseline(release_core, root, "--baseline", "b.json")
    found = result["frame"]["baseline"]
    assert found["state"] == "drift", found
    assert [row["reason"] for row in found["new"] if "c.rs" in row["reason"]], found["new"]
    assert len(found["new"]) == 1 and len(found["gone"]) == 1, found
