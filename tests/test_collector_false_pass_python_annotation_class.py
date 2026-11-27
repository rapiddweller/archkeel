# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2093, AD-1173: the class rule for a module that evaluates annotations.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. `app/lib` appends a line
to a counter file when CPython loads it. Each plant makes CPython 3.12 load it (the counter is 1),
so the rule `NO-LIB` must be UNKNOWN or FAIL, never PASS. Each control makes CPython leave the
counter at 0 and the rule is PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_collector_false_pass_python_annotation_routes import _counter
from test_collector_false_pass_python_trojan_attribute import _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

IMPORT = "__import__('app.lib')"
HEAD = "import contextlib\nimport operator\nimport typing\n\n\n"
HINTS = "\n\ntry:\n    typing.get_type_hints(K)\nexcept Exception:\n    pass\n"
EMPTY = "class K:\n    pass\n\n\n"
USE = "\n\nclass K:\n    x: s\n"


def one(body: str) -> str:
    return HEAD + body + HINTS


def named(value: str) -> str:
    return one(f"{value}\n{USE}")


WRITES = {
    "print of update": one(EMPTY + f'print(K.__annotations__.update(x="{IMPORT}"))\n'),
    "lambda": one(EMPTY + f'(lambda: K.__annotations__.update(x="{IMPORT}"))()\n'),
    "comprehension": one(
        EMPTY + f'[K.__annotations__.__setitem__("x", "{IMPORT}") for _ in [0]]\n'
    ),
    "return": one(
        EMPTY + f'def f():\n    return K.__annotations__.update(x="{IMPORT}")\n\n\nf()\n'
    ),
    "with target": one(
        EMPTY + f'with contextlib.nullcontext("{IMPORT}") as K.__annotations__["x"]:\n    pass\n'
    ),
    "for target": one(EMPTY + f'for K.__annotations__["x"] in ["{IMPORT}"]:\n    pass\n'),
    "operator setitem": one(EMPTY + f'operator.setitem(K.__annotations__, "x", "{IMPORT}")\n'),
    "alias of annotations": one(EMPTY + f'a = K.__annotations__\na["x"] = "{IMPORT}"\n'),
    "annotations key in type()": HEAD
    + f'K = type("K", (), {{"__annotations__": {{"x": "{IMPORT}"}}}})\n'
    + HINTS,
}
NAMES = {
    "tuple unpack": named(f's, t = "{IMPORT}", "int"'),
    "walrus": named(f's = None\n(s := "{IMPORT}")'),
    "augmented": named(f's = ""\ns += "{IMPORT}"'),
    "augmented in a loop": named(f's = ""\nfor _ in range(2):\n    s = "{IMPORT}"\n    s += ""'),
    "for target name": named(f'for s in ["{IMPORT}"]:\n    pass'),
    "conditional": named(f's = "{IMPORT}" if typing else "int"'),
    "and": named(f's = 1 and "{IMPORT}"'),
    "str call": named(f's = str("{IMPORT}")'),
    "replace": named("s = \"__import__('app.libX')\".replace('X', '')"),
    "decode": named(f's = b"{IMPORT}".decode()'),
    "dict item": one(f'd = {{"a": "{IMPORT}"}}\n\n\nclass K:\n    x: d["a"]\n'),
    "class attribute": one(f'class C:\n    s = "{IMPORT}"\n\n\nclass K:\n    x: C.s\n'),
    "attribute set on an object": one(
        f'import types\n\nm = types.ModuleType("m")\nm.s = "{IMPORT}"\n\n\nclass K:\n    x: m.s\n'
    ),
    "with as a name": named(f'with contextlib.nullcontext("{IMPORT}") as s:\n    pass'),
}
BUILDERS = {
    "ForwardRef of a name": HEAD
    + f's = "{IMPORT}"\nref = typing.ForwardRef(s)\n'
    + "try:\n    typing._eval_type(ref, globals(), None)\nexcept Exception:\n    pass\n",
    "TypedDict": HEAD + f'K = typing.TypedDict("K", {{"x": "{IMPORT}"}})\n' + HINTS,
    "NamedTuple": HEAD + f'K = typing.NamedTuple("K", [("x", "{IMPORT}")])\n' + HINTS,
}
LOOKUP = {
    "evaluator looked up by name": HEAD
    + f's, t = "{IMPORT}", "int"\n\n\nclass K:\n    x: s\n\n\n'
    + 'try:\n    getattr(typing, "get_type_hints")(K)\nexcept Exception:\n    pass\n',
}
REVIEW = {
    "signature of a nested function": HEAD
    + f'def outer():\n    def inner(x: b"{IMPORT}".decode()):\n        pass\n\n'
    + "    return inner\n\n\n"
    + "K = outer()\n"
    + HINTS,
    "cast returns the string": named(f's = typing.cast(str, "{IMPORT}")'),
    "evaluator imported under an alias": "from typing import get_type_hints as hints\n\n\n"
    + f's = str("{IMPORT}")\n\n\nclass K:\n    x: s\n\n\n'
    + "try:\n    hints(K)\nexcept Exception:\n    pass\n",
}
REVIEW2 = {
    "quoted annotation of a computed name": named(f's = str("{IMPORT}")').replace("x: s", 'x: "s"'),
    "alias of a held string": named(f's = "{IMPORT}"\nt = s').replace("x: s", "x: t"),
    "builder imported under an alias": "from typing import TypedDict as TD, get_type_hints\n\n\n"
    + f'K = TD("K", {{"x": "{IMPORT}"}})\n\n\n'
    + "try:\n    get_type_hints(K)\nexcept Exception:\n    pass\n",
}
REVIEW3 = {
    "alias with a computed name in a subscript": named(
        f's = str("{IMPORT}")\nAlias = list[s]'
    ).replace("x: s", "x: Alias"),
    "alias with a string in a subscript": one(
        f'Alias = list["{IMPORT}"]\n\n\nclass K:\n    x: Alias\n'
    ),
    "builder bound to another name": HEAD
    + "TD = typing.TypedDict\n"
    + f'K = TD("K", {{"x": "{IMPORT}"}})\n'
    + HINTS,
}
REVIEW4 = {
    "literal ForwardRef under an alias": "from typing import ForwardRef as FR, _eval_type\n\n\n"
    + f'ref = FR("{IMPORT}")\n'
    + "try:\n    _eval_type(ref, {}, {})\nexcept Exception:\n    pass\n",
    "held text names a computed name": named(f't = str("{IMPORT}")\ns = "t"'),
    "shadowed type factory": named(f'def TypeVar(v):\n    return v\n\n\ns = TypeVar("{IMPORT}")'),
}
REVIEW5 = {
    "held name reassigned from a computed name": named(f's = "int"\nt = str("{IMPORT}")\ns = t'),
}
PLANTS = {
    **WRITES,
    **NAMES,
    **BUILDERS,
    **LOOKUP,
    **REVIEW,
    **REVIEW2,
    **REVIEW3,
    **REVIEW4,
    **REVIEW5,
}
CONTROLS = {
    "plain forms": HEAD
    + "class K:\n    x: int\n    y: typing.Optional[str]\n    z: list[int] | None\n"
    + "    w: typing.Annotated[int, 'meta']\n    v: 'K'\n"
    + HINTS,
    "alias of a type": HEAD
    + "Alias = list[int]\nT = typing.TypeVar('T')\n\n\nclass K:\n    x: Alias\n    y: T\n"
    + HINTS,
    "harmless string in a name": named('s = "int"'),
    "annotations read without an evaluator": "class K:\n    x: int\n\n\nprint(K.__annotations__)\n",
    "class and function names": HEAD
    + "class A:\n    pass\n\n\ndef f(a: A) -> A:\n    return a\n\n\nclass K:\n    x: A\n"
    + HINTS,
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_form_that_puts_a_string_into_an_annotation_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PLANTS[name])
    assert _counter(root) == 1, "CPython must load app.lib once: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_module_with_plain_annotations_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert _counter(root) == 0, "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
