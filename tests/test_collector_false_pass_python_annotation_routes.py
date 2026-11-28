# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2039, AD-1134: three more routes to an evaluated string annotation.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. `app/lib` appends a line
to a counter file when CPython loads it. Each plant makes CPython 3.12 load it (the counter is 1),
so the rule `NO-LIB` must be UNKNOWN or FAIL, never PASS. Each control makes CPython leave the
counter at 0 and the rule is PASS.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

IMPORT = "__import__('app.lib')"
NESTED = "[" * 150 + IMPORT + "]" * 150
HINTS = "try:\n    typing.get_type_hints({name})\nexcept Exception:\n    pass\n"
HEAD = "import typing\n\n\n"
PLANTS = {
    "nesting over the parser bound": HEAD
    + f'class K:\n    x: "{NESTED}"\n\n\n'
    + HINTS.format(name="K"),
    "class annotations replaced": HEAD
    + "class K:\n    pass\n\n\n"
    + f'K.__annotations__ = {{"x": "{IMPORT}"}}\n'
    + HINTS.format(name="K"),
    "function annotation item set": HEAD
    + "def f(x):\n    pass\n\n\n"
    + f'f.__annotations__["x"] = "{IMPORT}"\n'
    + HINTS.format(name="f"),
    "annotations updated": HEAD
    + "class K:\n    pass\n\n\n"
    + f'K.__annotations__.update(x="{IMPORT}")\n'
    + HINTS.format(name="K"),
    "setattr of annotations (#2062 must keep it)": HEAD
    + "class K:\n    pass\n\n\n"
    + f'setattr(K, "__annotations__", {{"x": "{IMPORT}"}})\n'
    + HINTS.format(name="K"),
    "string in a variable": HEAD
    + f's = "{IMPORT}"\n\n\nclass K:\n    x: s\n\n\n'
    + HINTS.format(name="K"),
    "string built in a variable": HEAD
    + "s = '__import__(' + \"'app.lib')\"\n\n\nclass K:\n    x: s\n\n\n"
    + HINTS.format(name="K"),
}
CONTROLS = {
    "annotations read in a module that evaluates none": "class K:\n    pass\n\n\n"
    + "print(K.__annotations__)\n",
    "variable with a harmless string": HEAD
    + 's = "int"\n\n\nclass K:\n    x: s\n\n\n'
    + HINTS.format(name="K"),
    "variable of a class": HEAD
    + "class A:\n    pass\n\n\nclass K:\n    x: A\n\n\n"
    + HINTS.format(name="K"),
}


def _counter(root: Path) -> int:
    (root / "src/app/lib/__init__.py").write_text(
        "from pathlib import Path\n"
        "with open(Path(__file__).resolve().parents[3] / 'counter.txt', 'a') as f:\n"
        "    f.write('loaded\\n')\n"
    )
    code = "import sys; sys.path.insert(0, 'src'); import app.consumer"
    subprocess.run(["python3.12", "-I", "-c", code], cwd=root, capture_output=True)
    counter = root / "counter.txt"
    return len(counter.read_text().splitlines()) if counter.exists() else 0


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_route_to_an_evaluated_string_annotation_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _counter(root) == 1, "CPython must load app.lib once: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_text_that_loads_nothing_holds_the_evaluation_site(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert _counter(root) == 0, "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    # AD-1176: the call that evaluates the annotations is one site; a declaration gives PASS.
    expected = "UNKNOWN" if "get_type_hints" in str(CONTROLS[name]) else "PASS"
    assert frame["rules"]["NO-LIB"][1] == expected, frame
