# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2079, AD-1152: a module that a project module holds flows on through an attribute read.

Consumer: `archkeel validate`. `app.util` holds `import cProfile as cp`. The consumer reads `cp` as
an attribute of `util` (a read, `getattr`, a literal key of `vars` or `__dict__`) and a later call
reaches the trojan horse. The first read of the value is the site (AD-1098). Each plant imports
`app.lib` under CPython 3.12 (the test asserts it), so `NO-LIB` must be UNKNOWN or FAIL. Each
control reads an attribute that holds no such module: CPython leaves `app.lib` unloaded, PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

RUN = "('import app.lib')"
UTIL = "import cProfile as cp\n\nvalue = 1\n"
IMPORT = "from app import util\n"
# name -> (consumer imports, consumer call, util source, mid source)
PLANTS = {
    "getattr with a literal name": (IMPORT, "getattr(util, 'cp').run" + RUN, UTIL, ""),
    "getattr bound to a name": (
        IMPORT,
        "m = getattr(util, 'cp')\n        m.run" + RUN,
        UTIL,
        "",
    ),
    "attribute read bound to a name": (IMPORT, "cp = util.cp\n        cp.run" + RUN, UTIL, ""),
    "value in a dict": (IMPORT, "d = {'m': util.cp}\n        d['m'].run" + RUN, UTIL, ""),
    "value in an attribute": (
        IMPORT + "import types\n\nh = types.SimpleNamespace()\n",
        "h.m = util.cp\n        h.m.run" + RUN,
        UTIL,
        "",
    ),
    "vars with a literal key": (IMPORT, "vars(util)['cp'].run" + RUN, UTIL, ""),
    "__dict__ with a literal key": (IMPORT, "util.__dict__['cp'].run" + RUN, UTIL, ""),
    "two-hop from import, read of the alias": (
        "from app.mid import q2\n",
        "q2.run" + RUN,
        UTIL,
        "from app.util import cp as q2\n",
    ),
    "two-hop from import, read through the middle module": (
        "from app import mid\n",
        "mid.q2.run" + RUN,
        UTIL,
        "from app.util import cp as q2\n",
    ),
}
CONTROLS = {
    "setattr of the name": (IMPORT, "setattr(util, 'cp', 1)", UTIL, ""),
    "delattr of the name": (IMPORT, "delattr(util, 'cp')", UTIL, ""),
    "store through vars": (IMPORT, "vars(util)['cp'] = 1", UTIL, ""),
    "getattr of a number": (IMPORT, "getattr(util, 'value')", UTIL, ""),
    "attribute read of a number": (IMPORT, "n = util.value", UTIL, ""),
    "dict of a number": (IMPORT, "d = {'m': util.value}\n        d['m']", UTIL, ""),
    "vars with a literal key of a number": (IMPORT, "vars(util)['value']", UTIL, ""),
    "dict key of a number": (IMPORT, "util.__dict__['value']", UTIL, ""),
    "two-hop from import of a number": (
        "from app.mid import q2\n",
        "q2",
        UTIL,
        "from app.util import value as q2\n",
    ),
}


def _run(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, plant: tuple):
    imports, call, util, mid = plant
    root = _root(tmp_path, quiet(imports, call))
    (root / "src/app/util.py").write_text(util)
    (root / "src/app/mid.py").write_text(mid)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_module_read_as_an_attribute_of_a_project_module_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, PLANTS[name])

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_an_attribute_of_a_project_module_that_holds_no_such_module_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, CONTROLS[name])

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
