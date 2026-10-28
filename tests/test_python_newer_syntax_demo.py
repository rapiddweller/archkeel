# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Newer Python runtimes give the same verdicts on the same source (issue #724)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from test_runtime import _git, _interpreter, _report

FIXTURE = Path(__file__).parents[1] / "fixtures/python-newer-syntax-demo"


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "python-newer-syntax-demo"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Archkeel fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "python newer syntax demo")
    return root


@pytest.mark.parametrize("minor", [11, 12, 13, 14])
def test_demo_verdicts_do_not_depend_on_the_python_runtime(tmp_path: Path, minor: int) -> None:
    try:
        _interpreter(minor)
    except subprocess.CalledProcessError:
        # CI installs 3.11 and 3.12 only; a developer run with uv covers 3.13 and 3.14.
        pytest.skip(f"Python 3.{minor} is not installed")
    root = _fixture(tmp_path)
    # The CR body after the LF license header is the input under test.
    assert b"\r\r\r" in (root / "sample/legacy.py").read_bytes()
    code, result = _report(minor, root)
    assert result["python_version"].startswith(f"3.{minor}.")
    assert (code, result["exit_code"], result["diagnostics"]) == (0, 0, []), result
    assert result["coverage"]["files_parsed"] == result["coverage"]["files_discovered"] == 4
    assert result["coverage"]["calls_unresolved"] == 0
    assert result["declared_rules"] == "FAIL"
    assert {row["id"]: (row["status"], row["count"]) for row in result["rule_assessments"]} == {
        "CALL-PURGE-MAINTENANCE-ONLY": ("FAIL", 1),
        "CONSTRUCT-EXACT-TYPE-IGNORE": ("PASS", 0),
    }
    [finding] = result["findings"]
    assert finding["rules"] == ["CALL-PURGE-MAINTENANCE-ONLY"]
    assert finding["locations"] == [
        {"line": 4, "path": "sample/maintenance.py"},
        {"line": 9, "path": "sample/report.py"},
    ]
    assert finding["subjects"] == [
        "sample.maintenance.purge",
        "sample.report.summarize.<listcomp:9:11>.<genexpr:9:15>",
    ]
