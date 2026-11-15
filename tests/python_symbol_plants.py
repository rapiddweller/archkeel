# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python symbol declarations (AD-518): the hard forms of binding.

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
        "DIFF",
    ),
    "annotated-attribute-value": pl(
        "class A:\n    x: int = 1\n",
        [C, Want("attribute", "A.x", {"annotation": "int"})],
        "PASS",
    ),
    "assigned-attribute": pl(
        "class A:\n    limit = 10\n", [C, Want("attribute", "A.limit", STATIC)], "PASS"
    ),
    "private-attribute": pl(
        "class A:\n    _t: str = ''\n", [C, Want("attribute", "A._t", PRIVATE)], "PASS"
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

Y = "class A:\n    def y(self):\n        return 1\n"
AY = [C, Want("method", "A.y")]
CM = "class A:\n    def m(self):\n        return 1\n"
AM = [C, Want("method", "A.m")]


def other(name: str, text: str) -> dict[str, str]:
    return {name: text}


# The review of PR 1181: a name that a header binds, a `self` that is the class, a write that no
# visitor sees, a class that escapes, a kind that no proof gives, and the smaller strict rules.
REVIEW: dict[str, Plant] = {
    "hdr-nested-base": pl(Y + "    class B((y := object)):\n        pass\n", AY, "DIFF"),
    "hdr-nested-keyword": pl(Y + "    class B(metaclass=(y := type)):\n        pass\n", AY, "DIFF"),
    "hdr-nested-deco": pl(
        Y + "    @(y := (lambda c: c))\n    class B:\n        pass\n", AY, "DIFF"
    ),
    "hdr-func-deco": pl(
        Y + "    @(y := (lambda f: f))\n    def z(self):\n        return 1\n", AY, "DIFF"
    ),
    "classmethod-self-write": pl(
        CM + "    @classmethod\n    def setup(self):\n        self.m = 1\n\n\nA.setup()\n",
        AM,
        "DIFF",
    ),
    "self-classmethod-write": pl(
        CM
        + "    def __init_subclass__(self):\n        self.m = 1\n\n\n"
        + "class B(A):\n    def m(self):\n        return 2\n",
        [Want("class", "B"), Want("method", "B.m")],
        "DIFF",
    ),
    "cls-base-local-self": pl(
        "class B:\n    def __init_subclass__(self):\n        self.y = 1\n\n\n"
        + Y.replace("class A:", "class A(B):"),
        AY,
        "DIFF",
    ),
    "module-self-name": pl(CM + "\n\nself = A\nself.m = 1\n", AM, "DIFF"),
    "self-param-is-class": pl(CM + "\n\ndef fix(self):\n    self.m = 1\n\n\nfix(A)\n", AM, "DIFF"),
    "self-rebound-write": pl(
        CM + "\n    def fix(self):\n        self = type(self)\n        self.m = 1\n\n\nA().fix()\n",
        AM,
        "DIFF",
    ),
    "type-setattr-module": pl(CM + "\n\ntype.__setattr__(A, 'm', 1)\n", AM, "DIFF"),
    "cls-getattr-write": pl(
        Y + "\n    def fix(self):\n        type.__setattr__(type(self), 'y', 1)\n\n\nA().fix()\n",
        AY,
        "DIFF",
    ),
    "cls-base-local-dict": pl(
        "class B:\n    def __init_subclass__(c):\n        type.__setattr__(c, 'y', 1)\n\n\n"
        + Y.replace("class A:", "class A(B):"),
        AY,
        "DIFF",
    ),
    "cls-set-name": pl(
        "class D:\n    def __set_name__(self, owner, name):\n"
        "        type.__setattr__(owner, 'y', 1)\n\n\n" + Y + "    d = D()\n",
        AY,
        "DIFF",
    ),
    "escape-call-other-module": pl(
        "from demo.h import fix\n\n\n" + CM + "\n\nfix(A)\n",
        AM,
        "DIFF",
        **other("h.py", "def fix(c):\n    c.m = 1\n"),
    ),
    "escape-call-clean-other": pl(
        "from demo.h import fix\n\n\n" + CM + "\n\nfix(A)\n",
        AM,
        "PASS",
        **other("h.py", "def fix(c):\n    return c\n"),
    ),
    "other-module-write": pl(
        CM, AM, "DIFF", **other("__init__.py", "from demo.m import A\nA.m = 1\n")
    ),
    "other-module-del": pl(
        CM, AM, "DIFF", **other("__init__.py", "from demo.m import A\ndel A.m\n")
    ),
    "other-module-setattr": pl(
        CM, AM, "DIFF", **other("__init__.py", "from demo.m import A\nsetattr(A, 'm', 1)\n")
    ),
    "other-module-path-write": pl(
        CM, AM, "DIFF", **other("__init__.py", "import demo.m as q\nq.A.m = 1\n")
    ),
    "other-module-pass": pl(
        CM, AM, "PASS", **other("__init__.py", "from demo.m import A\nx = A.m\ny = A()\n")
    ),
    "enum-reserved-name": pl(
        "from enum import Enum\n\n\nclass E(Enum):\n    R = 1\n    mro = 2\n",
        [Want("enum", "E"), Want("enum_literal", "E.R")],
        "DIFF",
    ),
    "ff-attr-helper-method": pl(
        "def helper(self):\n    return 1\n\n\nclass A:\n    y = helper\n",
        AY,
        "PASS",
    ),
    "ff-attr-class-nested": pl(
        "class B:\n    pass\n\n\nclass A:\n    y = B\n", [C, Want("class", "A.y")], "PASS"
    ),
    "lambda-as-method": pl("class A:\n    m = lambda self: 1\n", AM, "PASS"),
    "enum-alias-literal": pl(
        "from enum import Enum\n\n\nclass E(Enum):\n    R = 1\n    S = 1\n",
        [Want("enum", "E"), Want("enum_literal", "E.R"), Want("enum_literal", "E.S")],
        "DIFF",
    ),
    "mangled-method": pl(
        "class A:\n    def __x(self):\n        return 1\n", [C, Want("method", "A.__x")], "DIFF"
    ),
    "ann-only-attribute": pl(
        "class A:\n    x: int\n", [C, Want("attribute", "A.x", {"annotation": "int"})], "DIFF"
    ),
    "ann-rebound-builtin": pl(
        "int = str\n\n\nclass A:\n    x: int = 1\n",
        [C, Want("attribute", "A.x", {"annotation": "int"})],
        "DIFF",
    ),
    "static-drawn-plain": pl(
        "class A:\n    @staticmethod\n    def z():\n        return 1\n",
        [C, Want("method", "A.z")],
        "DIFF",
    ),
    "implicit-new-drawn-plain": pl(
        "class A:\n    def __new__(cls):\n        return object.__new__(cls)\n",
        [C, Want("method", "A.__new__")],
        "DIFF",
    ),
    "implicit-init-subclass-plain": pl(
        "class A:\n    def __init_subclass__(cls):\n        pass\n",
        [C, Want("method", "A.__init_subclass__")],
        "DIFF",
    ),
}

PLANTS: dict[str, Plant] = {
    **SHAPES,
    **BOUND,
    **DECORATED,
    **CLASSES,
    **MEMBERS,
    **REVIEW,
}
