# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2025: a loader candidate in a lazy table keeps the proven edges of the other candidates.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. The module-level
`__getattr__` of `app.consumer` imports a table entry by `import_module`. CPython 3.12 imports
`app.lib` when the attribute `a` is read. The entry `pdb.main` is a loader that can reach more
than the table names, so its call stays a site; the edge to `app.lib` is proven and the rule FAILs.
A table with loader candidates only has no proven edge and stays UNKNOWN.
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

HEAD = "from importlib import import_module\n\n"
BODY = (
    "\n\ndef __getattr__(name):\n    value = _T.get(name)\n    if value is None:\n"
    "        raise AttributeError(name)\n    package, module = value\n"
    "    return import_module(module, package=package)\n"
)


def _source(*modules: str) -> str:
    entries = ", ".join(f"'{'ab'[at]}': ('app', '{name}')" for at, name in enumerate(modules))
    return HEAD + "_T = {" + entries + "}" + BODY


PROVEN = _source("app.lib", "pdb.main")
LOADERS_ONLY = _source("pdb.main", "dis.Bytecode")
CLEAN = _source("app.lib", "json")


def _root(tmp: Path, source: str) -> Path:
    root = tmp / "repo"
    root.mkdir(parents=True)
    build(root, Plant("lazy", source, ("app.lib",), {"src/app/lib/__init__.py": "value = 1\n"}))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule("NO-LIB", "forbidden_dependency", source="app.consumer", target="app.lib")
    forbidden["include_type_checking"] = True
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    path.write_text(json.dumps(contract))
    return root


def _loads_lib(root: Path) -> bool:
    code = (
        "import sys; sys.path.insert(0, 'src'); import app.consumer as c; c.a; "
        "print('app.lib' in sys.modules)"
    )
    done = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True
    )
    return done.stdout.strip() == "True"


def _frame(root: Path, core: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    return run("validate", "--root", str(root))[1]["frame"]


def test_a_proven_edge_beside_a_loader_candidate_fails_and_names_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, PROVEN)
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _frame(root, release_core, monkeypatch)

    assert frame["rules"]["NO-LIB"][1] == "FAIL", frame["collection_gaps"]
    reasons = [gap["reason"] for gap in frame["collection_gaps"]]
    assert "dynamic_import: import_module" in reasons, reasons


def test_a_table_with_loader_candidates_only_stays_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame(_root(tmp_path, LOADERS_ONLY), release_core, monkeypatch)

    assert frame["rules"]["NO-LIB"][1] == "UNKNOWN", frame["collection_gaps"]


def test_a_table_without_a_loader_candidate_is_unchanged(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, CLEAN)
    assert _loads_lib(root)
    frame = _frame(root, release_core, monkeypatch)

    assert frame["rules"]["NO-LIB"][1] == "FAIL", frame["collection_gaps"]
    assert not frame["collection_gaps"]
