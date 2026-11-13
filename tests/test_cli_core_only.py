# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The core-only entry must not load either Python decision package."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = """
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "archkeel.ir" or fullname.startswith("archkeel.ir."):
            raise AssertionError("Python IR imported: " + fullname)
        if fullname == "archkeel.check" or fullname.startswith("archkeel.check."):
            raise AssertionError("Python checker imported: " + fullname)
        if fullname == "archkeel.analyzer" or fullname.startswith("archkeel.analyzer."):
            raise AssertionError("Python collector imported: " + fullname)
sys.meta_path.insert(0, Guard())
from archkeel.cli import main
raise SystemExit(main(sys.argv[1:]))
"""


@pytest.mark.parametrize("command", ["validate", "report", "check", "explore"])
def test_core_only_never_imports_python_decision_packages(command: str, tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-c", GUARD, command, "--core-only", "--root", str(tmp_path), "--json"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2, done.stderr
    assert "Traceback" not in done.stderr
    assert '"status": "UNKNOWN"' in done.stdout


@pytest.mark.parametrize("value", ["1", "false"])
def test_a_bad_switch_value_also_refuses_without_python_decision_imports(value: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", GUARD, "validate", f"--core-only={value}", "--json"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2, done.stderr
    assert "Traceback" not in done.stderr
    assert '"status": "UNKNOWN"' in done.stdout
