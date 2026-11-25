# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1963: a script outside the scan roots that withholds symbol records is named by a gap.

The gap holds only the rules that read symbols. Each edge, layout and cycle rule keeps its verdict.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, RULE, project, verdict

SCRIPT = "import app.service\ngetattr(app.service, 'f')\n"
EDGE_RULES = ("FORBID", "CYCLES", "ASSIGN", "EXTERNAL")
FILES = {
    **BASE,
    "src/app/client.py": "from app.service import f\n\nf()\n",
    "src/app/service.py": "def f() -> None:\n    pass\n",
}


def tree(root: Path, script: str | None) -> Path:
    files = {**FILES, **({"scripts/tool.py": script} if script else {})}
    forbid = {**RULE, "id": "FORBID", "kind": "forbidden_dependency", "include_type_checking": True}
    rules: list[dict[str, Any]] = [
        {**forbid, "source": "app.service", "target": "app.client"},
        {**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"},
        {**RULE, "id": "CYCLES", "kind": "no_component_cycles"},
        {**RULE, "id": "EXTERNAL", "kind": "complete_external_scope", "source": "app"},
        {**RULE, "id": "INTERFACE", "kind": "interface_boundary"},
    ]
    project(root, files, contract_rules=rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    for component in contract["components"]:
        if component["label"] == "service":
            component["public"] = ["app.service:f"]
    path.write_text(json.dumps(contract))
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["add", "-A"], [*who, "commit", "-qm", "public"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return root


def statuses(result: dict[str, Any]) -> dict[str, str]:
    return {rule: row[1] for rule, row in result["frame"]["rules"].items()}


def test_without_a_script_each_rule_passes(release_core: Path, tmp_path: Path) -> None:
    found = statuses(verdict(release_core, tree(tmp_path, None)))
    assert found == {rule: "PASS" for rule in (*EDGE_RULES, "INTERFACE")}


@pytest.mark.parametrize("script", [SCRIPT, "import app.service\nvalue = app.service\n"])
def test_a_script_is_named_and_holds_only_the_symbol_rules(
    release_core: Path, tmp_path: Path, script: str
) -> None:
    result = verdict(release_core, tree(tmp_path, script))
    found = statuses(result)
    assert {rule: found[rule] for rule in EDGE_RULES} == dict.fromkeys(EDGE_RULES, "PASS"), found
    assert found["INTERFACE"] == "UNKNOWN", found
    named = [g["reason"] for g in result["frame"]["collection_gaps"]]
    assert len(named) == 1 and "scripts/tool.py" in named[0], named
    assert "names 1 module of the scan" in named[0], named
