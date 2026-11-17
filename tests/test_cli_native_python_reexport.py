# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-530: a re-export that nothing can rewrite, and a read that imports nothing.

Each plant (`python_reexport_plants.py`) is a tiny tree through the release core and the default
shell. The rule `FORBID` forbids `app.client` to import `app.service`; `client.py` never does, so
the row is PASS unless a gap holds the rule. Release 4.0.1 gives PASS for each plant. The core
gives PASS where its proof holds and UNKNOWN with a named gap where it does not. A core PASS is
always a PASS of 4.0.1 too, and CPython confirms the truth of each tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from python_reexport_plants import Plant
from python_setattr_plants import ALL as PLANTS
from test_cli_native_python_imports import RULE, project, rows, verdict

FORBID = [
    {
        **RULE,
        "id": "FORBID",
        "kind": "forbidden_dependency",
        "source": "app.client",
        "target": "app.service",
        "include_type_checking": True,
    }
]
# The plants whose row moves from UNKNOWN to PASS with AD-530. Each one is a PASS of 4.0.1 too.
MOVED = {
    "constant-of-the-package-is-no-escape",
    "tuple-of-the-package-is-no-escape",
    "name-of-an-external-origin-is-no-escape",
    "globals-read-with-a-literal-key",
    "globals-in-a-local-passed-to-a-lookup",
    "globals-passed-to-an-external-call",
    "parameter-named-like-a-door-module",
    "literal-getattr-of-a-module-attribute",
    "setattr-on-a-copied-local",
    "setattr-on-a-deepcopy-of-the-copy-module",
}
# The plants where the core is stricter than main was: a frame namespace is a door now.
STRICTER = {
    "frame-globals-write-at-import",
    # AD-762 (#1520): a runner of `code` on the name `code` is a gap whatever binds the name.
    "comprehension-variable-does-not-bind-outside",
}
# How CPython runs an inert read: the call, and the modules that it imports (none).
CALLS = {
    "globals-read-with-a-literal-key": "c.f(c.f)",
    "globals-in-a-local-passed-to-a-lookup": "c.f(c.f)",
    "globals-passed-to-an-external-call": "c.f(c.f)",
    "parameter-named-like-a-door-module": "c.f(1)",
}


def write(root: Path, plant: Plant) -> Path:
    return project(root, plant.files, contract_rules=FORBID)


def run_python(root: Path, code: str) -> str:
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def truth(root: Path, plant: Plant) -> str:
    """What `sub` is in `app.client`, for each import order of the two modules."""
    found = set()
    for order in (["app.client", "app.writer"], ["app.writer", "app.client"]):
        code = (
            "import importlib, sys\n"
            f"for name in {order!r}:\n"
            "    try:\n        importlib.import_module(name)\n"
            "    except ModuleNotFoundError:\n        pass\n"
            "client = sys.modules.get('app.client')\n"
            "sub = getattr(client, 'sub', None)\n"
            "kind = type(sub).__name__\n"
            "print('-' if sub is None else sub.__name__ if kind == 'module' else 'type:' + kind)\n"
        )
        found.add(run_python(root, code).strip().splitlines()[-1])
    return "|".join(sorted(found))


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    plant = PLANTS[name]
    result = verdict(release_core, write(tmp_path, plant))
    assert rows(result)["FORBID"] == plant.after, result["frame"].get("explained")
    gaps = [gap["reason"] for gap in result["frame"].get("collection_gaps", [])]
    assert bool(gaps) == (plant.after == "UNKNOWN"), gaps


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_is_never_weaker_than_the_release_and_cpython_agrees(
    tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    # A core PASS needs a release PASS; UNKNOWN is the stricter row.
    assert plant.after == plant.release or plant.after == "UNKNOWN", name
    root = write(tmp_path, plant)
    assert truth(root, plant) == plant.truth


def test_each_row_that_moves_toward_pass_is_listed_and_is_a_release_pass() -> None:
    moved = {n for n, p in PLANTS.items() if (p.before, p.after) == ("UNKNOWN", "PASS")}
    assert moved == MOVED
    assert all(PLANTS[name].release == "PASS" for name in moved)
    # No plant gets worse than before, and none moves from FAIL.
    assert all(p.after in {p.before, "PASS"} or n in STRICTER for n, p in PLANTS.items())


@pytest.mark.parametrize("name", sorted(CALLS))
def test_an_inert_read_of_the_globals_imports_no_module(tmp_path: Path, name: str) -> None:
    root = write(tmp_path, PLANTS[name])
    code = (
        "import sys\nimport app.client as c\nbefore = set(sys.modules)\n"
        f"{CALLS[name]}\nprint(sorted(set(sys.modules) - before))\n"
    )
    assert run_python(root, code).strip() == "[]"


def test_a_python_verdict_states_its_assumption(release_core: Path, tmp_path: Path) -> None:
    """The proofs rest on one premise, and the frame says it with the verdict (AD-530)."""
    for name in ("plain-submodule", "init-rebinds-after-the-import"):
        result = verdict(release_core, write(tmp_path / name, PLANTS[name]))
        premise = (
            "Code outside the scan roots, including test code, hands in no module object of the"
            " scan and writes no binding of a module or class of the scan."
        )
        assert result["frame"]["premise"] == premise
