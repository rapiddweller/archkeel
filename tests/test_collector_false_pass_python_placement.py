# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1713: a call that can create a class never passes `symbol_placement`.

Consumer: `archkeel validate`. Rule `PLACEMENT` allows classes in `app.service` only. In each plant
`app.client` holds no class statement, but `make()` creates a class when it runs: Python 3.12
returns a class from `make()`. Its place is not proven, so the rule is UNKNOWN, and the reason
names the file, the line and the callee.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_cli_native_python_imports import RULE, project, rows, verdict

# name: (src/app/client.py, the callee that the reason names)
PLANTS = {
    "enum": ("from enum import Enum\ndef make():\n    return Enum('Color', 'RED')\n", "enum.Enum"),
    "namedtuple": (
        "from collections import namedtuple\ndef make():\n    return namedtuple('P', 'x')\n",
        "collections.namedtuple",
    ),
    "build-class": (
        "def make():\n    return __build_class__(lambda: None, 'Hidden')\n",
        "builtins.__build_class__",
    ),
    "make-dataclass": (
        "from dataclasses import make_dataclass\n"
        "def make():\n    return make_dataclass('H', ['x'])\n",
        "dataclasses.make_dataclass",
    ),
    "typeddict": (
        "from typing import TypedDict\ndef make():\n    return TypedDict('H', {'x': int})\n",
        "typing.TypedDict",
    ),
    "new-class": (
        "import types\ndef make():\n    return types.new_class('H')\n",
        "types.new_class",
    ),
    "metaclass": (
        "from abc import ABCMeta\ndef make():\n    return ABCMeta('H', (), {})\n",
        "abc.ABCMeta",
    ),
    "module-alias": (
        "import enum as e\ndef make():\n    return e.IntEnum('N', 'A')\n",
        "enum.IntEnum",
    ),
    "type-three": ("def make():\n    return type('Hidden', (), {})\n", "builtins.type"),
}
# A call result that the module uses as a class (the callee is unknown): no truth of its own.
USED = {
    "result-called": "def make(factory):\n    made = factory()\n    return made()\n",
    "result-tested": "def check(x, factory):\n    return isinstance(x, factory())\n",
    "metaclass-shape": "def make(meta):\n    return meta('H', (object,), {})\n",
}
QUIET = {
    "plain": "def test():\n    return 1\n",
    "calls": "def run(items, cb):\n    total = len(items) + max(items)\n    return cb(total)\n",
    "type-of-value": "def kind(x):\n    return type(x)\n",
}


def _verdict(release_core: Path, tmp_path: Path, client: str) -> dict:
    placement = {
        **RULE,
        "id": "PLACEMENT",
        "kind": "symbol_placement",
        "source": "app",
        "class_kinds": ["class", "dataclass"],
        "allowed_sources": ["app.service"],
    }
    files = {
        "src/app/__init__.py": "",
        "src/app/client.py": client,
        "src/app/service.py": "class Allowed: pass\n",
    }
    return verdict(release_core, project(tmp_path, files, contract_rules=[placement]))


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_class_factory_in_a_function_names_its_site(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    client, callee = PLANTS[name]
    if shutil.which("python3.12"):
        code = f"{client}print(isinstance(make(), type))"
        done = subprocess.run(["python3.12", "-I", "-c", code], capture_output=True, text=True)
        assert done.stdout.strip() == "True", done.stderr
    result = _verdict(release_core, tmp_path, client)

    assert rows(result)["PLACEMENT"] == "UNKNOWN", result["frame"]
    reason = result["frame"]["explained"]["PLACEMENT"]
    line = next(n for n, text in enumerate(client.splitlines(), 1) if "return" in text)
    assert f"a call can create a class at src/app/client.py:{line} ({callee})" in reason, reason


@pytest.mark.parametrize("name", sorted(USED))
def test_a_call_result_used_as_a_class_is_unproven(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    result = _verdict(release_core, tmp_path, USED[name])

    assert rows(result)["PLACEMENT"] == "UNKNOWN", result["frame"]
    assert (
        "a call can create a class at src/app/client.py"
        in result["frame"]["explained"]["PLACEMENT"]
    )


@pytest.mark.parametrize("name", sorted(QUIET))
def test_a_function_that_creates_no_class_keeps_the_receipt(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    result = _verdict(release_core, tmp_path, QUIET[name])
    expected = "UNKNOWN" if name == "type-of-value" else "PASS"
    assert rows(result)["PLACEMENT"] == expected, result["frame"]
