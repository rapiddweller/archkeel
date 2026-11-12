# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-357: the self-check of native/ equals its pinned gaps and rule statuses, no more, no less.

Consumer: `make self-validate-native` (`tools/native_expected.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_expected import problems, summary  # noqa: E402

GAP = {"data": {"source_module": "a", "module": "b", "reason": "r"}, "title": "r"}
PINNED = {"rules": {"R": "UNKNOWN"}, "gaps": [["a", "b", "r"]]}


def _report(gaps: list[dict[str, Any]], status: str = "UNKNOWN", count: int = 0) -> dict[str, Any]:
    rules = [{"id": "R", "status": status, "count": count}]
    diagnostics = [{"kind": "incomplete_scan"}] if gaps else []
    exit_code = 2 if gaps else 0
    return {
        "coverage": {"failures": gaps},
        "rule_assessments": rules,
        "diagnostics": diagnostics,
        "exit_code": exit_code,
    }


def test_the_pinned_result_passes() -> None:
    assert problems(_report([GAP]), PINNED) == []


def test_a_new_gap_a_missing_gap_a_status_and_a_violation_fail() -> None:
    other = {"data": {"source_module": "a", "module": "c", "reason": "r"}, "title": "r"}
    assert problems(_report([GAP, other]), PINNED) == ["new gap: ('a', 'c', 'r')"]
    assert problems(_report([]), PINNED)[0] == "missing gap: ('a', 'b', 'r')"
    drift = {**_report([GAP]), "diagnostics": [{"kind": "contract_invalid"}]}
    assert problems(drift, PINNED) == ["diagnostic contract_invalid"]
    assert problems({**_report([GAP]), "exit_code": 1}, PINNED) == ["exit code 1 differs from 2"]
    assert problems(_report([GAP], "PASS"), PINNED)
    assert problems(_report([GAP], count=1), PINNED) == ["violation of R"]


def test_without_a_pinned_gap_every_rule_must_pass() -> None:
    assert problems(_report([], "PASS"), {"rules": {"R": "UNKNOWN"}, "gaps": []}) == []
    assert problems(_report([], "UNKNOWN"), {"rules": {"R": "UNKNOWN"}, "gaps": []})


def test_the_gate_line_counts_the_unknown_rules_and_the_pinned_gaps() -> None:
    """AD-382: a green gate with pinned gaps must not read as a proven result."""
    line = summary(_report([GAP]))
    assert line == "native self-check: 0 rules PASS, 0 FAIL, 1 UNKNOWN; 1 pinned gaps, 0 violations"


def test_a_violation_names_its_file_and_line_and_a_pinned_gap_counts() -> None:
    """AD-382: the gate prints where a violation is, and a pinned gap is a multiset member."""
    finding = {
        "rules": ["R"],
        "title": "eval imports toml",
        "locations": [{"path": "a.rs", "line": 3}],
    }
    report = {**_report([GAP], count=1), "findings": [finding]}
    assert problems(report, PINNED) == ["violation of R\n  eval imports toml at a.rs:3"]
    twice = {**PINNED, "gaps": [["a", "b", "r"], ["a", "b", "r"]]}
    assert problems(_report([GAP]), twice) == ["missing gap: ('a', 'b', 'r')"]
    assert problems(_report([GAP, GAP]), PINNED) == ["new gap: ('a', 'b', 'r')"]
