# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-564: a Python gap holds only the rules that read its effect, through the release core.

Consumer: a CI job that reads the row of each rule. A gap that states its effect leaves the rules
on the files decided. Each plant with a `truth` hides a real violation of `CLIENT-NO-SECRET` behind
its gap: Python runs the truth, and the row of the rule must not be PASS.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from test_cli_native_python_imports import RULE, project, rows, verdict

# The cited page: the component graph that each plant has (AD-466).
GRAPH = (
    "# Target\n\n<!-- archkeel-component-graph -->\n"
    "```mermaid\ngraph TD\n    client --> service\n```\n"
)
FILES = {
    "p": GRAPH,
    "src/app/__init__.py": "",
    "src/app/client/__init__.py": "",
    "src/app/client/page.py": "import app.service.model as model\n",
    "src/app/service/__init__.py": "",
    "src/app/service/model.py": "VALUE = 1\n",
    "src/app/service/secret.py": "KEY = 2\n",
}
RULES = [
    {
        **RULE,
        "id": "CLIENT-NO-SECRET",
        "kind": "forbidden_dependency",
        "source": "app.client",
        "target": "app.service.secret",
        "include_type_checking": True,
    },
    {
        **RULE,
        "id": "SERVICE-NO-CLIENT",
        "kind": "forbidden_dependency",
        "source": "app.service",
        "target": "app.client",
        "include_type_checking": True,
    },
    {**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"},
    {
        **RULE,
        "id": "LAYOUT",
        "kind": "root_layout",
        "root": "app",
        "allowed_children": ["app.client", "app.service"],
    },
    {**RULE, "id": "CYCLES", "kind": "no_component_cycles"},
    {**RULE, "id": "EXTERNAL", "kind": "complete_external_scope", "source": "app"},
    {**RULE, "id": "REQUIRES", "kind": "complete_requires"},
]
# The rules on the files and their names: no stated effect reaches them.
ON_FILES = ("ASSIGN", "LAYOUT")
# The text that the trojan horse of a plant runs: it gives the name `app.service.model` another
# module.
SWAP = "import sys, app.service.secret as s; sys.modules['app.service.model'] = s"
# True when the module that `app.client.page` binds is the secret module.
BINDS_SECRET = "import app.client.page as p; print(p.model.__name__ == 'app.service.secret')"


class Plant(NamedTuple):
    files: dict[str, str]
    # The rules that are not UNKNOWN, with their status. Each other rule is UNKNOWN.
    decided: dict[str, str]
    # Python code that prints `True` when the hidden violation is real, and the text of the trojan
    # horse.
    truth: str = ""
    trojan_horse: str = ""


def files_pass(**more: str) -> dict[str, str]:
    return {**dict.fromkeys(ON_FILES, "PASS"), **more}


def test_a_shadowed_loader_write_keeps_the_forbidden_literal_edge(
    release_core: Path, tmp_path: Path
) -> None:
    path = "src/app/client/page.py"
    files = {
        **FILES,
        path: "import importlib\nimportlib.import_module('app.service.secret')\n",
        "src/app/service/patch.py": (
            "import importlib as loader\n"
            "def replace(loader, other):\n"
            "    loader.import_module = other\n"
        ),
    }
    result = verdict(release_core, project(tmp_path, files, contract_rules=RULES))
    rule = "CLIENT-NO-SECRET"
    assert rows(result)[rule] == "FAIL", result
    frame = result["frame"]
    sites = [frame["locations"][e] for d in frame["details"][rule] for e in d["evidence"]]
    assert {"path": path, "line": 2} in sites, frame


PLANTS = {
    "clean": Plant({}, dict.fromkeys([rule["id"] for rule in RULES], "PASS")),
    # A star import imports each submodule that `__all__` names. The code of the client module is
    # unknown; the edges of each service module are known.
    "star": Plant(
        {
            "src/app/service/__init__.py": '__all__ = ["secret"]\n',
            "src/app/client/page.py": "from app.service import *\n",
        },
        files_pass(**{"SERVICE-NO-CLIENT": "PASS"}),
        truth="import sys, app.client.page; print('app.service.secret' in sys.modules)",
    ),
    # Text that the scan cannot see runs in a service module, and a client rule is the victim.
    "exec": Plant(
        {"src/app/service/model.py": "import os\nexec(os.environ.get('DOOR', ''))\n"},
        files_pass(),
        truth=BINDS_SECRET,
        trojan_horse=SWAP,
    ),
    # A loader call with an unknown name can return `sys`. No later site names the write, so the
    # edges of the source module alone are not the effect of the call.
    "loader": Plant(
        {
            "src/app/service/model.py": (
                "import importlib\nimport os\n"
                "found = importlib.import_module(os.environ.get('DOOR', 'os'))\n"
                "found.modules[__name__] = importlib.import_module('app.service.secret')\n"
            )
        },
        files_pass(),
        truth=BINDS_SECRET,
        trojan_horse="sys",
    ),
    # A name that is an attribute and a submodule: the code of the one service module is unknown.
    "ambiguity": Plant(
        {
            "src/app/service/__init__.py": "secret = 1\n",
            "src/app/service/other.py": "from app.service import secret\n",
        },
        files_pass(**{"CLIENT-NO-SECRET": "PASS"}),
    ),
    # A violation that the scan sees stays FAIL beside a gap.
    "seen": Plant(
        {
            "src/app/client/page.py": "import app.service.secret\n",
            "src/app/service/model.py": "import os\nexec(os.environ.get('DOOR', ''))\n",
        },
        files_pass(**{"CLIENT-NO-SECRET": "FAIL"}),
    ),
    # An import of a project module that the scan does not find can load a file that the scan
    # does not see: the code of every module is unknown, the files are known.
    "not found": Plant({"src/app/service/model.py": "import app.service.missing\n"}, files_pass()),
    # The twin: a gap that states no effect (a module that Python imports and the scan cannot
    # read) holds each rule, also the rules on the files.
    "no effect": Plant({"src/app/service/window.pyw": "import app.client\n"}, {}),
}


def scanned(binary: Path, root: Path, plant: Plant) -> dict[str, Any]:
    return verdict(binary, project(root, {**FILES, **plant.files}, contract_rules=RULES))


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_gap_holds_the_rules_that_read_its_effect_and_no_other_rule(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    result = scanned(release_core, tmp_path, plant)
    expected = {rule["id"]: plant.decided.get(rule["id"], "UNKNOWN") for rule in RULES}
    assert rows(result) == expected, result
    # AD-1440: `test_cli_string_import.py` decides the built-in rule; its row joins it.
    statuses = {*expected.values(), result["frame"]["rules"]["STRING-IMPORT"][1]}
    status = "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    assert result["status"] == status, result
    if plant.truth:
        done = subprocess.run(
            [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, 'src'); {plant.truth}"],
            cwd=tmp_path,
            env={**os.environ, "DOOR": plant.trojan_horse},
            capture_output=True,
            text=True,
            check=True,
        )
        # The violation is real, so a PASS of the rule would be a false PASS.
        assert done.stdout.strip() == "True", done
        assert expected["CLIENT-NO-SECRET"] == "UNKNOWN"


def test_the_report_names_for_each_held_rule_the_gaps_that_hold_it(
    release_core: Path, tmp_path: Path
) -> None:
    frame = scanned(release_core, tmp_path, PLANTS["star"])["frame"]
    holds = frame["explain"]["holds"]
    held = {"CLIENT-NO-SECRET", "CYCLES", "EXTERNAL", "REQUIRES", "STRING-IMPORT"}
    assert set(holds["rules"]) == held
    for rule in sorted(held):
        entry = holds["rules"][rule]
        assert (entry["kind"], entry["total"]) == ("scoped_gaps", 1), entry
        assert "the code of app.client.page" in frame["explained"][rule]
    (gap,) = holds["gaps"]
    assert sorted(gap["rules"]) == sorted(held)
    assert gap["id"] == holds["rules"]["CLIENT-NO-SECRET"]["gaps"][0]
    # A PASS beside the gap is a PASS beyond the reference engine, and the frame says so.
    assert set(frame["beyond"]) == {"SERVICE-NO-CLIENT", *ON_FILES}
