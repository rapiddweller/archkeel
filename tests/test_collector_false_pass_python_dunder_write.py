# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1979: a write of a literal dunder name is a site, never a silent PASS.

A write of `__call__`, `__getattr__`, `__getattribute__`, `__init__`, `__new__` or `__class__`
(through `setattr`, `delattr`, an assignment or a `del`) changes what a later plain call or
access runs. CPython 3.12 runs each plant, and a counter file proves that the hook ran. The scan
reads the same code and must not say PASS. A control that writes a plain name, `__doc__` or
`__module__` changes no behavior, leaves no counter file and keeps PASS.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

COUNT = "open('counter.txt', 'a').write('hooked')"
HOOK = f"def hook(self, *args):\n    {COUNT}\n\n\nclass K:\n    pass\n\n\n"
BASE = f"class B:\n    def __call__(self, *args):\n        {COUNT}\n\n\n"
PLANTS = {
    "call-setattr": HOOK + "setattr(K, '__call__', hook)\nK()('x')\n",
    "call-assign": HOOK + "K.__call__ = hook\nK()('x')\n",
    "getattr-assign": HOOK + "K.__getattr__ = hook\nK().missing\n",
    "getattribute-setattr": HOOK + "setattr(K, '__getattribute__', hook)\nK().anything\n",
    "init-assign": HOOK + "K.__init__ = hook\nK()\n",
    "new-setattr": HOOK + "setattr(K, '__new__', hook)\nK()\n",
    "class-assign": (
        f"class L:\n    def __call__(self, *args):\n        {COUNT}\n\n\nclass K:\n    pass\n\n\n"
        "k = K()\nk.__class__ = L\nk('x')\n"
    ),
    "call-delattr": (
        BASE + "class K(B):\n    def __call__(self, *args):\n        pass\n\n\n"
        "delattr(K, '__call__')\nK()('x')\n"
    ),
    "call-del": (
        BASE + "class K(B):\n    def __call__(self, *args):\n        pass\n\n\n"
        "del K.__call__\nK()('x')\n"
    ),
    "tuple-target": HOOK + "K.__call__, other = hook, 1\nK()('x')\n",
}
CONTROLS = {
    "plain-assign": HOOK + "K.value = 1\nK()\n",
    "plain-setattr": HOOK + "setattr(K, 'value', 1)\ndelattr(K, 'value')\nK()\n",
    "doc-module": HOOK + "K.__doc__ = 'text'\nK.__module__ = 'app.consumer'\nK()\n",
}


def _runs_hook(root: Path) -> bool:
    code = "import sys; sys.path.insert(0, 'src'); import app.consumer"
    subprocess.run(["python3.12", "-I", "-c", code], cwd=root, capture_output=True, check=True)
    return (root / "counter.txt").is_file()


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_write_of_a_literal_dunder_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _runs_hook(root), "CPython must run the hook: the write changes the later call"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_write_that_no_behavior_reads_keeps_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _runs_hook(root), "the control must not run the hook"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame["collection_gaps"]
