# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1976, AD-1096: more routes to a standard library trojan horse. CPython 3.12 imports `app.lib`.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. Each plant imports
`app.lib` (the test asserts it), so the rule `NO-LIB` must be UNKNOWN or FAIL, never PASS. Each
control has the same shape with a module that holds no trojan horse name: the rule stays PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import BUILD, CODE, guarded, quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

ARGV = "import sys\n\nsys.argv = ['x', '-m', 'app.lib']\n"
PLANTS = {
    "import_module unittest": guarded(
        "import importlib\n",
        "importlib.import_module('unittest').TestLoader().loadTestsFromName('app.lib')",
    ),
    "__import__ unittest": guarded(
        "", "__import__('unittest').defaultTestLoader.loadTestsFromName('app.lib')"
    ),
    "__import__ cProfile": quiet("", "__import__('cProfile').run('import app.lib')"),
    "import_module pdb": quiet(
        "from importlib import import_module\n",
        "import_module('pdb').Pdb(stdin=io.StringIO('c\\n'), stdout=io.StringIO())"
        ".run('import app.lib')",
    ),
    "import_module xml.sax": guarded(
        "from importlib import import_module\n",
        "import_module('xml.sax').make_parser(['app.lib'])",
    ),
    "import_module warnings": guarded(
        "from importlib import import_module\n",
        "import_module('warnings')._setoption('ignore::app.lib.X')",
    ),
    "import_module dis": "from importlib import import_module\n\n\n"
    + CODE
    + "code = import_module('dis').Bytecode(f).codeobj\n"
    + BUILD,
    "__import__ dis": "\n\n" + CODE + "code = __import__('dis')._get_code_object(f)\n" + BUILD,
    "dis __dict__": "import dis\n\n\n"
    + CODE
    + "code = dis.__dict__['Bytecode'](f).codeobj\n"
    + BUILD,
    "vars of dis": "import dis\n\n\n" + CODE + "code = vars(dis)['Bytecode'](f).codeobj\n" + BUILD,
    "vars of dis alias": "import dis as d\n\n\n"
    + CODE
    + "code = vars(d)['Bytecode'](f).codeobj\n"
    + BUILD,
    "cProfile main": quiet("import cProfile\n" + ARGV, "cProfile.main()"),
    "profile main": quiet("import profile\n" + ARGV, "profile.main()"),
    "pdb main": quiet("import pdb\n" + ARGV, "pdb.main()"),
    "pdb set_trace": quiet(
        "import io\nimport pdb\nimport sys\n\nsys.stdin = io.StringIO('import app.lib\\nc\\n')\n",
        "pdb.set_trace()",
    ),
}
CONTROLS = {
    "import_module json": guarded(
        "import importlib\n", "importlib.import_module('json').dumps({})"
    ),
    "__import__ os": guarded("", "__import__('os').getcwd()"),
    "vars of json": "import json\n\nvalue = vars(json)['dumps']\n",
    "dict of a project value": "class K:\n    run = 1\n\n\nvalue = K.__dict__['run']\n",
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_module_value_or_entry_point_of_a_trojan_horse_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_the_same_shape_on_a_module_without_a_trojan_horse_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
