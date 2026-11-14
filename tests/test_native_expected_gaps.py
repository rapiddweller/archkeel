# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-357, AD-382, AD-383: a self-check of the core equals its pins: gaps, violations, statuses.

Consumer: `make self-validate-native` and `make browser-architecture-check`
(`tools/native_expected.py`). The input is the result document of `archkeel validate --json`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_expected import expected_exit, problems, summary, written  # noqa: E402

GAP = {"kind": "collection_gap", "subjects": ["a"], "reason": "r"}
PIN = ["collection_gap", "a", "r"]
PINNED = {"rules": {"R": "UNKNOWN"}, "unknown": {"R": "scope_incomplete"}, "gaps": [PIN]}
CYCLE = {"source": "m.a -> m.b", "target": "m.a", "cause": "dependency cycle", "evidence": ["E1"]}
PINNED_CYCLE = {
    "rule": "R",
    "source": "m.a -> m.b",
    "target": "m.a",
    "cause": "dependency cycle",
    "issue": 7,
}
FAILED = {"rules": {"R": "FAIL"}, "unknown": {}, "gaps": [PIN], "violations": [PINNED_CYCLE]}


def _result(
    gaps: list[dict[str, Any]],
    status: str = "UNKNOWN",
    count: int = 0,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    frame = {
        "rules": {"R": ["forbidden_dependency", status]},
        "unknown_kinds": {"R": "scope_incomplete"} if status == "UNKNOWN" else {},
        "collection_gaps": gaps,
        "violations": {"R": count} if count else {},
        "details": {"R": rows} if rows else {},
        "locations": {"E1": {"path": "a.rs", "line": 3}},
    }
    exit_code = {"FAIL": 1, "UNKNOWN": 2}.get(status, 2 if gaps else 0)
    return {"frame": frame, "gaps": [], "exit_code": exit_code}


def test_the_pinned_result_passes() -> None:
    assert problems(_result([GAP]), PINNED) == []


def test_a_new_gap_a_missing_gap_a_status_and_a_violation_fail() -> None:
    other = {**GAP, "subjects": ["c"]}
    assert problems(_result([GAP, other]), PINNED) == ["new gap: ('collection_gap', 'c', 'r')"]
    assert problems(_result([]), PINNED)[0] == "missing gap: ('collection_gap', 'a', 'r')"
    assert problems({**_result([GAP]), "exit_code": 1}, PINNED) == ["exit code 1 differs from 2"]
    assert problems(_result([GAP], "PASS"), PINNED)
    counted = problems(_result([GAP], count=1), PINNED)
    assert counted == ["violation of R"]


def test_a_gap_of_the_result_document_is_a_gap_too() -> None:
    scope = {"kind": "scope_proof", "subject": "R", "reason": "no decision"}
    result = {**_result([GAP]), "gaps": [scope]}
    assert problems(result, PINNED) == ["new gap: ('scope_proof', 'R', 'no decision')"]


def test_a_refusal_fails_and_names_its_kind() -> None:
    refusal = {"kind": "collection_refused", "message": "no reply"}
    assert problems({"refusal": refusal, "exit_code": 2}, PINNED) == [
        "refused: collection_refused: no reply"
    ]


def test_another_reason_of_an_unknown_rule_fails() -> None:
    result = _result([GAP])
    result["frame"]["unknown_kinds"] = {"R": "rule_kind_not_ported"}
    [problem] = problems(result, PINNED)
    assert problem.startswith("UNKNOWN reasons {'R': 'rule_kind_not_ported'} differ")


def test_the_exit_code_comes_from_the_pinned_statuses() -> None:
    assert expected_exit({"rules": {"A": "PASS"}, "gaps": []}) == 0
    assert expected_exit({"rules": {"A": "PASS", "B": "UNKNOWN"}, "gaps": []}) == 2
    assert expected_exit({"rules": {"A": "PASS"}, "gaps": [PIN]}) == 2
    assert expected_exit({"rules": {"A": "FAIL", "B": "UNKNOWN"}, "gaps": [PIN]}) == 1
    # A result with no rule proves nothing.
    assert expected_exit({"rules": {}, "gaps": []}) == 2


def test_the_gate_line_counts_the_unknown_rules_and_the_pinned_gaps() -> None:
    """AD-382: a green gate with pinned gaps must not read as a proven result."""
    line = summary(_result([GAP]))
    assert line == "native self-check: 0 rules PASS, 0 FAIL, 1 UNKNOWN; 1 pinned gaps, 0 violations"
    assert summary(_result([GAP]), "Studio UI").startswith("Studio UI self-check: 0 rules PASS")


def test_a_violation_names_its_file_and_line_and_a_pinned_gap_counts() -> None:
    """AD-382: the gate prints where a violation is, and a pinned gap is a multiset member."""
    result = _result([GAP], "FAIL", 2, [CYCLE])
    where = "violation of R\n  m.a -> m.b -> m.a: dependency cycle at a.rs:3"
    assert problems(result, FAILED) == [where]
    twice = {**PINNED, "gaps": [PIN, PIN]}
    assert problems(_result([GAP]), twice) == ["missing gap: ('collection_gap', 'a', 'r')"]
    assert problems(_result([GAP, GAP]), PINNED) == ["new gap: ('collection_gap', 'a', 'r')"]


def test_a_pinned_violation_with_its_issue_passes_next_to_the_gaps() -> None:
    assert problems(_result([GAP], "FAIL", 1, [CYCLE]), FAILED) == []


def test_a_new_a_missing_or_a_violation_without_an_issue_number_fails() -> None:
    """The gate checks that an issue number is present, not that the issue exists."""
    other = {**CYCLE, "source": "m.a -> m.c"}
    cycle = ("R", "m.a -> m.b", "m.a", "dependency cycle")
    assert problems(_result([GAP], "FAIL", 2, [CYCLE, other]), FAILED) == [
        "new violation: ('R', 'm.a -> m.c', 'm.a', 'dependency cycle')"
    ]
    assert problems(_result([GAP], "FAIL", 0, []), FAILED) == [f"missing violation: {cycle}"]
    unfiled = {**FAILED, "violations": [{**PINNED_CYCLE, "issue": None}]}
    assert problems(_result([GAP], "FAIL", 1, [CYCLE]), unfiled) == [
        f"violation without an issue number: {cycle}"
    ]


def test_write_keeps_the_issue_of_a_known_violation_and_leaves_a_new_one_open() -> None:
    other = {**CYCLE, "source": "m.a -> m.c"}
    old = {"name": "Studio UI", "violations": [PINNED_CYCLE]}
    pinned = written(_result([GAP], "FAIL", 2, [CYCLE, other]), old)
    assert pinned["violations"] == [
        PINNED_CYCLE,
        {**PINNED_CYCLE, "source": "m.a -> m.c", "issue": None},
    ]
    assert pinned["gaps"] == [PIN]
    assert (pinned["name"], pinned["rules"], pinned["unknown"]) == ("Studio UI", {"R": "FAIL"}, {})
