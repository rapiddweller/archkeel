# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1260: the self-check gate fails on no usable answer, a refusal, FAIL or a violation only.

Each case runs `tools/self_check_gate.py` as a process on a real result of the core. An UNKNOWN rule
and a gap are shown and never fail it, and there is no comparison with another commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from self_check_support import FIXTURES, RULE, gate, real, save, violation, worse


def red(done, *shown: str) -> None:  # type: ignore[no-untyped-def]
    assert done.returncode == 1, done.stdout
    assert "self-check gate: RED (exit 1)" in done.stdout
    for text in shown:
        assert text in done.stdout, done.stdout


def test_a_real_result_with_an_unknown_rule_and_a_gap_is_green() -> None:
    result = real("base.json")
    assert result["frame"]["status"] == "UNKNOWN" and result["exit_code"] == 2
    done = gate(str(FIXTURES / "base.json"))
    assert done.returncode == 0, done.stdout
    assert "self-check gate: GREEN" in done.stdout and "UNKNOWN" in done.stdout


def test_an_all_pass_result_without_a_gap_is_green(tmp_path: Path) -> None:
    result = real("base.json")
    worse("PASS", result)
    result["gaps"] = []
    result["frame"]["collection_gaps"] = []
    result["exit_code"] = 0
    done = gate(save(tmp_path, "r.json", result))
    assert done.returncode == 0, done.stdout
    assert "1 rules PASS, 0 FAIL, 0 UNKNOWN" in done.stdout


def test_more_gaps_and_a_changed_rule_set_are_never_red(tmp_path: Path) -> None:
    """No base is read: a result is judged alone, so a growing gap list cannot fail it."""
    result = real("base.json")
    result["gaps"] = result["gaps"] * 50
    result["frame"]["rules"]["NEW-RULE"] = ["forbidden_dependency", "UNKNOWN"]
    assert gate(save(tmp_path, "r.json", result)).returncode == 0


def test_a_fail_or_a_violation_is_red_and_the_log_names_it(tmp_path: Path) -> None:
    result = real("base.json")
    violation(result)
    red(gate(save(tmp_path, "r.json", result)), f"rule {RULE} is FAIL", "violation:")


def test_the_log_shows_ten_violations_and_counts_the_rest(tmp_path: Path) -> None:
    result = real("base.json")
    violation(result, 500)
    done = gate(save(tmp_path, "r.json", result))
    red(done, "and 490 more violations")
    assert len(done.stdout.splitlines()) < 20


@pytest.mark.parametrize(
    "result",
    [
        {"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_error", "message": "x"}},
        "",
        "{not json",
        "[]",
        {"exit_code": 2},
        {"frame": {"rules": {}}, "exit_code": 2},
        {"frame": {"rules": {"R": ["k"]}}, "exit_code": 2},
    ],
)
def test_no_usable_answer_is_red(tmp_path: Path, result: object) -> None:
    done = gate(save(tmp_path, "r.json", result))  # type: ignore[arg-type]
    red(done)


def test_a_refusal_names_its_kind_and_a_missing_file_names_itself(tmp_path: Path) -> None:
    red(gate(str(FIXTURES / "refused.json")), "refusal: core_error")
    red(gate(str(tmp_path / "absent.json")), "is missing")


def test_a_status_the_core_never_writes_is_red(tmp_path: Path) -> None:
    result = real("base.json")
    worse("MAYBE", result)
    red(gate(save(tmp_path, "r.json", result)), "not PASS, FAIL or UNKNOWN")


def test_an_exit_code_that_its_statuses_do_not_give_is_red(tmp_path: Path) -> None:
    unknown = real("base.json")
    unknown["exit_code"] = 0  # UNKNOWN must not read as PASS
    red(gate(save(tmp_path, "u.json", unknown)), "exit code 0 differs from 2")
    counted = real("base.json")
    violation(counted)
    counted["frame"]["details"] = {}
    red(gate(save(tmp_path, "c.json", counted)), "counts 1 violations and lists 0")


def test_a_newline_in_a_message_never_starts_a_log_line(tmp_path: Path) -> None:
    refused = {"refusal": {"kind": "k", "message": "a\n::error::boom"}, "exit_code": 2}
    done = gate(save(tmp_path, "r.json", refused))
    red(done)
    assert [line for line in done.stdout.splitlines() if line.startswith("::")] == []
