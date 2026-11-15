# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python sources and the UML targets of the symbol plants (AD-518).

A `Plant` is one module `demo/m.py`, the entities that its target plans (parents first), the row of
release 4.0.1 on the same tree (`four`), the row of the core (`core`) and the truth: whether
Python binds the planned entities when the module runs (`PASS`) or not (`DIFF`).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PUBLIC = {"kind": "public", "basis": "declared"}


@dataclass(frozen=True)
class Want:
    """One planned entity below the module `demo.m`: `name` is its qualified name below it."""

    kind: str
    name: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plant:
    source: str
    wants: tuple[Want, ...]
    truth: str
    four: str = "UNKNOWN"
    core: str = "UNKNOWN"
    files: dict[str, str] = field(default_factory=dict)
    cause: str = ""


def entity(identity: str, kind: str, name: str, parent: str, extra: dict) -> dict:
    return {
        "id": identity,
        "kind": kind,
        "qualified_name": name,
        "parent_id": parent,
        "language": "python",
        "presence": "planned",
        "provenance": ["docs/target.md"],
        "responsibilities": ["Hold it."],
        **extra,
    }


def contract(wants: tuple[Want, ...]) -> dict:
    ids = {want.name: f"e{index}" for index, want in enumerate(wants)}
    entities = [entity("m", "module", "demo.m", "demo-component", {"file_path": "demo/m.py"})]
    for want in wants:
        holder = want.name.rsplit(".", 1)[0] if "." in want.name else ""
        parent = ids[holder] if holder in ids else "m"
        entities.append(
            entity(ids[want.name], want.kind, f"demo.m.{want.name}", parent, want.extra)
        )
    component = {
        "id": "demo-component",
        "label": "demo",
        "role": "component",
        "packages": ["demo"],
        "namespace": "demo",
        "responsibilities": ["Hold the plants."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    uml = {"schema_version": "1.1.0", "entities": entities, "relationships": [], "scopes": []}
    return {
        "schema_version": "2.2.0",
        "components": [component],
        "rules": [],
        "declarations": {"uml": uml},
    }


def project(root: Path, plant: Plant) -> Path:
    """Write the tree of a plant below `root` and return the project root."""
    (root / "demo").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("# Plant\n")
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["demo"]\nnamespace = "demo"\ncontract = "architecture-contract.json"\n'
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "plant"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
    )
    (root / "architecture-contract.json").write_text(json.dumps(contract(plant.wants)))
    (root / "demo/__init__.py").write_text("")
    (root / "demo/m.py").write_text(plant.source)
    for name, text in plant.files.items():
        (root / "demo" / name).write_text(text)
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
