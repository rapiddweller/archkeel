# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The project of a `boundary_types` plant (AD-550): one component `api`, one rule `API-TYPES`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from boundary_types_plants import Plant

RULE = "API-TYPES"


def contract(plant: Plant) -> dict[str, Any]:
    component = {
        "id": "comp-api",
        "label": "api",
        "role": "component",
        "packages": ["app"],
        "namespace": "app",
        "responsibilities": ["Hold the plants."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/p.md"],
        "decided_by": "architect",
        "public": list(plant.public),
    }
    rule: dict[str, Any] = {
        "id": RULE,
        "kind": "boundary_types",
        "source": "app.api",
        "rationale": "The facade is typed.",
        "provenance": ["docs/p.md"],
        "decided_by": "architect",
    }
    if plant.allowed:
        rule["allowed_positions"] = list(plant.allowed)
    return {"schema_version": "3.3.0", "components": [component], "rules": [rule]}


def project(root: Path, plant: Plant) -> Path:
    """Write the tree of a plant below `root` and return the project root."""
    (root / "app").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/p.md").write_text("# Plant\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "p"\nversion = "0"\nrequires-python = ">=3.11"\n'
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["app"]\nnamespace = "app"\ncontract = "architecture-contract.json"\n'
    )
    (root / "architecture-contract.json").write_text(json.dumps(contract(plant)))
    (root / "app/__init__.py").write_text("")
    for name, text in {"api.py": plant.api, **plant.files}.items():
        (root / "app" / name).write_text(text)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root
