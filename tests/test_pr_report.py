# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The PR gate report runs every step and lists all failures (AD-756)."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

import pr_report  # noqa: E402


def fake(failing: set[str]):
    ran: list[str] = []

    def runner(command: Sequence[str]) -> tuple[int, str]:
        ran.append(" ".join(command))
        name = next((n for n in failing if n in " ".join(command)), None)
        return (1, f"noise\nE  {name} broke\nmore") if name else (0, "ok")

    return runner, ran


def test_the_precheck_runs_only_the_cheap_steps_and_all_failures_are_listed(capsys) -> None:
    runner, ran = fake({"tools/rust_api.py", "test_repository_hygiene.py"})
    code = pr_report.main(["--mode", "precheck"], runner)
    out = capsys.readouterr().out
    assert code == 1
    assert len(ran) == len([s for s in pr_report.steps("b") if s.kind == pr_report.CHEAP])
    assert not any("make" in command for command in ran)
    assert "rust-api-baseline | FAIL" in out and "hygiene-and-file-size | FAIL" in out
    assert "E  tools/rust_api.py broke" in out and "fix:" in out
    assert "2 of 7 steps failed" in out


def test_the_report_runs_the_steps_after_a_failure_and_the_cheap_ones_come_first() -> None:
    listed = pr_report.steps("origin/main")
    kinds = [step.kind for step in listed]
    assert kinds == sorted(kinds, key=lambda kind: kind != pr_report.CHEAP)
    runner, ran = fake({"ruff format"})
    assert pr_report.main(["--mode", "report"], runner) == 1
    assert len(ran) == len(listed), "a failed first step does not stop the others"


def test_a_green_run_exits_zero_and_a_missing_tool_is_a_failure(capsys) -> None:
    runner, _ran = fake(set())
    assert pr_report.main(["--mode", "precheck"], runner) == 0
    assert "all steps passed" in capsys.readouterr().out
    code, text = pr_report.shell(("no-such-tool-for-archkeel",))
    assert code == 127 and "no-such-tool" in text
