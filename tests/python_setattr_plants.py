# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of AD-530, decision 5: a `setattr` or `delattr` that can write a module of the scan.

A write on a local whose one binding is `copy.copy` or `copy.deepcopy` of one argument writes no
module (`copy_local.rs`): CPython refuses to copy a module, and only a hook can give one. Each other
first argument keeps the gap. `truth` of a plant runs the writer, so a plant that can write the
package shows `type:int` for `sub` in `client`.
"""

from __future__ import annotations

from python_reexport_plants import IMPORT_SUB, PLANTS, Plant, tree

# `make` binds `new` by `bind` and writes `sub` on it; `{copier}` imports the copier.
MAKE = "{copier}def make(obj, value, box=None):\n    {bind}\n    setattr(new, 'sub', value)\n"
COPY = "from copy import copy\n"
BOX = "class Box:\n    pass\n"
CALL_WITH_A_BOX = "from app.pkg import make\n" + BOX + "make(Box(), 1)\n"


def make(bind: str, copier: str = COPY) -> str:
    return MAKE.format(copier=copier, bind=bind)


SETATTR: dict[str, Plant] = {
    "setattr-on-a-copied-local": Plant(
        tree(IMPORT_SUB, pkg=make("new = copy(obj)"), writer=CALL_WITH_A_BOX),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    "setattr-on-a-deepcopy-of-the-copy-module": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = copy.deepcopy(obj)", "import copy\n"),
            writer=CALL_WITH_A_BOX,
        ),
        "PASS",
        "UNKNOWN",
        "PASS",
        "app.pkg.sub",
    ),
    # CPython refuses to copy the package; the hand-over itself is an escape of the package.
    "copy-of-the-package-raises": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = copy(obj)"),
            writer=(
                "import app.pkg\ntry:\n    app.pkg.make(app.pkg, 1)\nexcept TypeError:\n    pass\n"
            ),
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub",
    ),
    "setattr-on-a-copy-with-a-copy-hook": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = copy(obj)")
            + "class Hook:\n    def __copy__(self):\n        import sys\n"
            + "        return sys.modules[__name__]\n",
            writer="from app.pkg import make, Hook\nmake(Hook(), 1)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    "setattr-on-a-deepcopy-with-a-memo": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = deepcopy(obj, box)", "from copy import deepcopy\n"),
            writer="import app.pkg\n" + BOX + "b = Box()\napp.pkg.make(b, 1, {id(b): app.pkg})\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    "setattr-on-an-attribute-of-a-copy": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = copy(obj).inner"),
            writer="import app.pkg\n" + BOX + "b = Box()\nb.inner = app.pkg\napp.pkg.make(b, 1)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    "setattr-on-a-rebound-copy": Plant(
        tree(
            IMPORT_SUB,
            pkg=make("new = copy(box)\n    new = obj"),
            writer="import app.pkg\n" + BOX + "app.pkg.make(app.pkg, 1, Box())\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    # A scanned caller can hand the package to a parameter: the gap stays.
    "setattr-on-a-parameter": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make(obj, value):\n    setattr(obj, 'sub', value)\n",
            writer="import app.pkg\napp.pkg.make(app.pkg, 1)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
        "app.pkg.sub|type:int",
    ),
    "delattr-on-an-attribute-of-a-parameter": Plant(
        tree(
            IMPORT_SUB,
            pkg="def make(obj):\n    delattr(obj.inner, 'x')\n",
            writer="from app.pkg import make\nprint(make)\n",
        ),
        "PASS",
        "UNKNOWN",
        "UNKNOWN",
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
}

ALL: dict[str, Plant] = {**PLANTS, **SETATTR}
