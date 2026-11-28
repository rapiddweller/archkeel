# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2240: a test source outside the scan roots does not switch off a product proof.

`BOX = Box()` is an instance of a class with no base: the name is no module, so `print(BOX)` hands
no module on. A write to the class by code that can run in the product withholds that proof. A
write by test source (a `conftest.py`, a file under `testpaths`, a file under `tests/`) is no
product runtime.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, RULE, project, verdict

PATCH = "import app.service\n\nsetattr(app.service.Box, 'extra', 1)\n"
FILES = {
    **BASE,
    "src/app/client.py": "from app.service import BOX\n\nprint(BOX)\n",
    "src/app/service.py": "class Box:\n    pass\n\n\nBOX = Box()\n",
}


def tree(root: Path, extra: dict[str, str], pyproject: str = "") -> Path:
    rules: list[dict[str, Any]] = [{**RULE, "id": "INTERFACE", "kind": "interface_boundary"}]
    project(root, {**FILES, **extra}, contract_rules=rules)
    pyproject_path = root / "pyproject.toml"
    pyproject_path.write_text(pyproject_path.read_text() + pyproject)
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


TESTPATHS = '[tool.pytest.ini_options]\ntestpaths = ["checks"]\n'


def test_without_a_writer_the_instance_is_proven(release_core: Path, tmp_path: Path) -> None:
    assert interface(release_core, tree(tmp_path, {})) == "PASS"


@pytest.mark.parametrize(
    ("extra", "pyproject"),
    [
        ({"conftest.py": PATCH}, ""),
        ({"deep/dir/conftest.py": PATCH}, ""),
        ({"checks/helper.py": PATCH}, TESTPATHS),
        ({"tests/helper.py": PATCH}, ""),
    ],
    ids=["conftest", "nested-conftest", "testpaths", "tests-dir"],
)
def test_a_test_source_writer_keeps_the_proof(
    release_core: Path, tmp_path: Path, extra: dict[str, str], pyproject: str
) -> None:
    assert interface(release_core, tree(tmp_path, extra, pyproject)) == "PASS"


@pytest.mark.parametrize(
    ("extra", "pyproject"),
    [
        ({"scripts/patch.py": PATCH}, ""),
        ({"checks/helper.py": PATCH}, ""),
        ({"checks/helper.py": PATCH}, '[tool.pytest.ini_options]\ntestpaths = ["other"]\n'),
        ({"checks/helper.py": PATCH}, '[tool.pytest.ini_options]\ntestpaths = ["ch*"]\n'),
        ({"checks/helper.py": PATCH}, '[tool.pytest.ini_options]\ntestpaths = ["../checks"]\n'),
        ({"checksum/helper.py": PATCH}, TESTPATHS),
        (
            {
                "src/app/conftest.py": PATCH,
                "src/app/client.py": (
                    "import app.conftest\nfrom app.service import BOX\n\nprint(BOX)\n"
                ),
            },
            "",
        ),
    ],
    ids=[
        "script",
        "no-testpaths",
        "other-testpaths",
        "glob-testpath",
        "parent-testpath",
        "prefix-of-testpath",
        "product-conftest",
    ],
)
def test_a_product_writer_still_withholds_the_proof(
    release_core: Path, tmp_path: Path, extra: dict[str, str], pyproject: str
) -> None:
    assert interface(release_core, tree(tmp_path, extra, pyproject)) == "UNKNOWN"
