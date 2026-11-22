# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1058 (third review, B7): a literal attribute name can still hand out reflection.

Consumer: a CI job that must never read PASS for a project that imports a forbidden module.
`getattr(json, "__dict__")` gives the dictionary of a module, and `getattr(f, "__getattribute__")`
gives a method that reads any attribute by a name that is built later. Python 3.12 imports
`app.lib` in both plants. The sweep names each dunder of `object`, `FunctionType`, `ModuleType`
and `type`: a literal read of one is a site unless the allow-list says that it hands out only text.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

PLAIN = {"__name__", "__doc__", "__file__", "__version__", "__all__", "__module__", "__qualname__"}
BUILTINS = "'__bui' + 'ltins__'"
IMPORT = "'__imp' + 'ort__'"
PLANTS = {
    # Plant A of the review: the dictionary of a module holds `__builtins__`.
    "module-dict": (
        "import json\n\n\ndef load(k1, k2, t):\n    d = getattr(json, '__dict__')\n"
        f"    return d[k1][k2](t)\n\n\nload({BUILTINS}, {IMPORT}, 'app.lib')\n"
    ),
    # Plant B: the method `__getattribute__` of a function reads any attribute by a computed name.
    "getattribute-method": (
        "def f():\n    pass\n\n\ndef load(k, k1, k2, t):\n    ga = getattr(f, '__getattribute__')\n"
        "    return ga(k)[k1][k2](t)\n\n\n"
        f"load('__glo' + 'bals__', {BUILTINS}, {IMPORT}, 'app.lib')\n"
    ),
    "local-name": (
        "import json\n\n\ndef load(k1, k2, t):\n    n = '__dict__'\n    d = getattr(json, n)\n"
        f"    return d[k1][k2](t)\n\n\nload({BUILTINS}, {IMPORT}, 'app.lib')\n"
    ),
    "method-call": (
        "import json\n\n\ndef load(k1, k2, t):\n    d = json.__getattribute__('__dict__')\n"
        f"    return d[k1][k2](t)\n\n\nload({BUILTINS}, {IMPORT}, 'app.lib')\n"
    ),
}
DUNDERS = sorted(
    {
        name
        for owner in (object, types.FunctionType, types.ModuleType, type)
        for name in dir(owner)
        if name.startswith("__") and name.endswith("__")
    }
)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_literal_name_that_hands_out_reflection_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.fixture(scope="module")
def flagged(tmp_path_factory: pytest.TempPathFactory, release_core: Path) -> set[str]:
    """The dunder names whose literal `getattr` has a gap, from one scan of all of them."""
    source = "".join(f"getattr(x, '{name}')\n" for name in DUNDERS)
    root = _root(tmp_path_factory.mktemp("sweep"), source)
    with pytest.MonkeyPatch.context() as patch:
        frame = _verdict(root, release_core, patch)["frame"]
    lines = {
        frame["locations"][evidence]["line"]
        for gap in frame["collection_gaps"]
        for evidence in gap["evidence"]
        if frame["locations"][evidence]["path"].endswith("consumer.py")
    }
    return {name for line, name in enumerate(DUNDERS, 1) if line in lines}


@pytest.mark.parametrize("name", DUNDERS)
def test_a_literal_dunder_is_a_site_unless_it_hands_out_only_text(
    flagged: set[str], name: str
) -> None:
    assert (name in flagged) == (name not in PLAIN), name
