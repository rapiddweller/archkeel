# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1973, AD-1089: a project module re-exports a standard library module that holds a trojan horse.

Consumer: `archkeel validate`. `app.util` imports the standard library module and `app.consumer`
reaches the trojan horse through `util`. Each plant imports `app.lib` under CPython 3.12 (the test
asserts it), so the rule `NO-LIB` must be UNKNOWN or FAIL, never PASS. Each control has the same
shape with a standard library module that holds no trojan horse name: CPython leaves `app.lib`
unloaded and the rule is PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import BUILD, CODE, quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")


def use(call: str) -> str:
    return quiet("from app import util\n\n", call)


PLANTS = {
    "cProfile.run": (use("util.cProfile.run('import app.lib')"), "import cProfile\n"),
    "trace.Trace": (use("util.trace.Trace().run('import app.lib')"), "import trace\n"),
    "profile.run": (use("util.profile.run('import app.lib')"), "import profile\n"),
    "mock.patch": (
        use("util.mock.patch('app.lib.value').start()"),
        "from unittest import mock\n",
    ),
    "unittest.mock.patch": (
        use("util.unittest.mock.patch('app.lib.value').start()"),
        "import unittest.mock\n",
    ),
    "unittest.main": (
        use("util.unittest.main(module='app.lib', exit=False, argv=['x'])"),
        "import unittest\n",
    ),
    "TestLoader": (
        use("util.unittest.TestLoader().loadTestsFromName('app.lib')"),
        "import unittest\n",
    ),
    "logging.config": (
        use(
            "util.logging.config.dictConfig({'version': 1, 'handlers': {'h': {'()': 'app.lib.X'}}})"
        ),
        "import logging.config\n",
    ),
    "dis": (
        "from app import util\n\n\n" + CODE + "code = util.dis.Bytecode(f).codeobj\n" + BUILD,
        "import dis\n",
    ),
    "import as": (use("util.cp.run('import app.lib')"), "import cProfile as cp\n"),
    "attribute of a call": (
        use("util.get().cProfile.run('import app.lib')"),
        "import cProfile\n\n\ndef get():\n    import sys\n    return sys.modules[__name__]\n",
    ),
}
CONTROLS = {
    "cProfile Stats": (
        "from app import util\n\nutil.cProfile.Stats\n",
        "import cProfile\n",
    ),
    "unittest TestCase": (
        "from app import util\n\nutil.unittest.TestCase\n",
        "import unittest\n",
    ),
    "os path": ("from app import util\n\nutil.os.path.join('a', 'b')\n", "import os\n"),
    "json dumps": ("from app import util\n\nutil.json.dumps({})\n", "import json\n"),
}


def _run(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, plant: tuple):
    source, util = plant
    root = _root(tmp_path, source)
    (root / "src/app/util.py").write_text(util)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_trojan_horse_reached_through_a_project_module_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, PLANTS[name])

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_standard_library_module_without_a_trojan_horse_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, CONTROLS[name])

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
