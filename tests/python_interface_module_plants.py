# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The `interface_boundary` plants of a use through a Python module object (#1415, AD-708)."""

from __future__ import annotations

from python_interface_plants import DEFINES, LIB, Plant


def module_objects() -> list[Plant]:
    """#1415, AD-708: a use of a name through a module binding is the import of that name.

    Python 3.12 runs each consumer: `app.lib._priv.secret.__module__ == "app.lib._priv"`. 4.0.1
    judges imports only and says PASS; the core judges each use, or says UNKNOWN when the module
    object escapes and its names are not read.
    """
    p = Plant
    private = {LIB: "from app.lib import _priv\n", "src/app/lib/_priv.py": "def secret(): pass\n"}
    why = "AD-708: a use through a module object is the import of its name"
    return [
        p(
            "private submodule used through the public module object",
            "import app.lib\napp.lib._priv.secret()\n",
            ("app.lib",),
            private,
            core=("FAIL",),
            truth="FAIL",
            why=why,
        ),
        p(
            "private submodule used through an alias of the module",
            "import app.lib as lib\nlib._priv.secret()\n",
            ("app.lib",),
            private,
            core=("FAIL",),
            truth="FAIL",
            why=why,
        ),
        p(
            "private submodule used through a package binding",
            "from app import lib\nlib._priv.secret()\n",
            ("app.lib",),
            private,
            core=("FAIL",),
            truth="FAIL",
            why=why,
        ),
        p(
            "private name used through the module object",
            "import app.lib\nprint(app.lib._x)\n",
            ("app.lib",),
            {LIB: "_x = 1\n"},
            core=("FAIL",),
            truth="FAIL",
            why=why,
        ),
        p(
            "public name used through the module object",
            "import app.lib\napp.lib.f()\n",
            ("app.lib",),
            {LIB: DEFINES},
        ),
        p(
            "module object that escapes",
            "import app.lib\nx = app.lib\nx._priv.secret()\n",
            ("app.lib",),
            private,
            core=("UNKNOWN",),
            truth="FAIL",
            why="AD-708: the module object escapes, so the names that it gives are not read",
        ),
    ]
