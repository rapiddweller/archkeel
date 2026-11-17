# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1506: a local name with the spelling of a module binding is not the module (AD-708).

Consumer: `archkeel validate` with the native Python collector and `interface_boundary`. `app.lib`
is public and binds the private name `_x = 5`; `Obj._x` is 123. Python 3.12 runs each consumer and
prints what it reads. A name that a parameter, an assignment, a comprehension or a lambda binds in
its own scope is another value: no use of `app.lib._x`, so no FAIL. Where the name is the module
(a `global`, a closure, an import in the function), the use is FAIL; where it may be the module
(a module object passed as an argument, an import and a value in one scope), the rule is UNKNOWN,
never PASS.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from python_interface_plants import LIB, Plant, build
from test_cli_native_python_imports import rows, verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

HEAD = "import app.lib as lib\n\n\nclass Obj:\n    _x = 123\n\n\n"
# name: (consumer body, what Python prints, the verdicts of BOUNDARY)
PLANTS = {
    "a parameter shadows the binding": (
        "def use(lib):\n    return lib._x\n\n\nprint(use(Obj()))\n",
        "123",
        {"PASS"},
    ),
    "a local assignment shadows the binding": (
        "def use():\n    lib = Obj()\n    return lib._x\n\n\nprint(use())\n",
        "123",
        {"PASS"},
    ),
    "a comprehension target shadows the binding": (
        "print([lib._x for lib in [Obj()]][0])\n",
        "123",
        {"PASS"},
    ),
    "a lambda parameter shadows the binding": (
        "print((lambda lib: lib._x)(Obj()))\n",
        "123",
        {"PASS"},
    ),
    "a class body binds the name": (
        "class K:\n    lib = Obj()\n    y = lib._x\n\n\nprint(K.y)\n",
        "123",
        {"PASS", "UNKNOWN"},
    ),
    "the module object is an argument": (
        "def use(m):\n    return m._x\n\n\nprint(use(lib))\n",
        "5",
        {"UNKNOWN", "FAIL"},
    ),
    "a global declaration names the binding": (
        "def use():\n    global lib\n    return lib._x\n\n\nprint(use())\n",
        "5",
        {"FAIL"},
    ),
    "a closure reads the binding": (
        "def use():\n    def inner():\n        return lib._x\n\n    return inner()\n\n\n"
        "print(use())\n",
        "5",
        {"FAIL"},
    ),
    "an import in the function binds the name": (
        "def use():\n    import app.lib as lib\n\n    return lib._x\n\n\nprint(use())\n",
        "5",
        {"FAIL"},
    ),
    "an import and a value bind the name in one scope": (
        "def use(flag):\n    if flag:\n        import app.lib as lib\n"
        "    else:\n        lib = Obj()\n"
        "    return lib._x\n\n\nprint(use(True))\n",
        "5",
        {"UNKNOWN", "FAIL"},
    ),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_local_name_is_the_module_only_where_its_scope_binds_the_module(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    body, printed, expected = PLANTS[name]
    plant = Plant(name, HEAD + body, ("app.lib",), {LIB: "_x = 5\n"})
    root = build(tmp_path / "p", plant)
    truth = subprocess.run(
        ["python3.12", "-I", "-c", "import sys; sys.path.insert(0, 'src'); import app.consumer"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert truth.stdout.strip() == printed, truth.stderr
    result = verdict(release_core, root)

    assert rows(result)["BOUNDARY"] in expected, (name, result["frame"]["explained"])
