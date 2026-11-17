# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An empty function body is visible even when another form remains unread."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_cli_native_python_imports import rows
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def check():\n    return 1\n", "UNKNOWN"),
        ("def check():\n    pass\n", "FAIL"),
        ("def check():\n    ...\n", "FAIL"),
        ("def check():\n    'documentation'\n", "FAIL"),
        ("def check():\n    'documentation'\n    pass\n", "FAIL"),
        ("def check():\n    'documentation'\n    ...\n", "FAIL"),
        ("def check():\n    raise UnknownError\n", "UNKNOWN"),
        ("class P:\n    def check(self): ...\n", "FAIL"),
        (
            "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
            "class C(P):\n    pass\n",
            "UNKNOWN",
        ),
        ("from typing import Protocol as P\nclass C(P):\n    def check(self): ...\n", "UNKNOWN"),
        ("import typing as t\nclass C(t.Protocol):\n    def check(self): pass\n", "UNKNOWN"),
        (
            "from typing import Protocol\nclass C(Protocol):\n    def check(self): 'doc'\n",
            "UNKNOWN",
        ),
        ("from other import Base\nclass C(Base):\n    def check(self): ...\n", "UNKNOWN"),
        ("from abc import abstractmethod\n@abstractmethod\ndef check(): ...\n", "UNKNOWN"),
        ("from typing import overload\n@overload\ndef check(): ...\n", "UNKNOWN"),
        ("class C:\n    @staticmethod\n    def check(): ...\n", "FAIL"),
        ("def check(): ...\ndef check(): return 1\n", "UNKNOWN"),
        ("from other import deco\n@deco\ndef check(): ...\n", "UNKNOWN"),
    ],
)
def test_placeholder_bodies_keep_unread_raises_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-PLACEHOLDER", "constructs": ["placeholder_body"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-PLACEHOLDER"] == expected, result["frame"]


def test_a_protocol_body_is_a_declaration() -> None:
    source = (
        "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
        "class C(P):\n    pass\nprint(P._is_protocol)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "True"
