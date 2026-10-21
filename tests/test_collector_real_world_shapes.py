# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Ordinary Python shapes from a large real repository must not abort collection (#646)."""

from pathlib import Path

import pytest
from test_analyzer import _observe

KINDS = "from enum import StrEnum\nclass Kind(StrEnum):\n    A = 'a'\n    B = 'b'\n"
CLIENT = (
    "from typing import Protocol\n\n\n"
    "class Client(Protocol):\n    def count(self, name: str) -> int: ...\n"
)
CASES = {
    "getattr-result-called": {
        "sample/client.py": CLIENT,
        "sample/mod.py": (
            "from sample.client import Client\n\n\n"
            "def total(client: Client, name: str) -> object:\n"
            "    return getattr(client, 'count')(name)\n"
        ),
    },
    "getattr-default-called-under-future-annotations": {
        "sample/client.py": CLIENT,
        "sample/mod.py": (
            "from __future__ import annotations\n\nfrom typing import Any\n\n"
            "from sample.client import Client\n\n\n"
            "def total(client: Client, name: str) -> list[Any]:\n"
            "    try:\n"
            "        count = int(getattr(client, 'count', lambda c: 0)(str(name)) or 0)\n"
            "    except Exception:\n        count = 0\n    return [count]\n"
        ),
    },
    "class-annotation-three-branches": {
        "sample/mod.py": (
            "class Store:\n    _config: dict[str, int]\n\n"
            "    def __init__(self, kind: str) -> None:\n"
            "        if kind == 'a':\n            self._config = {'a': 1}\n"
            "        elif kind == 'b':\n            self._config = {'b': 2}\n"
            "        else:\n            self._config = {'c': 3}\n"
        )
    },
    "class-default-annotated-self-write": {
        "sample/mod.py": (
            "class Exporter:\n    _cli: object | None = None\n\n"
            "    def __init__(self, shared: bool) -> None:\n"
            "        if shared:\n            self._cli: object = Exporter._cli\n"
            "        else:\n            self._cli = Exporter._cli\n"
        )
    },
    "self-attr-two-branches": {
        "sample/mod.py": (
            "class Store:\n    def __init__(self, cloud: bool) -> None:\n"
            "        if cloud:\n            self._config = {'a': 1}\n"
            "        else:\n            self._config = {'b': 2}\n"
        )
    },
    "stdlib-alias-value": {"sample/mod.py": "import time as _time\nHELPERS = {'time': _time}\n"},
    "reexport-value": {
        "sample/impl.py": "def helper() -> int:\n    return 1\n",
        "sample/api.py": "from sample.impl import helper\n__all__ = ['helper']\n",
        "sample/mod.py": "from sample.api import helper\nHELPERS = {'helper': helper}\n",
    },
    "reexport-spread": {
        "sample/impl.py": "HELPERS = {'a': 1}\n",
        "sample/api.py": "from sample.impl import HELPERS\n__all__ = ['HELPERS']\n",
        "sample/mod.py": "from sample.api import HELPERS\nALL = {**HELPERS, 'b': 2}\n",
    },
    "enum-in-multiline-call-value": {
        "sample/kinds.py": KINDS,
        "sample/mod.py": (
            "from dataclasses import dataclass\nfrom sample.kinds import Kind\n\n"
            "@dataclass(frozen=True)\nclass Rule:\n    name: str\n    kind: Kind\n\n"
            "RULES = {\n    'a': Rule(\n        'a',\n        Kind.A,\n    ),\n}\n"
        ),
    },
    "local-import-call": {
        "sample/mod.py": (
            "def draw(seed: int) -> float:\n    from random import Random\n"
            "    rng = Random(seed)\n    return rng.random()\n"
        )
    },
    "local-import-module-call": {
        "sample/mod.py": (
            "def draw(seed: int) -> float:\n    import random\n"
            "    return random.Random(seed).random()\n"
        )
    },
    "chained-random-choices": {
        "sample/mod.py": (
            "def pick(seed: int) -> list[int]:\n    from random import Random\n"
            "    return Random(seed).choices(range(3), k=2)\n"
        )
    },
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_real_world_shape_keeps_the_collection_valid(tmp_path: Path, name: str) -> None:
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("")
    for path, text in CASES[name].items():
        (tmp_path / path).write_text(text)
    result = _observe(tmp_path)
    assert result.observation is not None, [item.unknown_claim for item in result.diagnostics]
