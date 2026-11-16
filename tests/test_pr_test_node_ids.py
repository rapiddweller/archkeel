# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-341: every test file and test node that tests/pr-test.mk names exists.

pytest collects nothing for any file when one named file or node id is missing, so a renamed test,
a changed parameter or a deleted file would silently empty the whole PR test run (issue #979).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = re.compile(r"(tests/[^\s'\\]+::[^\s'\\]+)")
FILE = re.compile(r"(tests/[^\s'\\:]+\.py)")


def test_each_named_node_of_the_pr_test_list_exists() -> None:
    nodes = NODE.findall((ROOT / "tests/pr-test.mk").read_text(encoding="utf-8"))
    assert nodes, "tests/pr-test.mk names no single test node; update this test."
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *nodes],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    missing = [
        line for line in (collected.stdout + collected.stderr).splitlines() if "not found" in line
    ]
    assert collected.returncode == 0 and not missing, "\n".join(missing) or collected.stdout[-2000:]


def test_each_file_of_the_pr_test_list_exists() -> None:
    text = (ROOT / "tests/pr-test.mk").read_text(encoding="utf-8")
    files = sorted(set(FILE.findall(text)))
    assert files, "tests/pr-test.mk names no single test file; update this test."
    missing = [name for name in files if not (ROOT / name).is_file()]
    assert not missing, f"tests/pr-test.mk names files that do not exist: {missing}"
