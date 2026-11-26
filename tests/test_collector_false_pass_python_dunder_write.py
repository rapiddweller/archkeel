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
    # #2090: Python reads the chain of an exception to print it and never calls it as a hook.
    "chain-assign": (
        HOOK
        + "e = ValueError('a')\ne.__cause__ = KeyError('b')\ne.__context__ = KeyError('c')\n"
        + "e.__traceback__ = None\ne.__suppress_context__ = True\ne.__notes__ = ['n']\n"
    ),
    "chain-setattr": (
        HOOK
        + "e = ValueError('a')\nsetattr(e, '__cause__', KeyError('b'))\n"
        + "object.__setattr__(e, '__context__', KeyError('c'))\n"
        + "setattr(e, '__suppress_context__', False)\n"
    ),
    # The chain write beside a class that has a loader `__call__`: the class gets no new route.
    "chain-beside-call": (
        HOOK
        + "e = ValueError('a')\ne.__cause__ = KeyError('b')\n"
        + "class L:\n    def __call__(self, *a):\n        pass\n\n\nL()('x')\n"
    ),
}

# #2090: a write of an exception-chain name can run project code through the receiver. The scan
# reads no type, so the exemption holds only when no hook of the project can be reached. CPython
# 3.12 runs each hook (counter file); the scan must not say PASS.
RUN = "open('counter.txt', 'a').write('hooked')"


def _code(*lines: str) -> str:
    return "\n".join(lines).replace("RUN", RUN) + "\n"


SETTER = ("class K:", "    @property", "    def __cause__(self):", "        return 1")
CHAIN_HOOKS = {
    "setattr-method": _code(
        "class K:",
        "    def __setattr__(self, n, v):",
        "        RUN",
        "",
        "e = K()",
        "e.__cause__ = 1",
    ),
    "setattr-call": _code(
        "class K:",
        "    def __setattr__(self, n, v):",
        "        RUN",
        "",
        "setattr(K(), '__cause__', 1)",
    ),
    "descriptor-set": _code(
        "class D:",
        "    def __set__(self, o, v):",
        "        RUN",
        "",
        "class K:",
        "    __cause__ = D()",
        "",
        "K().__cause__ = 1",
    ),
    "property-setter": _code(
        *SETTER,
        "    @__cause__.setter",
        "    def __cause__(self, v):",
        "        RUN",
        "",
        "K().__cause__ = 2",
    ),
    "property-setter-setattr": _code(
        *SETTER,
        "    @__cause__.setter",
        "    def __cause__(self, v):",
        "        RUN",
        "",
        "setattr(K(), '__cause__', 2)",
    ),
    "property-deleter": _code(
        *SETTER,
        "    @__cause__.deleter",
        "    def __cause__(self):",
        "        RUN",
        "",
        "delattr(K(), '__cause__')",
    ),
    "property-deleter-del": _code(
        *SETTER,
        "    @__cause__.deleter",
        "    def __cause__(self):",
        "        RUN",
        "",
        "del K().__cause__",
    ),
    "metaclass-setattr": _code(
        "class M(type):",
        "    def __setattr__(cls, n, v):",
        "        RUN",
        "",
        "class K(metaclass=M):",
        "    pass",
        "",
        "K.__cause__ = 1",
    ),
    "notes-list-subclass": _code(
        "class L(list):",
        "    def append(self, x):",
        "        RUN",
        "",
        "e = ValueError('a')",
        "e.__notes__ = L()",
        "e.__notes__.append('x')",
    ),
    "notes-list-subclass-attribute": _code(
        "class L(list):",
        "    def append(self, x):",
        "        RUN",
        "",
        "class K:",
        "    pass",
        "",
        "k = K()",
        "k.__notes__ = L()",
        "k.__notes__.append('x')",
    ),
    "notes-iadd": _code(
        "class L(list):",
        "    def __iadd__(self, x):",
        "        RUN",
        "        return self",
        "",
        "k = ValueError('a')",
        "k.__notes__ = L()",
        "k.__notes__ += ['x']",
    ),
    "traceback-finalizer": _code(
        "class T:",
        "    def __del__(self):",
        "        RUN",
        "",
        "e = ValueError('a')",
        "e.__traceback__ = T()",
        "e.__traceback__ = None",
    ),
    "traceback-finalizer-setattr": _code(
        "class T:",
        "    def __del__(self):",
        "        RUN",
        "",
        "class K:",
        "    pass",
        "",
        "k = K()",
        "setattr(k, '__traceback__', T())",
        "delattr(k, '__traceback__')",
    ),
    "exception-subclass-setattr": _code(
        "class E(ValueError):",
        "    def __setattr__(self, n, v):",
        "        RUN",
        "",
        "e = E('a')",
        "e.__cause__ = KeyError('b')",
    ),
    "exception-subclass-property": _code(
        "class E(ValueError):",
        "    @property",
        "    def __cause__(self):",
        "        return None",
        "    @__cause__.setter",
        "    def __cause__(self, v):",
        "        RUN",
        "",
        "e = E('a')",
        "e.__cause__ = KeyError('b')",
    ),
}


def _runs_hook(root: Path, check: bool = True) -> bool:
    code = "import sys; sys.path.insert(0, 'src'); import app.consumer"
    subprocess.run(["python3.12", "-I", "-c", code], cwd=root, capture_output=True, check=check)
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


@pytest.mark.parametrize("name", sorted(CHAIN_HOOKS))
def test_a_chain_write_that_can_reach_a_project_hook_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, "def _pad():\n    pass\n\n" + CHAIN_HOOKS[name])
    # A non-exception written to a chain name raises after the hook ran: the run may end badly.
    assert _runs_hook(root, check=False), (
        "CPython must run the hook: the write reaches project code"
    )
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
