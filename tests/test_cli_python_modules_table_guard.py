# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2240: only the real `sys.modules` is the import table of the typing and class proofs.

A local dict or an attribute that is named `modules` is no import table. A write to the real
table, also through an alias, a parameter, a replaced table or a call, withholds the proof that
`BOX = Box()` is no module. Each withholding plant also runs under CPython and writes the real
table.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, RULE, project, verdict

KEY = "archkeel_probe_2240"
SERVICE = "class Box:\n    pass\n\n\nBOX = Box()\n"
FILES = {**BASE, "src/app/client.py": "from app.service import BOX\n\nprint(BOX)\n"}

HARMLESS = {
    "local-dict": (
        "def tally(items, modules=None):\n    modules = {}\n    for item in items:\n"
        "        modules[item] = 1\n    del modules[items[0]]\n    return modules\n"
    ),
    "attribute": (
        "class Registry:\n    def __init__(self):\n        self.modules = {}\n\n"
        "    def put(self, key):\n        self.modules[key] = 1\n"
    ),
}
WRITES = {
    "alias": "import sys\nmodules = sys.modules\nmodules[KEY] = 'planted'\n",
    "from-import": "from sys import modules\nmodules[KEY] = 'planted'\n",
    "from-import-alias": "from sys import modules as table\ntable[KEY] = 'planted'\n",
    "module-alias": "import sys as s\ns.modules[KEY] = 'planted'\n",
    "parameter": (
        "import sys\n\n\ndef put(modules):\n    modules[KEY] = 'planted'\n\n\nput(sys.modules)\n"
    ),
    "replaced-table": ("import sys\nsys.modules = {**sys.modules}\nsys.modules[KEY] = 'planted'\n"),
    "getattr": "import sys\ngetattr(sys, 'modules')[KEY] = 'planted'\n",
    "module-copy": "import sys\nthere = sys\nthere.modules[KEY] = 'planted'\n",
    "call-receiver": (
        "import importlib\nimportlib.import_module('sys').modules[KEY] = 'planted'\n"
    ),
}


def tree(root: Path, extra: str) -> Path:
    rules: list[dict[str, Any]] = [{**RULE, "id": "INTERFACE", "kind": "interface_boundary"}]
    project(root, {**FILES, "src/app/service.py": SERVICE + extra}, contract_rules=rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    for component in contract["components"]:
        if component["label"] == "service":
            component["public"] = ["app.service:BOX", "app.service:Box"]
    path.write_text(json.dumps(contract))
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["add", "-A"], [*who, "commit", "-qm", "public"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return root


def interface(binary: Path, root: Path) -> str:
    return verdict(binary, root)["frame"]["rules"]["INTERFACE"][1]


@pytest.mark.parametrize("name", sorted(HARMLESS))
def test_a_name_that_is_no_import_table_keeps_the_proof(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    assert interface(release_core, tree(tmp_path, "\n\n" + HARMLESS[name])) == "PASS"


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_write_to_the_real_table_withholds_the_proof(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    assert (
        interface(release_core, tree(tmp_path, f"\n\nKEY = {KEY!r}\n" + WRITES[name])) == "UNKNOWN"
    )


@pytest.mark.parametrize("name", sorted(WRITES))
def test_the_withholding_plant_writes_the_real_table_under_cpython(name: str) -> None:
    source = f"KEY = {KEY!r}\n{WRITES[name]}\nimport sys\nprint(sys.modules.get(KEY))\n"
    done = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "planted"
