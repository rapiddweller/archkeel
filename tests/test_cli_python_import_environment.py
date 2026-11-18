# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Import environment values keep their gaps when their runtime behavior is not proven."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from python_syspath_plants import Plant
from test_cli_native_python_imports import RULE, component, project, rows, verdict
from test_cli_python_syspath import tree


@pytest.mark.parametrize("comparison", ["Mutator() == sys.path", "sys.path == Mutator()"])
def test_comparison_can_mutate_path(release_core: Path, tmp_path: Path, comparison: str) -> None:
    source = (
        "import sys\n"
        "class Mutator:\n"
        " def __eq__(self, path):\n"
        "  path.append('/injected')\n"
        "  return False\n"
        f"{comparison}\n"
        "assert sys.path[-1] == '/injected'\n"
    )
    subprocess.run([sys.executable, "-c", source], check=True, capture_output=True)
    result = verdict(release_core, tree(tmp_path, Plant("comparison", source)))
    assert "import_system_change" in json.dumps(result)
    assert result["status"] == "UNKNOWN"


def test_literal_membership_comparison_remains_unknown(release_core: Path, tmp_path: Path) -> None:
    source = "import sys\nx = 'a' in sys.path\n"
    result = verdict(release_core, tree(tmp_path, Plant("literal", source)))
    assert "import_system_change" in json.dumps(result)
    assert result["status"] == "UNKNOWN"


def test_issue_1847_plain_reads_pass_validation(release_core: Path, tmp_path: Path) -> None:
    root = project(
        tmp_path,
        {
            "app/beta/models.py": 'class Plan:\n    code = "x"\n    name = "n"\n',
            "app/alpha/a.py": (
                "import sys\n\n"
                "from app.beta.models import Plan\n\n\n"
                "def inspect(x):\n"
                "    return x\n\n\n"
                "def use(plan: Plan) -> list[str]:\n"
                "    inspect(1)\n"
                "    a = Plan.code\n"
                "    b = Plan.name\n"
                "    paths = [p for p in sys.path if p]\n"
                "    return [a, b, *paths]\n"
            ),
            "p": "# Target\n\n<!-- archkeel-component-graph -->\n"
            "```mermaid\nflowchart LR\n    alpha --> beta\n```\n",
        },
        roots='["app"]',
        contract_rules=[
            {**RULE, "id": "ASSIGNMENT-COMPLETE", "kind": "complete_assignment", "source": "app"},
            {**RULE, "id": "COMPONENT-NO-CYCLES", "kind": "no_component_cycles"},
            {**RULE, "id": "REQUIRES", "kind": "complete_requires"},
        ],
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.14"\n')
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["components"] = [
        component("alpha", ["app.alpha"], ["beta"]),
        component("beta", ["app.beta"]),
    ]
    path.write_text(json.dumps(contract))
    result = verdict(release_core, root)
    assert result["frame"]["collection_gaps"] == []
    assert rows(result) == dict.fromkeys(
        ["ASSIGNMENT-COMPLETE", "COMPONENT-NO-CYCLES", "REQUIRES"], "PASS"
    )
    assert (result["status"], result["exit_code"]) == ("PASS", 0)


@pytest.mark.parametrize(
    ("client", "called"),
    [
        ("from app.service import Plan\nPlan.code.interact()\n", True),
        ("from app.service import Plan as P\nP.code.interact()\n", True),
        ("from app.service import Described\nDescribed.code.interact()\n", True),
        ("from app.service import Plan\nvalue = Plan.code\n", False),
    ],
)
def test_class_code_dispatch_keeps_gap(
    release_core: Path, tmp_path: Path, client: str, called: bool
) -> None:
    models = (
        "import code as module\n"
        "value = None\n"
        "class Descriptor:\n"
        " def __get__(self, obj, owner): return value\n"
        "class Plan:\n code = None\n"
        "class Described:\n code = Descriptor()\n"
        "Plan.code = module\nvalue = module\n"
    )
    root = project(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/service.py": models,
            "src/app/client.py": client,
            "p": "# Target\n\n<!-- archkeel-component-graph -->\n"
            "```mermaid\nflowchart LR\n    client --> service\n```\n",
        },
        contract_rules=[{**RULE, "id": "CYCLES", "kind": "no_component_cycles"}],
    )
    witness = (
        "import code\ncalls = []\n"
        "code.interact = lambda: calls.append('called')\n"
        f"import app.client\nassert calls == {['called'] if called else []!r}\n"
    )
    subprocess.run(
        [sys.executable, "-c", witness],
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        check=True,
        capture_output=True,
    )
    result = verdict(release_core, root)
    assert any(
        gap["reason"] == "dynamic_import: code" and gap["subjects"] == ["app.client"]
        for gap in result["frame"]["collection_gaps"]
    )
    assert result["status"] == "UNKNOWN"
    assert rows(result)["CYCLES"] == "UNKNOWN"
