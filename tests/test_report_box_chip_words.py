# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The line of a box about the deviations inside follows the status of the box (S1, AD-730).

"Violation" is for a FAIL box. An UNKNOWN box says "open gap": the run has not decided there. An
allowed but unused dependency is no violation in any box.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCENE = Path(__file__).resolve().parents[1] / "native/report/assets/explorer/report-scene.js"
SCRIPT = """
const vm = require("node:vm");
const window = {};
vm.runInNewContext(require("node:fs").readFileSync(process.argv[1], "utf8"), { window });
const [status, rows] = JSON.parse(process.argv[2]);
console.log(window.ArchkeelReportScene.deviationChipText(status, rows));
"""
UNDECLARED = {"kind": "undeclared"}
UNUSED = {"kind": "allowed_unused"}


def chip(status: str, rows: list[dict[str, str]]) -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("no node on this runner")
        pytest.skip("no node on this machine")
    done = subprocess.run(
        [node, "-e", SCRIPT, str(SCENE), json.dumps([status, rows])],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout.strip()


@pytest.mark.parametrize(
    ("status", "rows", "text"),
    [
        ("FAIL", [UNDECLARED], "1 violation inside"),
        ("FAIL", [UNDECLARED, UNDECLARED], "2 violations inside"),
        ("UNKNOWN", [UNDECLARED], "1 open gap inside"),
        ("UNKNOWN", [UNDECLARED, UNDECLARED], "2 open gaps inside"),
        ("PASS", [UNUSED], "1 unused permission inside"),
        ("UNKNOWN", [UNUSED], "1 unused permission inside"),
        ("UNKNOWN", [UNDECLARED, UNUSED], "1 open gap · 1 unused permission inside"),
        ("PASS", [], ""),
    ],
)
def test_the_words_follow_the_status_of_the_box(
    status: str, rows: list[dict[str, str]], text: str
) -> None:
    assert chip(status, rows) == text


def test_no_box_says_deviation_any_more() -> None:
    assert "deviation inside" not in SCENE.read_text(encoding="utf-8")
    for part in sorted(SCENE.with_name("flow").glob("*.js")):
        assert "deviation inside" not in part.read_text(encoding="utf-8"), part.name


def test_the_colour_of_the_box_lines_follows_the_status_of_the_box() -> None:
    css = SCENE.with_name("explorer.css").read_text(encoding="utf-8")
    assert ".atlas-finding-chip,\n.rp-explorer .atlas-deviation-chip{fill:var(--ink-muted)}" in css
    for status, token in (("UNKNOWN", "--unknown-text"), ("FAIL", "--fail")):
        assert (
            f'.node[data-assessment-status="{status}"] .atlas-deviation-chip{{fill:var({token})}}'
            in css
        )
