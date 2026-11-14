# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python symbol declarations (AD-514): the hard forms of binding.

Each plant gives its module, the planned entities and the truth. The rows of release 4.0.1 and of
the core are pinned in `python_symbol_rows.json` (`tests/python_symbol_rows.py` writes them).
"""

from __future__ import annotations

from python_symbol_sources import PUBLIC, Plant, Want

C = Want("class", "A")
PRIVATE = {"visibility": {"kind": "private", "basis": "declared"}}
STATIC = {"modifiers": ["static"]}
HELPER = "def deco(fn):\n    return 5\n\n"
META = "class M(type):\n    def __new__(mcs, name, bases, body):\n        return 5\n\n"


def fn(name: str = "f", **extra: object) -> Want:
    return Want("function", name, dict(extra))


def pl(source: str, wants: list[Want], truth: str, **files: str) -> Plant:
    return Plant(source, tuple(wants), truth, files=files)


# truth PASS: Python binds what the target plans. DIFF: it does not.
SHAPES: dict[str, Plant] = {
    "class": pl("class A:\n    pass\n", [C], "PASS"),
    "function": pl("def f(a: int) -> str:\n    return ''\n", [fn()], "PASS"),
    "function-signature": pl(
        "def f(a: int) -> str:\n    return ''\n",
        [
            fn(
                signature={
                    "parameters": [
                        {
                            "name": "a",
                            "annotation": "int",
                            "kind": "positional",
                            "default_known": True,
                        }
                    ],
                    "returns": "str",
                },
                visibility=PUBLIC,
            )
        ],
        "PASS",
    ),
    "function-signature-differs": pl(
        "def f(a: int) -> str:\n    return ''\n",
        [fn(signature={"parameters": [], "returns": "int"})],
        "DIFF",
    ),
    "async-function": pl("async def f():\n    pass\n", [fn(modifiers=["async"])], "PASS"),
    "method": pl("class A:\n    def m(self):\n        pass\n", [C, Want("method", "A.m")], "PASS"),
    "staticmethod": pl(
        "class A:\n    @staticmethod\n    def s():\n        pass\n",
        [C, Want("method", "A.s", STATIC)],
        "PASS",
    ),
    "classmethod": pl(
        "class A:\n    @classmethod\n    def k(cls):\n        pass\n",
        [C, Want("method", "A.k", {"modifiers": ["class"]})],
        "PASS",
    ),
    "annotated-attribute": pl(
        "class A:\n    x: int\n",
        [C, Want("attribute", "A.x", {"annotation": "int"})],
        "PASS",
    ),
    "assigned-attribute": pl(
        "class A:\n    limit = 10\n", [C, Want("attribute", "A.limit", STATIC)], "PASS"
    ),
    "private-attribute": pl(
        "class A:\n    _t: str\n", [C, Want("attribute", "A._t", PRIVATE)], "PASS"
    ),
    "enum-literal": pl(
        "from enum import Enum\n\n\nclass E(Enum):\n    R = 1\n    G = 2\n",
        [Want("enum", "E"), Want("enum_literal", "E.R")],
        "PASS",
    ),
    "protocol": pl(
        "from typing import Protocol\n\n\nclass P(Protocol):\n    pass\n",
        [Want("interface", "P")],
        "PASS",
    ),
    "qualified-enum": pl(
        "import enum\n\n\nclass E(enum.IntEnum):\n    R = 1\n", [Want("enum", "E")], "PASS"
    ),
    "nested-class": pl("class A:\n    class B:\n        pass\n", [C, Want("class", "A.B")], "PASS"),
    "local-base": pl(
        "class A:\n    pass\n\n\nclass B(A):\n    pass\n", [C, Want("class", "B")], "PASS"
    ),
    "builtin-base": pl("class A(Exception):\n    pass\n", [C], "PASS"),
    "slots": pl("class A:\n    __slots__ = ('x',)\n", [C], "PASS"),
    "all-list": pl("__all__ = ['f']\n\n\ndef f():\n    pass\n", [fn()], "PASS"),
    "wrong-kind": pl("class f:\n    pass\n", [fn()], "DIFF"),
    "enum-as-class": pl("from enum import Enum\n\n\nclass A(Enum):\n    R = 1\n", [C], "DIFF"),
    "protocol-subclass": pl(
        "from typing import Protocol\n\n\nclass P(Protocol):\n    pass\n\n\n"
        "class A(P):\n    pass\n",
        [Want("interface", "P"), Want("interface", "A")],
        "DIFF",
    ),
}

BOUND: dict[str, Plant] = {
    "redefined": pl("def f():\n    pass\n\n\ndef f(a):\n    pass\n", [fn()], "DIFF"),
    "def-then-assign": pl("def f():\n    pass\n\n\nf = 5\n", [fn()], "DIFF"),
    "conditional": pl("if __name__:\n    def f():\n        pass\n", [fn()], "PASS"),
    "try-except": pl(
        "try:\n    def f():\n        pass\nexcept ValueError:\n    pass\n", [fn()], "PASS"
    ),
    "type-checking": pl(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    def f():\n        pass\n"
        "else:\n    def f():\n        pass\n",
        [fn()],
        "PASS",
    ),
    "deleted": pl("def f():\n    pass\n\n\ndel f\n", [fn()], "DIFF"),
    "for-target": pl("def f():\n    pass\n\n\nfor f in range(2):\n    pass\n", [fn()], "DIFF"),
    "with-target": pl(
        "from contextlib import nullcontext\n\n\ndef f():\n    pass\n\n\n"
        "with nullcontext(5) as f:\n    pass\n",
        [fn()],
        "DIFF",
    ),
    "walrus": pl("def f():\n    pass\n\n\nvalues = [(f := 5)]\n", [fn()], "DIFF"),
    "except-target": pl(
        "def f():\n    pass\n\n\ntry:\n    pass\nexcept ValueError as f:\n    pass\n",
        [fn()],
        "DIFF",
    ),
    "match-capture": pl(
        "def f():\n    pass\n\n\nmatch 5:\n    case f:\n        pass\n", [fn()], "DIFF"
    ),
    "import-over-def": pl("def f():\n    pass\n\n\nimport os as f\n", [fn()], "DIFF"),
    "augmented": pl("def f():\n    pass\n\n\nf += 1\n", [fn()], "DIFF"),
    "global-write": pl(
        "def f():\n    pass\n\n\ndef swap():\n    global f\n    f = 5\n", [fn()], "DIFF"
    ),
    "star-import": pl(
        "def f():\n    pass\n\n\nfrom demo.other import *\n",
        [fn()],
        "DIFF",
        **{"other.py": "f = 5\n"},
    ),
    "class-redefined": pl("class A:\n    pass\n\n\nclass A:\n    x = 1\n", [C], "DIFF"),
    "module-getattr": pl("def __getattr__(name):\n    return lambda: 1\n", [fn("g")], "PASS"),
    "globals-write": pl("class f:\n    pass\n\n\nglobals()['f'] = lambda: 1\n", [fn()], "PASS"),
    "exec-def": pl("exec('def f(): return 5')\n", [fn()], "PASS"),
    "write-from-other": pl(
        "def f():\n    pass\n",
        [fn()],
        "DIFF",
        **{"user.py": "import demo.m as m\n\nm.f = 5\n"},
    ),
}

DECORATED: dict[str, Plant] = {
    "decorator-replaces": pl(HELPER + "@deco\ndef f():\n    pass\n", [fn()], "DIFF"),
    "decorated-class": pl(HELPER + "@deco\nclass A:\n    pass\n", [C], "DIFF"),
    "dataclass": pl(
        "from dataclasses import dataclass\n\n\n@dataclass\nclass A:\n    x: int\n", [C], "PASS"
    ),
    "property": pl(
        "class A:\n    @property\n    def p(self):\n        return 1\n",
        [C, Want("method", "A.p")],
        "DIFF",
    ),
    "wraps": pl(
        "import functools\n\n\n@functools.wraps(len)\ndef f():\n    pass\n", [fn()], "DIFF"
    ),
    "overload": pl(
        "from typing import overload\n\n\n@overload\ndef f(a: int) -> int: ...\n\n\n"
        "def f(a):\n    return a\n",
        [fn()],
        "PASS",
    ),
    "shadowed-staticmethod": pl(
        "staticmethod = lambda fn: 5\n\n\n"
        "class A:\n    @staticmethod\n    def s():\n        pass\n",
        [C, Want("method", "A.s", STATIC)],
        "DIFF",
    ),
}

CLASSES: dict[str, Plant] = {
    "metaclass-replaces": pl(META + "class A(metaclass=M):\n    pass\n", [C], "DIFF"),
    "metaclass-inherited": pl(
        META + "class Base(metaclass=M):\n    pass\n\n\nclass A(Base):\n    pass\n", [C], "DIFF"
    ),
    "namedtuple": pl(
        "from typing import NamedTuple\n\n\nclass A(NamedTuple):\n    x: int\n", [C], "PASS"
    ),
    "typeddict": pl(
        "from typing import TypedDict\n\n\nclass A(TypedDict):\n    x: int\n", [C], "PASS"
    ),
    "unknown-base": pl(
        "from demo.other import Base\n\n\nclass A(Base):\n    pass\n",
        [C],
        "DIFF",
        **{"other.py": "from enum import Enum\n\n\nclass Base(Enum):\n    pass\n"},
    ),
    "enum-rebound": pl(
        "from enum import Enum\n\nEnum = object\n\n\nclass E(Enum):\n    R = 1\n",
        [Want("enum", "E")],
        "DIFF",
    ),
    "enum-through-base": pl(
        "from enum import Enum\n\n\nclass Base(Enum):\n    pass\n\n\nclass A(Base):\n    R = 1\n",
        [C],
        "DIFF",
    ),
    "generic-base": pl(
        "from typing import Generic, TypeVar\n\nT = TypeVar('T')\n\n\n"
        "class A(Generic[T]):\n    pass\n",
        [C],
        "PASS",
    ),
}

MEMBERS: dict[str, Plant] = {
    "init-attribute": pl(
        "class A:\n    def __init__(self):\n        self.x = 1\n",
        [C, Want("attribute", "A.x")],
        "PASS",
    ),
    "setattr-instance": pl(
        "class A:\n    def __init__(self):\n        setattr(self, 'x', 1)\n",
        [C, Want("attribute", "A.x")],
        "PASS",
    ),
    "dict-instance": pl(
        "class A:\n    def __init__(self):\n        self.__dict__['x'] = 1\n",
        [C, Want("attribute", "A.x")],
        "PASS",
    ),
    "loop-attribute": pl(
        "class A:\n    for i in range(2):\n        pass\n", [C, Want("attribute", "A.i")], "PASS"
    ),
    "comprehension-attribute": pl(
        "class A:\n    y = [1]\n    z = [n for n in y]\n",
        [C, Want("attribute", "A.n")],
        "DIFF",
    ),
    "attribute-twice": pl(
        "class A:\n    x = 1\n    x = 2\n", [C, Want("attribute", "A.x", STATIC)], "PASS"
    ),
    "attribute-over-method": pl(
        "class A:\n    def m(self):\n        pass\n    m = 5\n",
        [C, Want("method", "A.m")],
        "DIFF",
    ),
    "write-after-class": pl(
        "class A:\n    def m(self):\n        pass\n\n\nA.m = None\n",
        [C, Want("method", "A.m")],
        "DIFF",
    ),
    "setattr-class": pl(
        "class A:\n    def m(self):\n        pass\n\n\nsetattr(A, 'm', None)\n",
        [C, Want("method", "A.m")],
        "DIFF",
    ),
    "classmethod-write": pl(
        "class A:\n    def m(self):\n        pass\n\n    @classmethod\n    def k(cls):\n"
        "        cls.m = None\n",
        [C, Want("method", "A.m")],
        "DIFF",
    ),
    "added-attribute": pl(
        "class A:\n    pass\n\n\nA.x = 1\n", [C, Want("attribute", "A.x")], "PASS"
    ),
    "enum-open-body": pl(
        "from enum import Enum\n\n\ndef make():\n    return 1\n\n\n"
        "class E(Enum):\n    R = make()\n",
        [Want("enum", "E"), Want("enum_literal", "E.R")],
        "PASS",
    ),
    "enum-ignore": pl(
        "from enum import Enum\n\n\nclass E(Enum):\n    _ignore_ = 'R'\n    R = 1\n",
        [Want("enum", "E"), Want("enum_literal", "E.R")],
        "DIFF",
    ),
    "enum-annotated": pl(
        "from enum import Enum\n\n\nclass E(Enum):\n    R: int\n",
        [Want("enum", "E"), Want("enum_literal", "E.R")],
        "DIFF",
    ),
    "nested-function": pl(
        "def outer():\n    def inner():\n        pass\n", [fn("outer.inner")], "PASS"
    ),
    "number-default": pl("def f(a: int = 1):\n    pass\n", [fn()], "PASS"),
    "subscript-annotation": pl("def f(a: list[int]):\n    pass\n", [fn()], "PASS"),
    "module-value": pl("VERSION = 1\n", [Want("constant", "VERSION")], "PASS"),
}

PLANTS: dict[str, Plant] = {**SHAPES, **BOUND, **DECORATED, **CLASSES, **MEMBERS}
