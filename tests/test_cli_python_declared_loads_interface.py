# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1500: a declared `loads` list is read by the interface rules, through the release core.

Consumer: a CI job that reads the row of an `interface_boundary` rule. A registry that loads its
tasks by `importlib.import_module(name)` declares the tasks in `loads`. Each loaded module that its
owner lists in `public` is a PASS; a loaded module that is not public is a FAIL; a module that the
scan does not hold is a named gap.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from python_interface_plants import GRAPH
from test_cli_native_python_imports import rows, verdict
from test_cli_python_trojan_horse_reach import GIT

REGISTRY = "src/app/registry.py"
SOURCE = "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
BASE = {
    "role": "component",
    "responsibilities": ["Own the modules."],
    "forbidden_responsibilities": [],
    "provenance": ["docs/target.md"],
    "decided_by": "architect",
    "requires": [],
}


def part(name: str, **owned: Any) -> dict[str, Any]:
    return {**BASE, "id": name, "label": name, **owned}


def declared(loads: list[str]) -> dict[str, Any]:
    return {
        "id": "D-LOAD",
        "module": "app.registry",
        "name": "import_module",
        "scope": "load",
        "loads": loads,
        "rationale": "The registry loads the task modules.",
        "provenance": ["docs/target.md"],
    }


def scan(root: Path, binary: Path, loads: list[str], public: list[str], extra: bool = False) -> Any:
    files = {
        "src/app/__init__.py": "",
        REGISTRY: SOURCE,
        "src/app/tasks/__init__.py": "",
        "src/app/tasks/a.py": "A = 1\n",
        "src/app/tasks/b.py": "B = 2\n",
        "docs/target.md": GRAPH,
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "archkeel.toml": (
            '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        ),
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    contract = {
        "schema_version": "3.20.0",
        "components": [
            part("root", packages=[], exact_modules=["app"]),
            part("registry", packages=[], exact_modules=["app.registry"]),
            part("tasks", packages=["app.tasks"], public=public),
        ],
        "declarations": {"trojan_horse_reach": [declared(loads)]},
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
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=GIT)
    return verdict(binary, root)


def test_a_declared_module_below_the_public_interface_is_a_pass(
    release_core: Path, tmp_path: Path
) -> None:
    result = scan(
        tmp_path, release_core, ["app.tasks.a", "app.tasks.b"], ["app.tasks.a", "app.tasks.b"]
    )
    assert rows(result)["BOUNDARY"] == "PASS", result["frame"]["explained"]


def test_a_declared_prefix_that_covers_a_module_outside_the_interface_is_a_fail(
    release_core: Path, tmp_path: Path
) -> None:
    result = scan(tmp_path, release_core, ["app.tasks"], ["app.tasks.a"])
    assert rows(result)["BOUNDARY"] == "FAIL", result["frame"]["explained"]


def test_a_module_that_a_name_entry_lists_only_in_part_is_named_not_passed(
    release_core: Path, tmp_path: Path
) -> None:
    result = scan(tmp_path, release_core, ["app.tasks.a"], ["app.tasks.a:A"])
    assert rows(result)["BOUNDARY"] == "UNKNOWN", result["frame"]["explained"]


def test_a_declared_module_that_the_scan_does_not_hold_is_a_named_gap_and_never_a_pass(
    release_core: Path, tmp_path: Path
) -> None:
    result = scan(tmp_path, release_core, ["app.ghost"], ["app.tasks.a"])
    kinds = {gap["kind"] for gap in result["gaps"]}
    assert "trojan_horse_reach.invalid" in kinds, kinds
    assert rows(result)["BOUNDARY"] == "UNKNOWN", result["frame"]["explained"]
