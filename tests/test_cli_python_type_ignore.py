# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Type-ignore comments have exact evidence and a bounded absence proof."""

import ast
import json
from pathlib import Path

import pytest
from core_support import ROOT
from test_cli_native_python_imports import rows, verdict
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned

from tools.fixture_tree import fixture_tree


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def check():\n    return 1\n", "PASS"),
        ("def check(item):\n    run(item)\n", "PASS"),
        ('def check(item):\n    run("# type: ignore[call-arg]")\n', "PASS"),
        ("def check(item):\n    run(item)  # type: ignore[call-arg]\n", "FAIL"),
        ("def check(run):\n    run(1)  # type: ignore[call-arg]\n", "FAIL"),
        ("def check(item):\n    run(\n        item)  # type: ignore[call-arg]\n", "UNKNOWN"),
        ("def check(item):\n    run(item); run(item)  # type: ignore[call-arg]\n", "UNKNOWN"),
        ("def check(item):\n    factory()(item)  # type: ignore[call-arg]\n", "UNKNOWN"),
        ("def check(item):\n    rün(item)  # type: ignore[call-arg]\n", "UNKNOWN"),
        ("def check(item):\n    run (item)  # type: ignore[call-arg]\n", "UNKNOWN"),
        ('def check():\n    return "# type: ignore[attr-defined]"\n', "PASS"),
        ("def check(item):\n    item.close()  # type: ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\n    item.close()  #type:ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\r    item.close()  # type: ignore[attr-defined]\r", "FAIL"),
        ("def check(item):\n    item.close(1)  # type: ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\n    item.close(key='x')  # type: ignore[attr-defined]\n", "FAIL"),
        ("def check(item):\n    value = item  # type: ignore[assignment]\n", "FAIL"),
        ("def check(item):\n    value = item.close(1)  # type: ignore[assignment]\n", "FAIL"),
        ("def check(item):\n    value: int = item  # type: ignore[assignment]\n", "FAIL"),
        ("def check(item):\n    value: int  # type: ignore[assignment]\n", "FAIL"),
        ("def check(item):\n    value: '# type: ignore[assignment]' = item\n", "PASS"),
        ("def check(item):\n    item.value: int = 1  # type: ignore[assignment]\n", "UNKNOWN"),
        (
            "def check(item):\n    value: int = (\n        item)  # type: ignore[assignment]\n",
            "UNKNOWN",
        ),
        (
            "def check(item):\n    value: int = item; other()  # type: ignore[assignment]\n",
            "UNKNOWN",
        ),
        ("def check(item):\n    return item  # type: ignore[return-value]\n", "FAIL"),
        ("def check():\n    return  # type: ignore[return-value]\n", "UNKNOWN"),
        ('def check(item):\n    return "# type: ignore[return-value]"\n', "PASS"),
        (
            "def check(item):\n    return (\n        item)  # type: ignore[return-value]\n",
            "UNKNOWN",
        ),
        (
            "def check(item):\n    return item; item.close()  # type: ignore[return-value]\n",
            "UNKNOWN",
        ),
        (
            "def check(item):\n    value = (\n        item)  # type: ignore[assignment]\n",
            "UNKNOWN",
        ),
        ("def check(item):\n    x = y = item  # type: ignore[assignment]\n", "UNKNOWN"),
        ("def check(item):\n    x = item; y = item  # type: ignore[assignment]\n", "UNKNOWN"),
        ("def check(item):\r    x = item\r    # type: ignore[assignment]\r", "UNKNOWN"),
        (
            "def check(item):\n    item.close(\n        1)  # type: ignore[attr-defined]\n",
            "UNKNOWN",
        ),
        (
            "def check(item):\n    item.close(1) + other()  # type: ignore[attr-defined]\n",
            "UNKNOWN",
        ),
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
@pytest.mark.parametrize(
    "statement",
    [
        "item.close()",
        "item.close(1, key='x')",
        "run(item, key='x')",
        "value = item",
        "value: int = item",
        "value: int",
        "return item",
    ],
)
def test_a_type_ignore_allowance_matches_the_exact_site(
    release_core: Path, tmp_path: Path, tag: str, expected: str, statement: str
) -> None:
    rule = {
        **CONSTRUCT,
        "id": "NO-TYPE-IGNORE",
        "constructs": ["type_ignore"],
        "allowed_type_ignores": [
            {
                "qualified_name": "app.client.page.check",
                "line": 2,
                "statement": statement,
                "tag": "[attr-defined]",
            }
        ],
    }
    source = f"def check(item):\n    {statement}  # type: ignore{tag}\n"
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-TYPE-IGNORE"] == expected, result["frame"]


@pytest.mark.parametrize(
    ("reviewed", "written", "tag", "expected"),
    [
        ("handle.close()", "handle.close()", "[attr-defined]", "PASS"),
        ("handle.inner.close()", "handle.inner.close()", "[attr-defined]", "PASS"),
        ("handle.close()", "handle.inner.close()", "[attr-defined]", "FAIL"),
        ("handle.inner.close()", "handle.inner.close()", "[call-arg]", "FAIL"),
        ("handle.inner.close()", "handle.inner.close(\r        )", "[attr-defined]", "UNKNOWN"),
        ("handle.inner.close()", "handle().inner.close()", "[attr-defined]", "UNKNOWN"),
        ("handle.inner.close()", "handle[0].inner.close()", "[attr-defined]", "UNKNOWN"),
        ("handle.inner.close()", 'handle.inner.close("# type: ignore[attr-defined]")', "", "PASS"),
    ],
)
def test_newer_syntax_demo_requires_an_exact_written_ignore(
    release_core: Path,
    reviewed: str,
    written: str,
    tag: str,
    expected: str,
) -> None:
    with fixture_tree(ROOT / "fixtures/python-newer-syntax-demo") as root:
        legacy = root / "sample/legacy.py"
        trailing = f"  # type: ignore{tag}" if tag else ""
        before = legacy.read_bytes()
        original = b"handle.close()  # type: ignore[attr-defined]"
        assert before.count(original) == 1
        source = before.replace(original, f"{written}{trailing}".encode())
        legacy.write_bytes(source)
        assert [ignore.tag for ignore in ast.parse(source, type_comments=True).type_ignores] == (
            [tag] if tag else []
        )

        contract = root / "docs/architecture/architecture-contract.json"
        payload = json.loads(contract.read_bytes())
        rule = next(
            rule for rule in payload["rules"] if rule["id"] == "CONSTRUCT-EXACT-TYPE-IGNORE"
        )
        rule["allowed_type_ignores"][0]["statement"] = reviewed
        contract.write_text(json.dumps(payload), encoding="utf-8")
        result = verdict(release_core, root, "report")
    frame = result["frame"]
    assert rows(result)["CONSTRUCT-EXACT-TYPE-IGNORE"] == expected, frame
    assert frame["self_test"]["reply"]["files"] == 4
    # AD-1070: a reviewed ignore that no written ignore matches is an unused exception.
    assert [gap["kind"] for gap in frame["gaps"]] == (
        ["unused_allowance"] if expected == "FAIL" else []
    )
    call_rule = "CALL-PURGE-MAINTENANCE-ONLY"
    assert frame["rules"][call_rule] == ["call_owner", "FAIL"]
    [detail] = frame["details"][call_rule]
    assert detail["target"] == "sample.maintenance.purge"
    assert {"path": "sample/report.py", "line": 9} in [
        frame["locations"][site] for site in detail["evidence"]
    ]
    assert result["exit_code"] == 1
