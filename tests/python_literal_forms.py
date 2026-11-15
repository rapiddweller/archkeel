# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The forms of a Python import call for the table "4.0.1 against the core" (AD-520, #880).

Each form is the source of `app/a/one.py`, which declares the edge `one -> t` of the UML target.
`proven` is true when the call is one of the two proven literal forms of AD-472. `four` is the
row of the UML target of release 4.0.1 (`rule_assessments` of one `validate` on the same tree; it
reads statements only, so it never sees the call). `core` is the row of the core: FAIL for a
proven literal call (the edge is a call, not a statement), UNKNOWN for each form that the survey
does not prove.
"""

from __future__ import annotations

from typing import NamedTuple


class Form(NamedTuple):
    name: str
    source: str
    proven: bool
    four: str = "FAIL"

    @property
    def core(self) -> str:
        return "FAIL" if self.proven else "UNKNOWN"


T = "app.b.t"
FORMS = [
    Form("import_module literal", f"import importlib\nt = importlib.import_module('{T}')\n", True),
    Form("__import__ literal", f"t = __import__('{T}')\n", True),
    Form(
        "import_module literal in a function",
        f"import importlib\n\n\ndef go():\n    return importlib.import_module('{T}')\n",
        True,
    ),
    Form(
        "import_module aliased module",
        f"import importlib as il\nt = il.import_module('{T}')\n",
        False,
    ),
    Form(
        "import_module from importlib",
        f"from importlib import import_module\nt = import_module('{T}')\n",
        False,
    ),
    Form(
        "variable argument",
        f"import importlib\nname = '{T}'\nt = importlib.import_module(name)\n",
        False,
    ),
    Form(
        "f-string argument",
        "import importlib\nx = 't'\nt = importlib.import_module(f'app.b.{x}')\n",
        False,
    ),
    Form(
        "concatenated argument",
        "import importlib\nt = importlib.import_module('app.b' + '.t')\n",
        False,
    ),
    Form(
        "relative name with package",
        "import importlib\nt = importlib.import_module('.b.t', package='app')\n",
        False,
    ),
    Form(
        "package as second argument",
        f"import importlib\nt = importlib.import_module('{T}', 'app')\n",
        False,
    ),
    Form("keyword argument", f"import importlib\nt = importlib.import_module(name='{T}')\n", False),
    Form(
        "importlib rebound",
        f"import importlib\nimportlib = object()\nt = importlib.import_module('{T}')\n",
        False,
    ),
    Form("__import__ shadowed", f"__import__ = print\nt = __import__('{T}')\n", False),
    Form(
        "getattr of the callee",
        f"import importlib\nt = getattr(importlib, 'import_module')('{T}')\n",
        False,
    ),
    Form(
        "callee stored in a name",
        f"import importlib\nload = importlib.import_module\nt = load('{T}')\n",
        False,
    ),
    Form(
        "globals in the module",
        f"import importlib\nglobals()\nt = importlib.import_module('{T}')\n",
        False,
    ),
]
