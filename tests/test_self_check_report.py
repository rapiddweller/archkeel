# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1064: what the log, the grown file and the job summary show of a self-check comparison."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from self_check_support import (
    FIXTURES,
    RULE,
    TOOL,
    green,
    many_gaps,
    real,
    red,
    run,
    save,
    violation,
    worse,
)


def test_the_log_shows_ten_items_and_the_file_holds_all_of_them(tmp_path: Path) -> None:
    grown, summary = tmp_path / "out/grown.txt", tmp_path / "summary.md"
    pr = save(tmp_path, "p.json", many_gaps(25))
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        pr,
        extra=("--grown-file", str(grown), "--summary-file", str(summary)),
    )
    green(done, "grown 25", "and 15 more", f"All 25 grown items are in {grown}")
    assert done.stdout.count("    gap [") == 10
    assert len(grown.read_text().splitlines()) == 25
    assert all(" -- " in line for line in grown.read_text().splitlines())
    assert summary.read_text().count("- `gap [") == 10
    assert "25 grown items" in summary.read_text() and "and 15 more" in summary.read_text()


def test_a_red_result_names_the_local_command(tmp_path: Path) -> None:
    done = run(tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "scan-shrank.json"))
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


def test_a_clean_result_alone_is_green_and_a_refusal_or_a_fail_is_red(tmp_path: Path) -> None:
    def tool(result: dict[str, Any] | str) -> subprocess.CompletedProcess[str]:
        args = [sys.executable, str(TOOL), "alone", save(tmp_path, "r.json", result)]
        return subprocess.run(args, capture_output=True, text=True, timeout=60)

    assert tool(real("base.json")).returncode == 0  # one gap is clean for `alone`
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


def test_a_newline_in_a_reason_never_starts_a_log_line(tmp_path: Path) -> None:
    more = many_gaps(1)
    more["gaps"][-1]["reason"] = "first\n::error::x\r::warning::y\u2028::notice::z"
    refused = {"refusal": {"kind": "k", "message": "a\n::error::boom"}, "exit_code": 2}
    for pr in (more, refused):
        done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr))
        assert done.returncode == (1 if "refusal" in pr else 0)
        assert [line for line in done.stdout.splitlines() if line.startswith("::")] == []
        assert "::error::x" in done.stdout or "::error::boom" in done.stdout


def test_the_summary_is_small_with_500_violations(tmp_path: Path) -> None:
    pr = real("base.json")
    worse("FAIL")(pr)
    row = {"source": "a", "target": "b", "cause": "x" * 400, "evidence": []}
    pr["frame"]["details"] = {RULE: [{**row, "source": f"s{i}"} for i in range(500)]}
    pr["frame"]["violations"] = {RULE: 500}
    pr["exit_code"] = 1
    summary = tmp_path / "summary.md"
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        save(tmp_path, "p.json", pr),
        extra=("--summary-file", str(summary)),
    )
    assert done.returncode == 1 and "and 490 more violations" in done.stdout
    text = summary.read_text()
    assert len(text) < 10_000 and len(text.splitlines()) <= 25
