# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1520: a runner of the `code` module on a value that the scan cannot prove is never PASS.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. `f` takes a provider from
outside the scan and calls `provider.code.interact()` through a local `code`; the provider's object
imports `app.lib`. Python 3.12 runs `outside.py`, which hands the provider in, and `app.lib` is then
in `sys.modules`. The name `code` proves nothing about its value, so the rule is UNKNOWN or FAIL.
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

CONSUMER = "def f(provider):\n    code = provider.code\n    code.interact()\n"
FILES = {
    "src/app/lib/__init__.py": "value = 1\n",
    "vendor/plugin_vendor.py": "class Loader:\n"
    "    def interact(self):\n        from importlib import import_module\n"
    "        import_module('app.lib')\n"
    "class Provider:\n    code = Loader()\nprovider = Provider()\n",
    "outside.py": "from plugin_vendor import provider\nfrom app.consumer import f\nf(provider)\n",
}


def test_a_code_runner_on_an_unknown_value_cannot_hide_a_forbidden_import(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    build(root, Plant("unknown provider", CONSUMER, ("app.lib",), FILES))
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
    code = (
        "import sys, runpy; sys.path[:0] = ['src', 'vendor']; runpy.run_path('outside.py'); "
        "print('app.lib' in sys.modules)"
    )
    truth = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True
    )
    assert truth.stdout.strip() == "True", truth.stderr
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    result = run("validate", "--root", str(root))[1]

    assert result["frame"]["rules"]["NO-IMPORT"][1] in {"FAIL", "UNKNOWN"}, result["frame"]
