# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1974, #1976, AD-1095: Python evaluates a string annotation, and the text can import a module.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. Each plant imports
`app.lib` under CPython 3.12 (the test asserts it), so the rule `NO-LIB` must be UNKNOWN or FAIL,
never PASS. Each control has a string annotation or a literal value that names no hazard: CPython
leaves `app.lib` unloaded and the rule is PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

TEXT = "\"__import__('app.lib')\""
GUARD = "try:\n    {call}\nexcept Exception:\n    pass\n"
TYPING = "import typing\n\n\n"
HINTS = GUARD.format(call="typing.get_type_hints({name})")
INSPECT = "import inspect\n\n\ndef f(x: " + TEXT + "):\n    pass\n\n\n"
SINGLE = "import functools\n\n\n@functools.singledispatch\ndef f(x):\n    pass\n\n\n"
PLANTS = {
    "get_type_hints of a class": TYPING + f"class K:\n    x: {TEXT}\n\n\n" + HINTS.format(name="K"),
    "get_type_hints of a parameter": TYPING
    + f"def f(x: {TEXT}):\n    pass\n\n\n"
    + HINTS.format(name="f"),
    "get_type_hints of a return": TYPING
    + f"def f() -> {TEXT}:\n    pass\n\n\n"
    + HINTS.format(name="f"),
    "get_type_hints of a nested string": TYPING
    + f"class K:\n    x: list[{TEXT}]\n\n\n"
    + HINTS.format(name="K"),
    "ForwardRef": TYPING
    + f"ref = typing.ForwardRef({TEXT})\n"
    + GUARD.format(call="typing._eval_type(ref, globals(), None)"),
    "inspect.signature eval_str": INSPECT
    + GUARD.format(call="inspect.signature(f, eval_str=True)"),
    "inspect.get_annotations eval_str": INSPECT
    + GUARD.format(call="inspect.get_annotations(f, eval_str=True)"),
    "singledispatch register": SINGLE
    + GUARD.format(call=f"@f.register\n    def g(x: {TEXT}):\n        pass"),
}
CONTROLS = {
    "plain string annotation": TYPING
    + "class K:\n    x: 'list[int]'\n\n\n"
    + HINTS.format(name="K"),
    "optional in a string": TYPING
    + 'class K:\n    y: "typing.Optional[int]"\n\n\n'
    + HINTS.format(name="K"),
    "literal value": TYPING
    + "class K:\n    x: typing.Literal['eval', 'help']\n\n\n"
    + HINTS.format(name="K"),
    "string that is no annotation": "text = \"__import__('app.libx')\"\nprint(len(text))\n",
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_string_annotation_that_imports_a_module_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_string_annotation_without_a_hazard_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
