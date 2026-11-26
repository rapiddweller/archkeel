# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2048, AD-1133: a name is judged by its value, not by the name of an attribute or a binding.

Consumer: `archkeel validate`. `types = pa.types` binds an attribute of a third-party module, not
the standard library module `types`, although another module of the scan imports `types`. The rule
`NO-LIB` stays PASS. Each plant hands a module with a trojan horse on through a module of the scan,
and CPython 3.12 imports `app.lib` (the test asserts it), so the rule must be UNKNOWN or FAIL.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

# name -> (consumer source, util source)
CONTROLS = {
    "attribute of a parameter, import elsewhere": (
        "def f(pa):\n    types = pa.types\n    return types.is_boolean(1)\n\n\n"
        "def g():\n    import pyarrow as pa\n\n    return pa\n",
        "import types\n",
    ),
    "attribute of an imported module": (
        "import pyarrow as pa\n\ntypes = pa.types\ntypes.is_boolean(1)\n",
        "import types\n",
    ),
    "name of an import in a function": (
        "def f(pa):\n    return pa.logging\n\n\ndef g():\n    import pyarrow as pa\n\n    pa.x\n",
        "import logging\n",
    ),
    "function local named types": (
        "def f(x):\n    types = x.kinds\n    return types.get(1)\n",
        "import types\n",
    ),
    "dict named profile": ("profile = {'name': 'Ada'}\nprofile.get('name')\n", "import profile\n"),
}
PLANTS = {
    "alias of the module": (
        quiet("import cProfile as types\n", "types.run('import app.lib')"),
        "",
    ),
    "relative import of the project module": (
        quiet("from . import util\n", "util.cProfile.run('import app.lib')"),
        "import cProfile\n",
    ),
    "attribute of a parameter, no import": (
        quiet("from app import util\n", "(lambda m: m.cProfile.run('import app.lib'))(util)"),
        "import cProfile\n",
    ),
    "attribute of the project module": (
        quiet("from app import util\n", "util.cProfile.run('import app.lib')"),
        "import cProfile\n",
    ),
}


def _run(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, plant: tuple):
    source, util = plant
    root = _root(tmp_path, source)
    (root / "src/app/util.py").write_text(util)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_name_bound_to_a_value_that_is_no_module_of_the_standard_library_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, CONTROLS[name])

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_name_bound_to_a_module_of_the_standard_library_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, PLANTS[name])

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
