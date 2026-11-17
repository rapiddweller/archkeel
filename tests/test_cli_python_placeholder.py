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
        ("def check():\n    'documentation'\n    pass\n", "UNKNOWN"),
        ("def check():\n    raise UnknownError\n", "UNKNOWN"),
        ("class P:\n    def check(self): ...\n", "FAIL"),
        (
            "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
            "class C(P):\n    pass\n",
            "FAIL",
        ),
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


def test_a_protocol_placeholder_can_reach_a_concrete_instance() -> None:
    source = (
        "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
        "class C(P):\n    pass\nprint(C().check() is None)\n"
    )
    done = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "True"
