# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-504: the plants of the delta review of #1178, through the release core.

Consumer: a CI job that reads the row of an `interface_boundary` rule on Python. The plants write
to a package from another module, bind a package name by a statement that is no plain top-level
one, or open a package with `__getattr__`. Python binds something other than the public thing, so
the row must not be PASS. The plants of `OPEN` are named open false PASS and pinned as PASS.
These plants fail against `05a34180b`, the head that the review attacked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from python_interface_plants import GRAPH
from python_review_plants import OPEN, PLANTS
from test_cli_native_python_imports import rows, verdict


def contract(plant: dict[str, Any]) -> dict[str, Any]:
    base = {
        "role": "component",
        "responsibilities": ["Own the modules."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
        "requires": [],
    }

    def part(name: str, **owned: Any) -> dict[str, Any]:
        return {**base, "id": name, "label": name, **owned}

    extra = [
        "app." + key[len("src/app/") : -3].replace("/", ".")
        for key in plant["files"]
        if key.startswith("src/app/")
    ]
    return {
        "schema_version": "2.2.0",
        "components": [
            part("root", packages=[], exact_modules=["app"]),
            part("consumer", packages=[], exact_modules=["app.consumer", *extra]),
            part("lib", packages=["app.lib"], public=plant["public"]),
        ],
        "rules": [
            {
                "id": "BOUNDARY",
                "kind": "interface_boundary",
                "rationale": "Callers use the declared interface.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
                "include_type_checking": True,
            }
        ],
    }


def build(root: Path, plant: dict[str, Any]) -> Path:
    files = {
        "src/app/__init__.py": "",
        "src/app/consumer.py": plant["consumer"],
        "docs/target.md": GRAPH,
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "archkeel.toml": (
            '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        ),
    }
    for key, text in plant["files"].items():
        place = key if key.startswith(("src/", "ROOT/")) else "src/app/lib/" + key
        files[place.removeprefix("ROOT/")] = text
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "architecture-contract.json").write_text(json.dumps(contract(plant), indent=1))
    from corpus_support import commit_tree

    commit_tree(root)
    return root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_no_plant_gives_a_pass_that_python_does_not_back(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    root = tmp_path / "p"
    root.mkdir()
    row = rows(verdict(release_core, build(root, plant)))["BOUNDARY"]
    if name in OPEN:
        assert row == "PASS", (name, row)
    elif plant["truth"] == "FAIL":
        assert row != "PASS", (name, row)
    else:
        assert row != "FAIL", (name, row)
