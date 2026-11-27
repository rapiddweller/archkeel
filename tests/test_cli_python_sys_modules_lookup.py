# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2197: a `sys.modules.get("text")` that is only compared by identity or tested for truth is no
import-system change. A write, a delete, an escape or any other use keeps every rule UNKNOWN.

Each plant that holds runs with Python in the unit tests of the collector. Here the verdict of a
whole project shows the effect on the rules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_cli_native_python_imports import verdict
from test_cli_python_outside_withheld import statuses, tree

HEAD = "import sys\n\n\n"

# The lookup is read and its value reaches no code.
READ = {
    "issue": HEAD + 'def is_math(value: object) -> bool:\n    found = sys.modules.get("math")\n'
    "    return found is not None and value is found\n",
    "inline identity": HEAD
    + 'def f(v: object) -> bool:\n    return sys.modules.get("math") is v\n',
    "truth test": HEAD
    + 'def f() -> int:\n    if sys.modules.get("math"):\n        return 1\n    return 0\n',
    "bound truth test": HEAD
    + 'def f() -> int:\n    m = sys.modules.get("math")\n    if not m:\n        return 0\n'
    "    return 1\n",
}

# Each of these keeps the hold: a write, a delete, an escape or a use that can run code.
HELD = {
    "item write": HEAD + 'sys.modules["x"] = object()\n',
    "item delete": HEAD + 'del sys.modules["x"]\n',
    "setdefault": HEAD + 'sys.modules.setdefault("x", object())\n',
    "pop": HEAD + 'sys.modules.pop("x")\n',
    "update": HEAD + "sys.modules.update({})\n",
    "return": HEAD + 'def f() -> object:\n    return sys.modules.get("x")\n',
    "bound and returned": HEAD + 'def f() -> object:\n    m = sys.modules.get("x")\n    return m\n',
    "computed key": HEAD + "def f(name: str) -> bool:\n    return sys.modules.get(name) is None\n",
    "attribute": HEAD + 'def f() -> object:\n    return sys.modules.get("x").attr\n',
    "bound attribute": HEAD
    + 'def f() -> object:\n    m = sys.modules.get("x")\n    return m.attr\n',
    "equality": HEAD + 'def f(o: object) -> bool:\n    return sys.modules.get("x") == o\n',
    "bound equality": HEAD
    + 'def f(o: object) -> bool:\n    m = sys.modules.get("x")\n    return m == o\n',
    "passed on": HEAD
    + 'def f(g: object) -> None:\n    m = sys.modules.get("x")\n    g(m)\n    assert m is None\n',
    "module level name": HEAD + 'm = sys.modules.get("x")\nok = m is None\n',
}


def probe(release_core: Path, root: Path, source: str) -> dict[str, str]:
    tree(root, None)
    client = root / "src/app/client.py"
    client.write_text(client.read_text() + "\n\n" + source)
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["add", "-A"], [*who, "commit", "-qm", "probe"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return statuses(verdict(release_core, root))


@pytest.mark.parametrize("name", sorted(READ))
def test_a_lookup_that_is_only_compared_or_tested_holds_nothing(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found = probe(release_core, tmp_path, READ[name])
    assert set(found.values()) == {"PASS"}, found


@pytest.mark.parametrize("name", sorted(HELD))
def test_each_other_use_of_the_table_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found = probe(release_core, tmp_path, HELD[name])
    assert "UNKNOWN" in found.values(), found
