# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2016, #2024, AD-1098: a standard library module with trojan horse names flows as a value.

Consumer: `archkeel validate`. A module value moves through a function return, an argument, an
assignment or a from-import alias, and a later read of an attribute reaches the trojan horse.
Each plant imports `app.lib` under CPython 3.12 (the test asserts it), so the rule `NO-LIB` must
be UNKNOWN or FAIL, never PASS. Each control moves a module without a trojan horse the same way:
CPython leaves `app.lib` unloaded and the rule is PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import BUILD, CODE, quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

RUN = "('import app.lib')"
DIS = "\n\n" + CODE + "code = alias.__dict__['Bytecode'](f).codeobj\n" + BUILD


def use(imports: str, call: str) -> str:
    return quiet(imports, call)


# name -> (consumer source, util source)
PLANTS = {
    "return of the module": (
        use("from app import util\n", "util.f().run" + RUN),
        "import cProfile\n\n\ndef f():\n    return cProfile\n",
    ),
    "late assignment": (
        use(
            "import cProfile\nfrom app import util\n", "util.c = cProfile\n        util.c.run" + RUN
        ),
        "",
    ),
    "from import of an alias": (
        use("from app.util import cp as x\n", "x.run" + RUN),
        "import cProfile as cp\n",
    ),
    "from import of the name": (
        use("from app.util import cProfile\n", "cProfile.run" + RUN),
        "import cProfile\n",
    ),
    "identity function": (
        "import dis\n\n\ndef same(m):\n    return m\n\n\nalias = same(dis)\n" + DIS,
        "",
    ),
    "assignment in the module": (
        use("from app import util\n", "util.c.run" + RUN),
        "import cProfile\n\nc = cProfile\n",
    ),
    "return of the module by a lambda": (
        use("import cProfile\n", "(lambda m: m)(cProfile).run" + RUN),
        "",
    ),
    "list of modules": (
        use("import cProfile\n", "[cProfile][0].run" + RUN),
        "",
    ),
}
CONTROLS = {
    "return of json": (
        use("from app import util\n", "util.f().dumps({})"),
        "import json\n\n\ndef f():\n    return json\n",
    ),
    "from import of os alias": (
        use("from app.util import p as x\n", "x.join('a', 'b')"),
        "import os.path as p\n",
    ),
    "identity function on os": (
        "import os\n\n\ndef same(m):\n    return m\n\n\nsame(os).getcwd()\n",
        "",
    ),
    "object named like an alias of another module": (
        "task = type('Runner', (), {'run': lambda self: 1})()\ntask.run()\n",
        "import cProfile as task\n",
    ),
    "ordinary data named like a module": (
        "profile = {'name': 'Ada'}\nname = profile['name']\n",
        "",
    ),
    "assignment of json": (
        "import json\n\nalias = json\nalias.dumps({})\n",
        "",
    ),
}


def _run(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, plant: tuple):
    source, util = plant
    root = _root(tmp_path, source)
    (root / "src/app/util.py").write_text(util)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_module_that_flows_as_a_value_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, PLANTS[name])

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_module_without_a_trojan_horse_that_flows_as_a_value_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, CONTROLS[name])

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
