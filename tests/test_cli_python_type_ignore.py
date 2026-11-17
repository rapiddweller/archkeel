# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Type-ignore comments have exact evidence and a bounded absence proof."""

from pathlib import Path

import pytest
from test_cli_native_python_imports import rows
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def check():\n    return 1\n", "PASS"),
        ('def check():\n    return "# type: ignore[attr-defined]"\n', "PASS"),
        ("def check(item):\n    item.close()  # type: ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\n    item.close()  #type:ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\r    item.close()  # type: ignore[attr-defined]\r", "FAIL"),
        ("def check(item):\n    item.close(1)  # type: ignore[attr-defined]\n", "UNKNOWN"),
        ("def check(item):\n    item.one(); item.two()  # type: ignore[attr-defined]\n", "UNKNOWN"),
        ("# type: ignore[attr-defined]\ndef check():\n    return 1\n", "UNKNOWN"),
    ],
)
def test_type_ignore_is_a_comment_not_string_text(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-TYPE-IGNORE", "constructs": ["type_ignore"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-TYPE-IGNORE"] == expected, result["frame"]


@pytest.mark.parametrize(("tag", "expected"), [("[attr-defined]", "PASS"), ("[other]", "FAIL")])
def test_a_type_ignore_allowance_matches_the_exact_site(
    release_core: Path, tmp_path: Path, tag: str, expected: str
) -> None:
    rule = {
        **CONSTRUCT,
        "id": "NO-TYPE-IGNORE",
        "constructs": ["type_ignore"],
        "allowed_type_ignores": [
            {
                "qualified_name": "app.client.page.check",
                "line": 2,
                "statement": "item.close()",
                "tag": "[attr-defined]",
            }
        ],
    }
    source = f"def check(item):\n    item.close()  # type: ignore{tag}\n"
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-TYPE-IGNORE"] == expected, result["frame"]
