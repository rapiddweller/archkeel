# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of AD-530: a re-export that nothing can rewrite, and a read that imports nothing.

Each plant is a tiny Python tree. `client.py` is the module that the rule `FORBID` reads: it must
not import `app.pkg.sub`. A plant gives its files, the row of release 4.0.1, and the row of the
core (AD-530). `TRUTH` says what CPython does with the tree.
"""

from __future__ import annotations

from typing import NamedTuple

LIB = "def f(): pass\n"
SUB = "VALUE = 1\n"
PKG = "src/app/pkg/__init__.py"
CLIENT = "src/app/client.py"
SUBPATH = "src/app/pkg/sub.py"
WRITER = "src/app/writer.py"
IMPORT_SUB = "from app.pkg import sub\n"


class Plant(NamedTuple):
    files: dict[str, str]
    # The row of release 4.0.1 for FORBID, and the row of the core before and after AD-530.
    release: str
    before: str
    after: str
    # What CPython does: `module` is the name of the object that `sub` is in `client`, or `-`.
    truth: str


def tree(client: str, pkg: str = "", **more: str) -> dict[str, str]:
    base = {
        PKG: pkg,
        SUBPATH: SUB,
        CLIENT: client,
        "src/app/service.py": "VALUE = 1\n",
    }
    return {**base, **{f"src/app/{name}.py": text for name, text in more.items()}}


# Group A: `from app.pkg import sub`, where `sub` is a submodule and maybe also an attribute.
REEXPORT: dict[str, Plant] = {
    "plain-submodule": Plant(
        tree(IMPORT_SUB),
        "PASS",
        "PASS",
        "PASS",
        "app.pkg.sub",
    ),
    "init-imports-the-submodule": Plant(
        tree(IMPORT_SUB, pkg="from . import sub\n"),
        "PASS",
        "PASS",
        "PASS",
        "app.pkg.sub",
    ),
    "init-rebinds-after-the-import": Plant(
        tree(IMPORT_SUB, pkg="from . import sub\nsub = 1\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "init-has-getattr": Plant(
        tree(IMPORT_SUB, pkg="def __getattr__(name):\n    return 1\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "attribute-only": Plant(
        tree("from app.pkg import helper\n", pkg="def helper(): pass\n"),
        "PASS",
        "PASS",
        "PASS",
        "-",
    ),
    "init-deletes-the-name": Plant(
        tree(IMPORT_SUB, pkg="from . import sub\ndel sub\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "init-imports-conditionally": Plant(
        tree(IMPORT_SUB, pkg="try:\n    from . import sub\nexcept ImportError:\n    sub = None\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "init-binds-under-type-checking": Plant(
        tree(
            IMPORT_SUB,
            pkg="from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    sub = 1\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    # A real write into the package: the survey must keep the gap.
    "another-module-writes-the-package": Plant(
        tree(IMPORT_SUB, writer="import app.pkg as p\nsetattr(p, 'sub', 1)\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    # The shape of FastAPI: another module passes a constant of the package as a value.
    "constant-of-the-package-is-no-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="VERSION = '1'\n",
            writer="from app.pkg import VERSION\nprint(VERSION)\n",
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "tuple-of-the-package-is-no-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="PAIR = (1, 2)\nALL = tuple(PAIR)\n",
            writer="from app.pkg import ALL\nprint(ALL)\n",
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "name-of-an-external-origin-is-no-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="from json import dumps as dumps\nRENAMED = dumps\n",
            writer="from app.pkg import RENAMED\nprint(RENAMED)\n",
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "call-result-of-the-package-stays-an-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make():\n    return 1\nFACTORY = make()\n",
            writer="from app.pkg import FACTORY\nprint(FACTORY)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "builtin-name-rebound-stays-an-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="def tuple(x):\n    return x\nALL = tuple(1)\n",
            writer="from app.pkg import ALL\nprint(ALL)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "name-of-a-module-of-the-scan-stays-an-escape": Plant(
        tree(
            IMPORT_SUB,
            pkg="import app.service as ALIAS\n",
            writer="from app.pkg import ALIAS\nALIAS.VALUE = 2\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    # AD-530 attacks on the proof: each rebinding of the name or of its origin keeps the gap.
    "init-star-import-brings-the-name": Plant(
        tree(IMPORT_SUB, pkg="from ..other import *\n", other="sub = 1\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "init-writes-globals": Plant(
        tree(IMPORT_SUB, pkg="globals()['sub'] = 1\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "inert-name-with-a-conditional-origin": Plant(
        tree(
            IMPORT_SUB,
            pkg="FLAG = True\nif FLAG:\n    BASE = 1\nCOPY = BASE\n",
            writer="from app.pkg import COPY\nprint(COPY)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "inert-name-whose-origin-is-rebound-to-a-module": Plant(
        tree(
            IMPORT_SUB,
            pkg="import app.service as MOD\nBASE = 1\nCOPY = BASE\nBASE = MOD\n",
            writer="from app.pkg import COPY\nprint(COPY)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "inert-name-of-a-star-import-of-the-package": Plant(
        tree(
            IMPORT_SUB,
            pkg="from external import *\nCOPY = BASE\n",
            writer="from app.pkg import COPY\nprint(COPY)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "inert-name-deleted-in-the-package": Plant(
        tree(
            IMPORT_SUB,
            pkg="BASE = 1\ndel BASE\nimport app.service as BASE\n",
            writer="from app.pkg import BASE\nBASE.VALUE = 2\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    # AD-530, decision 5: a `setattr` on a local object is no write to a module of the scan.
    "setattr-on-a-parameter": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make(obj, value):\n    setattr(obj, 'x', value)\n",
            writer="from app.pkg import make\nprint(make)\n",
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "delattr-on-an-attribute-of-a-parameter": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make(obj):\n    delattr(obj.inner, 'x')\n",
            writer="from app.pkg import make\nprint(make)\n",
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "setattr-on-a-global-name": Plant(
        tree(
            IMPORT_SUB,
            pkg="registry = object()\ndef make():\n    setattr(registry, 'x', 1)\n",
            writer="from app.pkg import make\nprint(make)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "setattr-on-a-call-result": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make(get):\n    setattr(get(), 'sub', 1)\n",
            writer="from app.pkg import make\nprint(make)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "monkeypatch-setattr-with-a-path-in-a-local": Plant(
        tree(
            IMPORT_SUB,
            pkg=(
                "def patch(monkeypatch):\n    path = 'app.pkg.sub'\n"
                "    monkeypatch.setattr(path, 1)\n"
            ),
            writer="from app.pkg import patch\nprint(patch)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "setattr-on-the-module-from-getmodule": Plant(
        tree(
            IMPORT_SUB,
            pkg=(
                "import inspect\ndef patch():\n"
                "    setattr(inspect.getmodule(patch), 'sub', 1)\npatch()\n"
            ),
            writer="from app.pkg import patch\nprint(patch)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "setattr-on-a-local-that-holds-the-getmodule-result": Plant(
        tree(
            IMPORT_SUB,
            pkg=(
                "import inspect\ndef patch():\n    me = inspect.getmodule(patch)\n"
                "    setattr(me, 'sub', 1)\npatch()\n"
            ),
            writer="from app.pkg import patch\nprint(patch)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "type:int",
    ),
    "frame-globals-write-at-import": Plant(
        tree(IMPORT_SUB, pkg="import sys\nsys._getframe().f_globals['sub'] = 1\n"),
        "PASS",
        "PASS",
        "UNKNOWN",
        "type:int",
    ),
}

# Group B: a read of the globals of a function, and the two other forms of the same gap.
GLOBALS: dict[str, Plant] = {
    "globals-read-with-a-literal-key": Plant(
        tree("def f(fn):\n    return getattr(fn, '__globals__', {}).get('__file__')\n"),
        "PASS",
        "UNKNOWN",
        "PASS",
        "-",
    ),
    "globals-in-a-local-passed-to-a-lookup": Plant(
        tree(
            "def look(g, key):\n    return g.get('__file__')\n"
            "def f(fn):\n    g = fn.__globals__\n    return look(g, 'x')\n"
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "-",
    ),
    "globals-passed-to-an-external-call": Plant(
        tree(
            "import typing\n"
            "def f(fn):\n    g = getattr(fn, '__globals__', {})\n"
            "    return typing.get_type_hints(fn, g)\n"
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "-",
    ),
    "globals-given-to-eval": Plant(
        tree("def f(fn):\n    g = fn.__globals__\n    return eval('1', g)\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-written": Plant(
        tree("def f(fn):\n    fn.__globals__['x'] = 1\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-returned": Plant(
        tree("def f(fn):\n    return fn.__globals__\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-builtins-key": Plant(
        tree("def f(fn):\n    return fn.__globals__.get('__builtins__')\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-computed-key": Plant(
        tree("def f(fn, key):\n    return fn.__globals__.get(key)\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-items": Plant(
        tree("def f(fn):\n    return list(fn.__globals__.items())\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-copied-into-a-name-written-twice": Plant(
        tree("def f(fn):\n    g = fn.__globals__\n    g = {}\n    return g.get('x')\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-passed-to-a-function-that-iterates": Plant(
        tree(
            "def walk(g):\n    return [k for k in g]\n"
            "def f(fn):\n    g = fn.__globals__\n    return walk(g)\n"
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "globals-passed-to-an-unknown-callee": Plant(
        tree("def f(fn, sink):\n    g = fn.__globals__\n    return sink.use(g)\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
}

# Group C: a local name that has the name of a door, and `getattr` with a literal attribute.
LOCAL: dict[str, Plant] = {
    "parameter-named-like-a-door-module": Plant(
        tree("def f(code):\n    return str(code)\n"),
        "PASS",
        "UNKNOWN",
        "PASS",
        "-",
    ),
    "the-door-module-itself": Plant(
        tree("import code\ndef f():\n    return code.interact\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "comprehension-variable-does-not-bind-outside": Plant(
        tree("def f(x):\n    y = [code for code in x]\n    return code.interact\n"),
        "PASS",
        "PASS",
        "PASS",
        "-",
    ),
    "literal-getattr-of-a-module-attribute": Plant(
        tree("import types\nUNION = getattr(types, 'UnionType', None)\n"),
        "PASS",
        "UNKNOWN",
        "PASS",
        "-",
    ),
    "literal-getattr-of-a-door": Plant(
        tree("import types\nMAKE = getattr(types, 'FunctionType')\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
    "computed-getattr-of-a-module": Plant(
        tree("import types\ndef f(name):\n    return getattr(types, name)\n"),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "-",
    ),
}

PLANTS: dict[str, Plant] = {**REEXPORT, **GLOBALS, **LOCAL}
