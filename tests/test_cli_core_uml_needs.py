# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-502: a run without a UML target has no need, so the frame does not change.

Each case runs one fixture twice through the default CLI and the release core: once without a
UML target and once with one. The UML target is the only need today. The second frame must hold
the UML row and no other difference but the identity of the contract and the status. A run
without a need builds no symbol table, so its frame is the frame of a core without the symbol
code. The same comparison between a core of `main` and this core is in the decision record.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from core_support import run

from archkeel.cli import core_only

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ROW = "UML-TARGET-a2e40c5592b1b06a"
# Fixtures of the three source languages of the core. H-typescript has a UML target of its own.
NAMES = [
    "H-typescript",
    "L-nest-realworld",
    "I-flutter-shop",
    "K-python-realworld",
    "M-review-workflow",
    "J-compass",
]
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


@pytest.fixture(autouse=True)
def release(release_core: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)


def _commit(root: Path, message: str) -> None:
    for command in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run([*GIT, *command], cwd=root, check=True, capture_output=True)


def _copy(tmp_path: Path, name: str) -> Path:
    """A clean repository of the fixture without a UML target in any of its contracts."""
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    for path in [root / "architecture-contract.json", *sorted((root / "contracts").glob("*.json"))]:
        contract = json.loads(path.read_text(encoding="utf-8"))
        declarations = contract.get("declarations", {})
        declarations.pop("uml", None)
        if not declarations:
            contract.pop("declarations", None)
        path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    subprocess.run([*GIT, "init", "-q"], cwd=root, check=True, capture_output=True)
    _commit(root, "fixture")
    return root


def _declare(root: Path) -> None:
    """Add a UML target with one module entity: the run now has the need of the UML target."""
    scan = tomllib.loads((root / "archkeel.toml").read_text(encoding="utf-8"))["scan"]
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    module = {
        "id": "m",
        "kind": "module",
        "qualified_name": f"{scan['namespace']}.nothing",
        "language": scan.get("language", "python"),
        "presence": "planned",
        "provenance": contract["components"][0]["provenance"],
        "responsibilities": ["Hold it."],
    }
    uml = {"schema_version": "1.1.0", "entities": [module], "relationships": [], "scopes": []}
    contract.setdefault("declarations", {})["uml"] = uml
    path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    _commit(root, "uml")


def _frame(root: Path) -> dict[str, Any]:
    _, envelope = run("validate", "--root", str(root))
    frame = envelope["frame"]
    assert isinstance(frame, dict)
    return frame


def _without_target(value: Any) -> Any:
    """The frame without what the contract, its target and its commit own."""
    if isinstance(value, dict):
        return {
            key: _without_target(item)
            for key, item in value.items()
            if ROW not in key and "declarations/uml" not in key and key != "git_head"
        }
    return value


@pytest.mark.parametrize("name", NAMES)
def test_a_uml_target_adds_its_row_and_changes_nothing_else(tmp_path: Path, name: str) -> None:
    root = _copy(tmp_path, name)
    plain = _frame(root)
    assert ROW not in plain["rules"]
    _declare(root)
    needed = _frame(root)
    assert ROW in needed["rules"]
    for frame in (plain, needed):
        for owned in ("contract_digest", "status"):
            frame.pop(owned)
        frame["self_test"]["collect"].pop("contract_files")
    assert _without_target(needed) == _without_target(plain)
