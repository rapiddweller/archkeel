# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1967: a computed attribute name on an unproved receiver is a trojan horse, never PASS.

A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.
Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. Each plant reads the
`__code__` of a function through `getattr`, `setattr` or `__getattribute__` with a name that the
scan cannot read, and Python 3.12 then imports `app.lib`. The rule must be UNKNOWN or FAIL. A
control with a project class, a literal name, a module receiver or a declared site clears.
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

EDIT = "tuple('app.lib' if n == 'json' else n for n in code.co_names)"
HEAD = "def f():\n    import json\n    return json\n\nname = {name}\n"
TAIL = "code = {read}\nsetattr(f, name, code.replace(co_names=" + EDIT + "))\nf()\n"
PLANTS = {
    "joined-getattr": ("'__co' + 'de__'", "getattr(f, name)"),
    "getattribute": ("''.join(['__c', 'ode__'])", "f.__getattribute__(name)"),
    "variable-name": ("''.join(['__c', 'ode__'])", "getattr(f, name)"),
    "reversed-name": ("'__edoc__'[::-1]", "getattr(f, name)"),
    "dir-filter": ("[n for n in dir(f) if n.startswith('__co')][0]", "getattr(f, name)"),
}
CONTROLS = {
    "literal-name": "def f():\n    return 1\n\nNAME = getattr(f, '__name__')\n",
    "local-literal": "def f():\n    n = '__name__'\n    return getattr(f, n)\n",
    "project-class": (
        "class C:\n    x = 1\n    def get(self, n):\n        return getattr(self, n)\n"
        "    @classmethod\n    def make(cls, n):\n        return getattr(cls, n)\n"
        "def read(n):\n    return getattr(C, n)\n"
    ),
    "module-receiver": "import json\n\ndef read(n):\n    return getattr(json, n)\n",
}
SITES = {"builtins": "import builtins\n\ndef read(n):\n    return getattr(builtins, n)\n"}


def _root(tmp: Path, source: str, version: str = "2.2.0", declared: list | None = None) -> Path:
    root = tmp / "repo"
    root.mkdir(parents=True)
    build(root, Plant("trojan", source, ("app.lib",), {"src/app/lib/__init__.py": "value = 1\n"}))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule("NO-LIB", "forbidden_dependency", source="app.consumer", target="app.lib")
    forbidden["include_type_checking"] = True
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    if declared is not None:
        contract["schema_version"] = version
        contract["declarations"] = {"trojan_horse_reach": declared}
    path.write_text(json.dumps(contract))
    return root


def _loads_lib(root: Path) -> bool:
    code = (
        "import sys; sys.path.insert(0, 'src'); import app.consumer; "
        "print('app.lib' in sys.modules)"
    )
    done = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True
    )
    return done.stdout.strip() == "True"


def _verdict(root: Path, core: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_computed_name_that_reaches_a_code_object_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    value, read = PLANTS[name]
    root = _root(tmp_path, HEAD.format(name=value) + TAIL.format(read=read))
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_receiver_or_name_that_the_scan_proves_clears(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


def test_a_declared_trojan_horse_site_passes_under_its_declaration(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "def read(n):\n    return getattr(read, n)\n"
    root = _root(tmp_path / "a", source)
    assert not _loads_lib(root)
    frame = _verdict(root, release_core, monkeypatch)["frame"]
    assert frame["rules"]["NO-LIB"][1] == "UNKNOWN", frame

    declared = [
        {
            "id": "T-1",
            "module": "app.consumer",
            "name": "getattr",
            "line": 2,
            "loads": [],
            "changes": [],
            "rationale": "The name comes from a fixed table of the product.",
            "provenance": ["docs/target.md"],
        }
    ]
    root = _root(tmp_path / "b", source, "3.20.0", declared)
    frame = _verdict(root, release_core, monkeypatch)["frame"]
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
    assert frame["trojan_horse_reach"][0]["id"] == "T-1", frame
