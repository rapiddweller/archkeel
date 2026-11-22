# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: an oracle test never skips in CI, and each selected oracle has run (hole 8).

Consumer: the CI jobs. A `skipif` on a missing python3.12, cargo, node or dart hid every oracle
check when the tool was absent from the runner. The plugin `oracle_support` turns such a skip
into a failure when `CI` is set, and fails the session when a selected oracle ran no test. These
tests run the plugin in a child pytest, so the real hooks decide.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import oracle_support
import pytest

TESTS = Path(__file__).parent
HEAD = "import pytest\n\n"
SKIPPED = HEAD + "@pytest.mark.skipif(True, reason='node is the oracle')\ndef test_x(): pass\n"
OTHER = HEAD + "@pytest.mark.skipif(True, reason='needs a symbolic link')\ndef test_x(): pass\n"
PASSED = HEAD + "@pytest.mark.skipif(False, reason='dart is the oracle')\ndef test_x(): pass\n"
XFAIL = (
    HEAD + "@pytest.mark.skipif(False, reason='cargo is not installed')\n"
    "@pytest.mark.xfail(strict=True)\ndef test_x(): assert False\n"
)


def child(tmp_path: Path, source: str, *, ci: bool) -> subprocess.CompletedProcess[str]:
    """Run the plugin in a child pytest on one test file."""
    (tmp_path / "test_child.py").write_text(source)
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    env = {k: v for k, v in os.environ.items() if k not in {"CI", "PYTEST_ADDOPTS"}}
    env["PYTHONPATH"] = str(TESTS)
    if ci:
        env["CI"] = "1"
    command = [sys.executable, "-m", "pytest", "-p", "oracle_support", "-p", "no:cacheprovider"]
    return subprocess.run(
        [*command, "-p", "no:xdist", "-q", str(tmp_path / "test_child.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("reason", "tool"),
    [
        ("Python is the oracle", "python312"),
        ("python3.12 is the oracle", "python312"),
        ("needs python3.12 as the truth", "python312"),
        ("CPython is the oracle", "python312"),
        ("rustc is the oracle", "cargo"),
        ("Rust runs the fixtures", "cargo"),
        ("node is the oracle", "node"),
        ("dart is the oracle", "dart"),
        ("needs a symbolic link", None),
    ],
)
def test_a_skip_reason_names_its_oracle(reason: str, tool: str | None) -> None:
    assert oracle_support.tool_of(reason) == tool


def test_every_oracle_skip_of_the_suite_names_a_tool() -> None:
    """A `skipif` on a missing oracle tool with a new wording would escape the guard."""
    found = 0
    pattern = re.compile(
        r'which\("(python3\.12|cargo|node|dart)"\)\s+is None,\s*reason="([^"]+)"', re.S
    )
    for path in sorted(TESTS.glob("test_*.py")):
        for tool, reason in pattern.findall(path.read_text()):
            found += 1
            assert oracle_support.tool_of(reason) is not None, (path.name, tool, reason)
    assert found >= 20, found


def test_the_oracles_that_a_run_selected_and_did_not_run_are_named() -> None:
    assert oracle_support.unran({"node", "dart"}, {"dart"}) == {"node"}
    assert oracle_support.unran({"node"}, {"node", "cargo"}) == set()
    assert oracle_support.unran(set(), set()) == set()


def test_a_skipped_oracle_fails_only_in_ci() -> None:
    def report() -> SimpleNamespace:
        shown = ("t.py", 3, "Skipped: dart is the oracle")
        return SimpleNamespace(skipped=True, longrepr=shown, outcome="skipped")

    ci, local, other = report(), report(), report()
    other.longrepr = ("t.py", 3, "Skipped: needs a symbolic link")
    assert oracle_support.fail_skip(ci, {"CI": "true"}) and ci.outcome == "failed"
    assert not oracle_support.fail_skip(local, {}) and local.outcome == "skipped"
    assert not oracle_support.fail_skip(other, {"CI": "true"}) and other.outcome == "skipped"


def test_the_child_run_fails_a_skipped_oracle_in_ci(tmp_path: Path) -> None:
    done = child(tmp_path, SKIPPED, ci=True)
    assert done.returncode == 1, done.stdout
    assert "CI must provide the oracle `node`" in done.stdout


def test_the_child_run_skips_a_missing_oracle_outside_ci(tmp_path: Path) -> None:
    done = child(tmp_path, SKIPPED, ci=False)
    assert done.returncode == 0 and "1 skipped" in done.stdout, done.stdout


def test_the_child_run_keeps_the_skip_of_another_reason_in_ci(tmp_path: Path) -> None:
    done = child(tmp_path, OTHER, ci=True)
    assert done.returncode == 0 and "1 skipped" in done.stdout, done.stdout


def test_the_child_run_accepts_an_oracle_that_ran(tmp_path: Path) -> None:
    done = child(tmp_path, PASSED, ci=True)
    assert done.returncode == 0 and "oracle never ran" not in done.stdout, done.stdout


def test_the_child_run_fails_when_a_selected_oracle_ran_no_passing_test(tmp_path: Path) -> None:
    done = child(tmp_path, XFAIL, ci=True)
    assert done.returncode == 1, done.stdout
    assert "oracle never ran in CI: cargo" in done.stdout, done.stdout
