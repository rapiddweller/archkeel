# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A small planted project with one module cycle, for the tests of the report.

Consumer: the report tests that need a failing rule with a cycle row. The self run of the core no
longer has a cycle (#1076), so it cannot show one.
"""

import subprocess
from pathlib import Path

import pytest

CONTRACT = """{
  "schema_version": "2.1.0",
  "components": [
    {
      "id": "COMP-APP",
      "label": "app",
      "role": "component",
      "packages": ["app"],
      "responsibilities": ["The small planted application."],
      "forbidden_responsibilities": ["Nothing else."],
      "provenance": ["docs/why.md"],
      "decided_by": "architect"
    }
  ],
  "rules": [
    {
      "id": "APP-NO-MODULE-CYCLES",
      "kind": "no_component_cycles",
      "level": "module",
      "rationale": "Modules use each other in one direction.",
      "provenance": ["docs/why.md"],
      "decided_by": "architect"
    }
  ]
}
"""
CONFIG = """[scan]
language = "python"
roots = ["app"]
namespace = "app"
contract = "architecture-contract.json"
"""
FILES = {
    "app/__init__.py": "",
    "app/a.py": "from app import b\n\n\ndef one():\n    return b.two()\n",
    "app/b.py": "from app import a\n\n\ndef two():\n    return a.one()\n",
    "docs/why.md": "The modules of the planted project use each other in one direction.\n",
    "archkeel.toml": CONFIG,
    "architecture-contract.json": CONTRACT,
}


@pytest.fixture(scope="session")
def cycle_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A Git repository with the modules `app.a` and `app.b` that import each other."""
    root = tmp_path_factory.mktemp("planted-cycle")
    for name, text in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git = ["git", "-c", "user.email=test@example.com", "-c", "user.name=test"]
    subprocess.run([*git, "init", "-q", str(root)], check=True)
    subprocess.run([*git, "-C", str(root), "add", "-A"], check=True)
    subprocess.run([*git, "-C", str(root), "commit", "-q", "-m", "planted cycle"], check=True)
    return root.resolve()
