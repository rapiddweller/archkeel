# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python `interface_boundary` differential (AD-504, #880).

One consumer module imports from one library component. Each plant sets the public entries of the
library, the files of the library and the import of the consumer. `FOUR` holds the verdict of
release 4.0.1 for the plant: its `report` on the same tree, one run of
`/private/tmp/oracle-401/bin/archkeel report --json` for each plant (read-only oracle).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAPH = "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n    root\n```\n"
LIB = "src/app/lib/__init__.py"
IMPL = "src/app/lib/impl.py"
DEFINES = "def f(): pass\ndef g(): pass\n"
REEXPORTS = "from app.lib.impl import f\n"


@dataclass(frozen=True)
class Plant:
    """One tree: the library files, the public entries and the import of the consumer."""

    name: str
    consumer: str
    public: tuple[str, ...]
    files: dict[str, str] = field(default_factory=dict)
    # The verdict of 4.0.1 and the verdicts that the core may give (the same, or a documented
    # stricter one). A core PASS is allowed only where 4.0.1 gives PASS.
    four: str = "PASS"
    core: tuple[str, ...] = ("PASS",)
    why: str = ""


def plants() -> list[Plant]:
    p = Plant
    return [
        p("module public, name defined", "from app.lib import f\n", ("app.lib",), {LIB: DEFINES}),
        p("module public, no __all__", "from app.lib import g\n", ("app.lib",), {LIB: DEFINES}),
        p(
            "name outside a literal __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "name inside a literal __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n"},
        ),
        p(
            "private name",
            "from app.lib import _f\n",
            ("app.lib",),
            {LIB: "def _f(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "exact symbol entry",
            "from app.lib.impl import f\n",
            ("app.lib.impl:f",),
            {LIB: "", IMPL: DEFINES},
        ),
        p(
            "other symbol than the exact entry",
            "from app.lib.impl import g\n",
            ("app.lib.impl:f",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "submodule of a public module",
            "from app.lib.impl import f\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "reexport covered at the first hop",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: REEXPORTS + "__all__ = ['f']\n", IMPL: DEFINES},
        ),
        p(
            "reexport covered only at the second hop",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: REEXPORTS, IMPL: DEFINES},
        ),
        p(
            "reexport not covered at any hop",
            "from app.lib import f\n",
            ("app.lib.impl:g",),
            {LIB: REEXPORTS, IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p("module object of a public module", "import app.lib\n", ("app.lib",), {LIB: DEFINES}),
        p(
            "module object of a hidden module",
            "import app.lib.impl\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "module with __getattr__, no __all__",
            "from app.lib import lazy\n",
            ("app.lib",),
            {LIB: "def __getattr__(name): return name\n"},
        ),
        p(
            "name in a dynamic __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f'] + ['g']\n"},
            core=("UNKNOWN",),
            why="4.0.1 reads the literal strings; the core cannot read the rest of __all__",
        ),
        p(
            "name outside a dynamic __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f'] + more()\n"},
            core=("UNKNOWN",),
            why="the unread part of __all__ may exclude g; 4.0.1 passes it (false PASS)",
        ),
        p(
            "all of a computed __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = compute()\n"},
            core=("UNKNOWN",),
            why="4.0.1 treats an unreadable __all__ as none and passes every name (false PASS)",
        ),
        p(
            "augmented __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n__all__ += ['g']\n"},
            core=("UNKNOWN",),
            why="the core reads one literal __all__ only",
        ),
        p(
            "binding with two sources",
            "from app.lib import f\n",
            ("app.lib",),
            {
                LIB: "try:\n    from app.lib.impl import f\n"
                "except ImportError:\n    from app.lib.impl import g as f\n",
                IMPL: DEFINES,
            },
            core=("PASS", "UNKNOWN"),
            why="an alias with two targets is not a proven route",
        ),
        p(
            "alias of a private name",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: "from app.lib.impl import _g as f\n", IMPL: "def _g(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "binding redefined after the re-export",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: REEXPORTS + "def f(): pass\n", IMPL: DEFINES},
            four="UNKNOWN",
            core=("UNKNOWN",),
        ),
        p(
            "type-checking import of a hidden name",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.lib.impl import f\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
    ]


def build(root: Path, plant: Plant) -> Path:
    """Write the tree of one plant below `root` and commit it."""
    files = {
        "src/app/__init__.py": "",
        "src/app/consumer.py": plant.consumer,
        "docs/target.md": GRAPH,
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "archkeel.toml": (
            '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        ),
        **plant.files,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "architecture-contract.json").write_text(json.dumps(contract(plant), indent=1))
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


def contract(plant: Plant) -> dict[str, Any]:
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

    return {
        "schema_version": "2.2.0",
        "components": [
            part("root", packages=[], exact_modules=["app"]),
            part("consumer", packages=[], exact_modules=["app.consumer"]),
            part("lib", packages=["app.lib"], public=list(plant.public)),
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
