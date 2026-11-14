# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-480: the `interface_boundary` receipt needs the scan check, for a mount and for a root.

The trees are the plants of the proof review of #1155; each expected row is the row of 4.0.1.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from test_cli_core_only_scan import command

# The plants of the proof review of #1155: each tree maps a path to its text, and `expected`
# gives the rule and the row of release 4.0.1 on it.
DATA = json.loads(
    (Path(__file__).parent / "golden/mounted-receipt/interface-plants.json").read_text()
)
PLANTS: dict[str, dict[str, str]] = DATA["plants"]
EXPECTED: dict[str, list[str]] = DATA["expected"]


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_an_interface_row_without_the_scan_check_is_never_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    done = command(release_core, tree(tmp_path, PLANTS[name]), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    rule, expected = EXPECTED[name]
    rows = {key: row[1] for key, row in result["frame"]["rules"].items()}
    assert rows[rule] == expected, result["frame"]["explained"]
