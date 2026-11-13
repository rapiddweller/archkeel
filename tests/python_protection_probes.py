# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generated public syntax probes for every AD-410 proof branch."""

from __future__ import annotations

BASES = (
    "class C: pass\n",
    "from typing import TypedDict\nclass C(TypedDict):\n x: int\n",
    "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass C:\n x: 'int'\n",
    "from typing import Generic, TypeVar\nT = TypeVar('T')\nclass C(Generic[T]): pass\n",
    "from typing import overload\n@overload\ndef f(x: int): ...\n"
    "@overload\ndef f(x: str): pass\ndef f(x): return x\n",
    "class C:\n @property\n def x(self): pass\n @x.setter\n def x(self, x): self.x = x\n",
    "class C:\n x: int\ndef f(x: C) -> C:\n return C()\n",
    "class C: pass\nAlias = list[C | None]\nf = lambda: C\n",
    "import os.path as p\nfrom os.path import join\nx = p\nx.attr = 1\n",
    "from typing import Mapping\nx: Mapping[str, int]\n",
    "class C:\n x = 1\n y = x + 2\n z = other + 2\n",
    "from __future__ import annotations\nclass C:\n def f(self, x: C=1): pass\n",
    "class C: pass\nC.x = 1\nsetattr(C, 'x', 1)\ndef f(x=C): pass\n",
    "class C(Base[Other]):\n def f(self): pass\n",
    "from typing import TypedDict as TD\nclass C(TD, total=False):\n x: 'int'\n",
    "class C: pass\nclass D(C): pass\nvalue = C\nconsume(value)\n",
)

BRANCHES = (
    "class C: pass\nclass C: pass\n",
    "from typing import TypedDict\nclass C(TypedDict, total=1): pass\n",
    "from typing import TypedDict\n@deco\nclass C(TypedDict): pass\n",
    "from typing import TypedDict\nclass C(TypedDict):\n x = 1\n",
    "from typing import TypedDict\nclass C(TypedDict):\n def f(self): pass\n",
    "from typing import TypedDict\nclass C(TypedDict):\n x: Unknown\n",
    "from typing import TypedDict\nclass C(TypedDict):\n x: 'Unknown'\n",
    "from typing import TypedDict\nconsume(TypedDict)\nclass C(TypedDict): pass\n",
    "import typing\nclass C(typing.TypedDict):\n x: bytes\n",
    "from typing_extensions import TypedDict\nclass C(TypedDict):\n x: object\n",
    "from typing import TypedDict\nclass C(TypedDict, total=True, metaclass=M): pass\n",
    "from typing import TypedDict\nclass C(TypedDict, Other): pass\n",
    "from dataclasses import dataclass\n@dataclass\nclass C: pass\n",
    "import dataclasses\n@dataclasses.dataclass\nclass C: pass\n",
    "from dataclasses import dataclass\n@dataclass(1)\nclass C: pass\n",
    "from dataclasses import dataclass\n@dataclass(other=True)\nclass C: pass\n",
    "from dataclasses import dataclass\n@dataclass(frozen=1)\nclass C: pass\n",
    "from dataclasses import dataclass\n@dataclass(**kw)\nclass C: pass\n",
    "from dataclasses import dataclass\n@dataclass\nclass C(Base): pass\n",
    "from dataclasses import dataclass\n@dataclass\nclass C:\n x = factory()\n",
    "class C(A, B): pass\nclass D(object, C): pass\n",
    "import abc\nclass C(abc.ABC, Base): pass\n",
    "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
    "class Base(Generic[T]): pass\nclass C(Base[T]): pass\n",
    "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
    "class Base(Generic[T]):\n __x__ = 1\nclass C(Base[T]): pass\n",
    "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
    "class Base(Generic[T]): pass\nclass C(Base[T]): pass\nconsume(Base)\n",
    "from typing import Generic\nclass C(Generic[int]): pass\n",
    "class C(Missing[int]): pass\n",
    "def outer():\n class C: pass\n f = lambda: C\n return f\n",
    "f = lambda: 1\nx: int = lambda: 2\n(x := lambda: 3)\n",
    "class C:\n @property\n def x(self): pass\n @x.setter\n"
    " def x(self, x):\n  global other\n  return [x for x in x]\n",
    "class C: pass\nf: Callable[[C], C]\nx: unknown[effect(C)]\n",
    "class C: pass\nx: list[C]\ny: pkg.Name\nz: C | None\n",
    "class C: pass\nx: list[C | str]\ny: list[C | None]\nz: C | str\n",
    "class C: pass\nx = C\ny = x\nconsume(y)\n",
    "def f(): pass\nconsume(f)\nimport os\n",
    "from builtins import globals as g\ng()\nclass C: pass\n",
    "locals()\nclass C: pass\n",
    "class C:\n exec(code)\n",
    "class C:\n __module__ = 'm'\n",
    "class C: pass\nC.__x__ = value\nsetattr(C, '__x__', value)\n",
    "class C: pass\nsetattr(C, 'x', factory())\n",
    "class C: pass\ndef f(x: C=C()) -> C: return C()\n",
    "class C: pass\ndef f(C): return C()\n",
    "class C: pass\ndef f():\n C = other\n return C()\n",
    "class C: pass\ndef f():\n if ok: return C()\n",
    "class C: pass\n@deco\ndef f(): return C()\n",
    "class C:\n x: int\nasync def f(*x: str, **kw: bool) -> C: return C()\n",
    "class C:\n x: Unknown\ndef f(): return C()\n",
    "class C:\n x: 'Unknown'\ndef f() -> C: return C(1)\n",
    "class C:\n x: list\ndef f(): return C()\n",
    "def f(): return C()\nclass C: pass\n",
    "class C:\n x = 1\n y = (a := 2)\n z = lambda x=call(): x\n",
    "x = ['A | None', 'pkg.Name', 'list[A]', 'A + B', 'A;', '(', 'None', 'A | B', '']\n",
    "from typing import overload, TypeVar\nT = TypeVar('T')\n@overload\n"
    "def f(x: T): ...\n@overload\ndef f(x: str): ...\ndef f(x): return x\n",
    "from typing import overload\n@overload\ndef f(x: int): ...\n"
    "other = 1\n@overload\ndef f(x: str): ...\ndef f(x): return x\n",
    "from typing import overload\n@overload\nasync def f(x: int): ...\n"
    "@overload\ndef f(x: str): ...\ndef f(x): return x\n",
    "from typing import overload\n@overload\ndef f(x: int): return 1\n"
    "@overload\ndef f(x: str): ...\ndef f(x): return x\n",
    "from typing import overload\n@overload()\ndef f(x: int): ...\n"
    "@overload\ndef f(x: str): ...\ndef f(x): return x\n",
    "from typing import overload\n@overload\ndef f(x: int): ...\n"
    "@overload\ndef f(x: str): ...\n@deco\ndef f(x): return x\n",
    "from typing import overload\n@overload\ndef f(x: int): ...\n"
    "@overload\ndef f(x: str): ...\ndef f(x): return x\nconsume(f)\n",
    "from typing import overload\n@overload\ndef f(x: int): ...\n"
    "@overload\ndef f(x: str): ...\ndef f(x): return x\nglobals().update(x=1)\n",
    "import os\nfrom os import path\nother = os\nother.attr = 1\n",
    "def f(): pass\nf.__globals__['x'] = 1\n",
    "class C:\n @property\n def x(self): pass\n @x.setter\n def x(self, x): return x\n",
    "x = ['\\x1cA | None\\x1f', ' None ', '((A | B))', 'A # comment', 'A; B']\n",
    "x = f'A{value}None'\ny = f'{value:A}'\n",
    "if yes:\n x: A\nelif other:\n consume(A)\nwhile A if test else B: pass\n",
    "import os\nos.path.join('a', 'b')\nos.__dict__.update(x=1)\n",
    "x: dict[str, int]\ny: tuple[[A, B], C]\n",
    BASES[4] + "def outer():\n global other\n other = 1\n",
)


def _combine(a: str, b: str) -> str:
    future = "from __future__ import annotations\n"
    return (future if future in a + b else "") + (a + b).replace(future, "")


PROBES = tuple(_combine(a, b) for a in BASES for b in BASES) + BRANCHES
