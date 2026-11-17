# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python loaders outside the scan: a forbidden import that they make is never PASS (#1519, #1521).

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. A module outside the scan
roots (`vendor/plugin_vendor.py`) loads the module whose name it is given. Python 3.12 runs the
consumer with `vendor` on the path, and `app.lib` is then in `sys.modules`: the dependency is real.
The scan cannot read the loader, so the rule is UNKNOWN with a named gap, or FAIL.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import run
from python_interface_plants import Plant, build
from rust_repository import rule

from archkeel.cli import core_only

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

# name: (consumer, the files outside the scan)
PLANTS = {
    "#1519 a third-party string loader": (
        "from plugin_vendor import load\nload('app.lib')\n",
        {
            "vendor/plugin_vendor.py": "from importlib import import_module\n"
            "def load(name):\n    import_module(name)\n"
        },
    ),
    "#1521 a library globals dictionary hides the builtin importer": (
        "from plugin_vendor import namespace\nkey = ''.join(['__im', 'port__'])\n"
        "namespace()[key]('app.lib')\n",
        {
            "vendor/plugin_vendor.py": "from builtins import __import__\n"
            "def namespace():\n    return globals()\n"
        },
    ),
}


def _truth(root: Path) -> bool:
    code = (
        "import sys; sys.path[:0] = ['src', 'vendor']; import app.consumer; "
        "print('app.lib' in sys.modules)"
    )
    done = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip() == "True"


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_loader_outside_the_scan_cannot_hide_a_forbidden_import(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    consumer, files = PLANTS[name]
    root = tmp_path / "repo"
    root.mkdir()
    build(
        root,
        Plant(name, consumer, ("app.lib",), {"src/app/lib/__init__.py": "value = 1\n", **files}),
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule(
        "NO-IMPORT",
        "forbidden_dependency",
        source="app.consumer",
        target="app.lib",
        include_type_checking=True,
    )
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    path.write_text(json.dumps(contract))
    assert _truth(root), name
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    result = run("validate", "--root", str(root))[1]

    assert result["frame"]["rules"]["NO-IMPORT"][1] in {"FAIL", "UNKNOWN"}, result["frame"]
