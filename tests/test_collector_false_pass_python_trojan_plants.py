# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1058: the plants of the two reviews and of the counter-example runs of #1968.

Consumer: a CI job that must never read PASS for a project that imports a forbidden module. Each
plant is a source for `app.consumer` (and extra files); Python 3.12 runs it. When it imports
`app.lib`, the rule `NO-LIB` must not be PASS. A plant that imports nothing is a control and
asserts nothing here (the controls of `test_collector_false_pass_python_trojan_attribute.py`
assert the PASS that must stay).
"""

from __future__ import annotations

import importlib
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

TRUTH = (
    "import sys; sys.path.insert(0, 'src'); import app.consumer; print('app.lib' in sys.modules)"
)
PLANTS = [
    (number, name, plant)
    for number in range(1, 7)
    for name, plant in importlib.import_module(f"python_trojan_plants_{number}").P.items()
]


@pytest.mark.parametrize(
    ("number", "name", "plant"), PLANTS, ids=[f"{n}-{name}" for n, name, _ in PLANTS]
)
def test_a_plant_that_imports_the_module_is_never_pass(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    number: int,
    name: str,
    plant: object,
) -> None:
    source, extra = plant if isinstance(plant, tuple) else (plant, {})
    root = tmp_path / "repo"
    build(
        root, Plant("trojan", source, ("app.lib",), {"src/app/lib/__init__.py": "x = 1\n", **extra})
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule("NO-LIB", "forbidden_dependency", source="app.consumer", target="app.lib")
    forbidden["include_type_checking"] = True
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    path.write_text(json.dumps(contract))
    done = subprocess.run(
        ["python3.12", "-W", "ignore", "-I", "-c", TRUTH], cwd=root, capture_output=True, text=True
    )
    imports = done.stdout.strip().splitlines()[-1:] == ["True"]
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    frame = run("validate", "--root", str(root))[1]["frame"]

    assert not (imports and frame["rules"]["NO-LIB"][1] == "PASS"), (name, frame)


DECLARED = list(importlib.import_module("python_trojan_declared_plants").cases.items())


@pytest.mark.parametrize(("name", "case"), DECLARED, ids=[name for name, _ in DECLARED])
def test_a_declared_import_that_the_secret_reaches_is_never_pass(
    tmp_path: Path, release_core: Path, name: str, case: tuple
) -> None:
    """A declaration on `import pickle` must not clear a rule while Python imports the secret."""
    from test_cli_python_trojan_horse_name import imports_secret, rows
    from test_cli_python_trojan_horse_name import run as run_declared

    files, declared = case
    result = run_declared(tmp_path / "repo", dict(files), declared, release_core)
    try:
        secret = imports_secret(tmp_path / "repo")
    except subprocess.CalledProcessError:
        secret = False  # the plant fails in Python: a bogus control

    assert not (secret and rows(result)["CLIENT-NO-SECRET"] == "PASS"), (name, result["frame"])
    if name[0] in "YZBW":
        # B8 of the third review: the escape of the module value refuses the declaration.
        assert "trojan_horse_reach.invalid" in {gap["kind"] for gap in result["gaps"]}, name
