# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2196, AD-1340: a reserved name that is only tested is data; every other use keeps the gap.

Consumer: `archkeel validate`. `NO-LIB` forbids `app.consumer` to depend on `app.lib`. A control
tests reserved names (`name in {"__globals__", "__import__"}`) and imports nothing: CPython leaves
`app.lib` unloaded and the rule is PASS. Each plant sends a reserved name to a lookup and imports
`app.lib` under CPython 3.12 (the test asserts it), so the rule must be UNKNOWN or FAIL.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

LOAD = "('app.lib')"
B = "import builtins\n"
TEST = "def reserved(name):\n    return name in {'__globals__', '__builtins__', '__import__'}\n\n\n"
EQ = (
    "import string\n\n\nclass Lookup:\n    def __eq__(self, name):\n"
    "        space = string.Formatter().get_field('0.' + name, (lambda: None,), {})[0]\n"
    "        space[''.join(['__bui', 'ltins__'])][''.join(['__imp', 'ort__'])]('app.lib')\n"
    "        return False\n\n\n"
)
# name -> (consumer source, source of the module app.rules)
CONTROLS = {
    "reproduction of the issue": (
        "def reserved(name):\n    return type(name) is str and name in "
        "{'__globals__', '__builtins__', '__import__'}\n\n\nreserved('x')\n",
        "",
    ),
    "tuple and list": (
        "def f(n):\n    return type(n) is str and n in ('__globals__',)\n\n\n"
        "def g(n):\n    return type(n) is str and n not in ['__import__']\n\n\nf('x')\ng('x')\n",
        "",
    ),
    "equality": (
        "def f(n):\n    return type(n) is str and n == '__import__'\n\n\nf('x')\n",
        "",
    ),
    "frozenset bound to a module name": (
        "_RESERVED = frozenset({'__globals__', '__import__'})\n\n\n"
        "def f(n):\n    return type(n) is str and n in _RESERVED\n\n\nf('x')\n",
        "",
    ),
    "set in another module that nobody reads": (
        "from app import rules\n\nrules.reserved('x')\n",
        "_R = frozenset({'__import__'})\n\n\n"
        "def reserved(n):\n    return type(n) is str and n in _R\n",
    ),
    "exact str beside an equality hook": (
        EQ.replace("return False\n", "return False\n\n    def __hash__(self):\n        return 1\n")
        + "def reserved(name):\n"
        "    return type(name) is str and name in {'__globals__', '__import__'}\n\n\n"
        "reserved('x')\n",
        "",
    ),
}
MATCH = (
    "import string\n\n\nclass C:\n    __match_args__ = ('__globals__',)\n"
    "    n = 'x'\n    checked = type(n) is str and n in __match_args__\n\n"
    "    def __getattr__(self, name):\n"
    "        space = string.Formatter().get_field('0.' + name, (lambda: None,), {})[0]\n"
    "        space[''.join(['__bui', 'ltins__'])][''.join(['__imp', 'ort__'])]('app.lib')\n"
    "        return 1\n\n\n"
    "def run():\n    match C():\n        case C(value):\n            return value\n\n\n"
)
PREPARE = (
    "class Space(dict):\n    reads = 0\n\n    def __getitem__(self, key):\n"
    "        if key != 'n':\n            return super().__getitem__(key)\n"
    "        self.reads += 1\n        return 'x' if self.reads == 1 else Lookup()\n\n\n"
    "class Meta(type):\n    @classmethod\n    def __prepare__(mcls, name, bases):\n"
    "        return Space()\n\n\n"
    "def run():\n    class C(metaclass=Meta):\n"
    "        ok = type(n) is str and n == '__globals__'\n\n\n"
)
TRACE = (
    "import sys\n\nn = 'x'\n\n\ndef check():\n    return (type(n) is str\n"
    "            and n == '__globals__')\n\n\n"
    "def tracer(frame, event, arg):\n    global n\n"
    "    if event == 'line' and frame.f_code.co_name == 'check':\n"
    "        if frame.f_lineno == check.__code__.co_firstlineno + 2:\n"
    "            n = Lookup()\n    return tracer\n\n\n"
    "def run():\n    sys.settrace(tracer)\n    try:\n        check()\n"
    "    finally:\n        sys.settrace(None)\n\n\n"
)
PLANTS = {
    "global name that a trace function replaces between the two reads": (
        quiet(EQ + TRACE, "run()"),
        "",
    ),
    "class body whose namespace answers differently the second time": (
        quiet(EQ + PREPARE, "run()"),
        "",
    ),
    "class attribute that a match statement reads by itself": (quiet(MATCH, "run()"), ""),
    "comparison chain that shares the literal": (
        quiet(EQ, "'_' in '__globals__' == Lookup()"),
        "",
    ),
    "equality hook bound by an unpacking assignment": (
        quiet(
            EQ.replace("def __eq__(self, name):", "def compare(self, name):").replace(
                "        return False\n",
                "        return False\n    __eq__, unused = compare, None\n",
            ),
            "Lookup() == '__globals__'",
        ),
        "",
    ),
    "set display with an element that runs the hook": (
        quiet(
            EQ.replace(
                "return False\n",
                "return False\n\n    def __hash__(self):\n        return hash('__globals__')\n",
            )
            + "n = 'x'\n",
            "type(n) is str and n in {'__globals__', Lookup()}",
        ),
        "",
    ),
    "set test with an inherited equality hook and an own hash": (
        quiet(
            EQ
            + "class Child(Lookup):\n    def __hash__(self):\n"
            + "        return hash('__globals__')\n\n\n",
            "Child() in {'__globals__'}",
        ),
        "",
    ),
    "name rebound between the type check and the comparison": (
        quiet(
            EQ + "n = 'x'\n",
            "type(n) is str and (n := Lookup()) and n == '__globals__'",
        ),
        "",
    ),
    "type check by equality with a metaclass hook": (
        quiet(
            EQ.replace(
                "class Lookup:",
                "class Meta(type):\n    def __eq__(cls, other):\n        return True\n\n"
                "    def __hash__(cls):\n        return 1\n\n\nclass Lookup(metaclass=Meta):",
            )
            + "n = Lookup()\n",
            "type(n) == str and n == '__globals__'",
        ),
        "",
    ),
    "comparison that calls an equality hook with the literal": (
        quiet(EQ, "Lookup() == '__globals__'"),
        "",
    ),
    "list test that calls an equality hook with the literal": (
        quiet(EQ, "Lookup() in ('__globals__',)"),
        "",
    ),
    "set test that calls an equality hook with the literal": (
        quiet(
            EQ.replace(
                "return False\n",
                "return False\n\n    def __hash__(self):\n        return hash('__globals__')\n",
            ),
            "Lookup() in {'__globals__'}",
        ),
        "",
    ),
    "literal passed to a library lookup": (
        quiet(B + "import inspect\n", f"inspect.getattr_static(builtins, '__import__'){LOAD}"),
        "",
    ),
    "literal passed to attrgetter": (
        quiet(B + "import operator\n", f"operator.attrgetter('__import__')(builtins){LOAD}"),
        "",
    ),
    "literal that a test also reads": (
        quiet(
            B + "import operator\n",
            "operator.attrgetter('__import__')(builtins)"
            f"{LOAD} if 'x' not in ('__import__',) else None",
        ),
        "",
    ),
    "getattr with the literal": (quiet(B, f"getattr(builtins, '__import__'){LOAD}"), ""),
    "literal bound to a name": (
        quiet(B + "name = '__import__'\n", f"getattr(builtins, name){LOAD}"),
        "",
    ),
    "dict key": (quiet(B, f"builtins.__dict__['__import__']{LOAD}"), ""),
    "set that an iteration reads": (
        quiet(
            B + "_RESERVED = {'__import__'}\n",
            f"[getattr(builtins, n) for n in _RESERVED][0]{LOAD}",
        ),
        "",
    ),
    "tuple that a subscript reads": (
        quiet(
            B + "_RESERVED = ('__import__',)\n_RESERVED_TEST = 'x' in _RESERVED\n",
            f"getattr(builtins, _RESERVED[0]){LOAD}",
        ),
        "",
    ),
    "test beside the lookup": (
        quiet(
            B + "name = '__import__'\n",
            f"getattr(builtins, name){LOAD} if name in {{'__import__'}} else None",
        ),
        "",
    ),
    "tuple that another module reads": (
        quiet(
            B + "from app.rules import _R\n",
            f"getattr(builtins, _R[0]){LOAD}",
        ),
        "_R = ('__import__',)\n\n\ndef reserved(n):\n    return n in _R\n",
    ),
}


def _run(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, plant: tuple):
    source, rules = plant
    root = _root(tmp_path, source)
    (root / "src/app/rules.py").write_text(rules)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_reserved_name_that_is_only_tested_leaves_the_rule_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, CONTROLS[name])

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_reserved_name_that_reaches_a_lookup_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, PLANTS[name])

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
