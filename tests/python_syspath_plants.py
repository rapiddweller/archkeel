# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the `sys.path.append` rule (AD-538, #880).

Each plant is the tree of the project of `test_cli_native_python_imports` (scan root `app`,
namespace `app`) with extra files, and the source of `app/client.py`, which writes to `sys.path`.
The control is the form of K-python-realworld: `append` of the repository root. Every other plant
keeps the gap `import_system_change`. `source_note` says what Python does (observed with Python
3.12 by the proof review; `python3` truth runs are in the review directory of the owner).
"""

from __future__ import annotations

from typing import NamedTuple

HEAD = "import pathlib\nimport sys\n\n"
WRITE = "sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))\n"
CONTROL = HEAD + WRITE


class Plant(NamedTuple):
    name: str
    client: str
    files: dict[str, str] = {}
    roots: str = '["app"]'
    note: str = ""
    # Links of the repository root: (name, target).
    links: tuple[tuple[str, str], ...] = ()


def plants() -> list[Plant]:
    importer = {"app/service.py": "import colorsys\nimport docs\nimport x\n"}
    plants = [
        # R1: insert at any index.
        Plant("insert at 0", HEAD + WRITE.replace("append(", "insert(0, "), note="CE9, CE11"),
        Plant("insert at 3", HEAD + WRITE.replace("append(", "insert(3, "), note="CE9, CE11"),
        # R2 and R3: the namespace entry.
        Plant(
            "relative import through a namespace portion",
            HEAD + WRITE.replace("parents[1]", "parents[2]") + "from . import extra\n",
            {"app/extra.py": "", "src/app/extra.py": "", "src/app/__init__.py": ""},
            '["src/app"]',
            "CE1",
        ),
        Plant(
            "another app beside the scan root",
            HEAD + WRITE.replace("parents[1]", "parents[2]"),
            {"app/__init__.py": "", "app/client.py": "", "src/app/__init__.py": ""},
            '["src/app"]',
            "CE2",
        ),
        Plant("app.py beside app/", CONTROL, {"app.py": ""}, note="CE3"),
        Plant("APP.py beside app/", CONTROL, {"APP.py": ""}, note="CE3, case"),
        Plant("app/ without __init__.py", CONTROL, {"app/__init__.py": None}, note="CE3"),
    ]
    plants += [
        Plant(
            "namespace entry that no import names",
            HEAD + WRITE.replace("parents[1]", "parents[2]"),
            {"app/__init__.py": ""},
            '["src/app"]',
            "R2",
        ),
        Plant("dangling link in the directory", CONTROL, links=(("gone", "nowhere"),)),
        Plant("link out of the snapshot in the directory", CONTROL, links=(("out", "/usr"),)),
    ]
    # R4: the module-like entries.
    for entry in [
        "x.so",
        "x.abi3.so",
        "x.cpython-312-darwin.so",
        "x.pyc",
        "x.pyd",
        "X/m.py",
        "x/m.py",
    ]:
        plants.append(
            Plant(f"import x against {entry}", CONTROL, {**importer, entry: ""}, note="CE4, CE10")
        )
    plants += [
        Plant(
            "literal import call",
            CONTROL,
            {
                "app/service.py": "import importlib\nm = importlib.import_module('docs.x')\n",
                "docs/x.py": "",
            },
        ),
        Plant(
            "import in a function",
            CONTROL,
            {"app/service.py": "def go():\n    import docs\n", "docs/__init__.py": ""},
        ),
    ]
    # R5: the expression and the binders.
    one = WRITE.rstrip("\n")
    forms = {
        "no resolve": one.replace(".resolve()", ""),
        "parents[-1]": one.replace("parents[1]", "parents[-1]"),
        "computed index": "n = 1\n" + one.replace("parents[1]", "parents[n]"),
        "parents[2] leaves the snapshot": one.replace("parents[1]", "parents[2]"),
        "no str": one.replace("str(", "(").replace("))\n", ")\n")
        if False
        else "sys.path.append(pathlib.Path(__file__).resolve().parents[1])",
        "__file__ rebound": "__file__ = '/x/y.py'\n" + one,
        "str shadowed": "str = repr\n" + one,
        "star import": "from os.path import *\n" + one,
        "in a function": "def go():\n    " + one,
        "in a class": "class C:\n    " + one,
        "in an if": "if True:\n    " + one,
        "extend": "sys.path.extend([str(pathlib.Path(__file__).resolve().parents[1])])",
        "plus equals": "sys.path += [str(pathlib.Path(__file__).resolve().parents[1])]",
    }
    for name, form in forms.items():
        plants.append(Plant(f"R5 {name}", HEAD + form + "\n", note="CE7"))
    plants.append(Plant("two writes, one refused", CONTROL + "sys.path.insert(0, '/x')\n"))
    return plants
