# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""A placement PASS needs a complete selected class inventory."""

from pathlib import Path

import pytest
from test_cli_native_python_imports import RULE, project, rows, verdict


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test():\n    return 1\n", "PASS"),
        ("class Wrong: pass\n", "FAIL"),
        ("@replace\nclass Maybe: pass\n", "UNKNOWN"),
        ("if condition:\n    class Maybe: pass\n", "UNKNOWN"),
        ("class Wrong: pass\n@replace\nclass Maybe: pass\n", "FAIL"),
        ("from typing import Protocol\nclass Maybe(Protocol): pass\n", "UNKNOWN"),
        ("Hidden = type('Hidden', (), {})\n", "UNKNOWN"),
    ],
)
def test_placement_needs_proven_classes(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    placement = {
        **RULE,
        "id": "PLACEMENT",
        "kind": "symbol_placement",
        "source": "app",
        "class_kinds": ["class", "dataclass"],
        "allowed_sources": ["app.service"],
    }
    root = project(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/client.py": source,
            "src/app/service.py": "class Allowed: pass\n",
        },
        contract_rules=[placement],
    )
    result = verdict(release_core, root)
    assert rows(result)["PLACEMENT"] == expected, result["frame"]
