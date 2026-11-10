# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-341: every test node that tests/pr-test.mk names exists.

pytest collects nothing for any file when one named node id is missing, so a renamed test or a
changed parameter would silently empty the whole PR test run (issue #979).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = re.compile(r"(tests/[^\s'\\]+::[^\s'\\]+)")


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
