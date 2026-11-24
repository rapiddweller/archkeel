# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1064: what the log, the grown file and the job summary show of a self-check comparison."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from self_check_support import FIXTURES, RULE, TOOL, real, red, run, save, violation


def many_gaps(count: int) -> dict[str, Any]:
    more = real("base.json")
    gap = more["gaps"][0]
    more["gaps"] += [{**gap, "subject": f"{gap['subject']}/new{i}"} for i in range(count)]
    return more


def test_the_log_shows_ten_items_and_the_file_holds_all_of_them(tmp_path: Path) -> None:
    grown, summary = tmp_path / "out/grown.txt", tmp_path / "summary.md"
    pr = save(tmp_path, "p.json", many_gaps(25))
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        pr,
        extra=("--grown-file", str(grown), "--summary-file", str(summary)),
    )
    red(done, "grown 25", "and 15 more", f"All 25 grown items are in {grown}")
    assert done.stdout.count("    gap [") == 10
    assert len(grown.read_text().splitlines()) == 25
    assert all(" -- " in line for line in grown.read_text().splitlines())
    assert summary.read_text().count("- `gap [") == 10
    assert "25 grown items" in summary.read_text() and "and 15 more" in summary.read_text()


def test_a_red_result_names_the_local_command(tmp_path: Path) -> None:
    done = run(tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "plus-one-gap.json"))
    red(done, "`make self-validate-native`")
    assert "DISAGREEMENT" not in done.stdout


def test_the_summary_prints_the_counts_of_the_run(tmp_path: Path) -> None:
    done = run(
        tmp_path,
        save(tmp_path, "b.json", real("base.json")),
        save(tmp_path, "p.json", real("base.json")),
    )
    assert "rules PASS" in done.stdout and "gap records" in done.stdout


def test_report_only_fails_on_a_result_that_is_not_clean_but_not_on_growth(tmp_path: Path) -> None:
    growth = ("--report-only",)
    done = run(
        tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "plus-one-gap.json"), extra=growth
    )
    assert done.returncode == 0 and "inventory.stock" in done.stdout
    failing = real("base.json")
    violation(failing)
    done = run(
        tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", failing), extra=growth
    )
    red(done, f"rule {RULE} is FAIL")


@pytest.mark.parametrize("mode", ["alone", "shell"])
def test_a_clean_result_alone_is_green_and_a_refusal_or_a_fail_is_red(
    tmp_path: Path, mode: str
) -> None:
    def tool(result: dict[str, Any] | str) -> subprocess.CompletedProcess[str]:
        args = [sys.executable, str(TOOL), mode, save(tmp_path, "r.json", result)]
        return subprocess.run(args, capture_output=True, text=True, timeout=60)

    clean = real("base.json")
    # The base fixture has one gap: clean for `alone`, red for the strict shell gate.
    assert tool(clean).returncode == (1 if mode == "shell" else 0)
    pass_only = real("base.json")
    pass_only["gaps"] = []
    pass_only["frame"]["collection_gaps"] = []
    pass_only["exit_code"] = 0
    done = tool(pass_only)
    assert done.returncode == 0, done.stdout
    assert "rules PASS" in done.stdout
    failing = real("base.json")
    violation(failing)
    assert tool(failing).returncode == 1
    assert tool(REFUSED).returncode == 1 and "refusal" in tool(REFUSED).stdout
    assert tool("").returncode == 1


REFUSED = {"refusal": {"kind": "core_error", "message": "x"}, "exit_code": 2}
