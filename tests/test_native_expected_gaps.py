# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-357, AD-382, AD-383: a self-check of the core equals its pins: gaps, violations, statuses.

Consumer: `make self-validate-native`
(`tools/native_expected.py`). The input is the result document of `archkeel validate --json`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_expected import (  # noqa: E402
    expected_exit,
    growth,
    main,
    problems,
    summary,
    unlisted,
    written,
)

ROOT = Path(__file__).resolve().parents[1]

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


# AD-672: the pins are ratchets. A pin may only shrink; growth needs a reason in the growth file.
GROWTH_FILES = [
    ROOT / "native/expected-growth.json",
    ROOT / "docs/architecture/target/shell-expected-growth.json",
]
CLEAN = {"rules": {"R": "PASS"}, "unknown": {}, "gaps": [], "violations": []}


def test_growth_names_a_new_gap_violation_status_and_unknown_reason() -> None:
    assert growth(CLEAN, CLEAN) == []
    assert growth(PINNED, PINNED) == []
    assert growth(PINNED, CLEAN) == [
        ["gap", "collection_gap", "a", "r"],
        ["rule", "R", "UNKNOWN"],
        ["unknown", "R", "scope_incomplete"],
    ]
    assert growth(FAILED, PINNED) == [
        ["violation", "R", "m.a -> m.b", "m.a", "dependency cycle"],
        ["rule", "R", "FAIL"],
    ]
    assert growth(CLEAN, FAILED) == [], "a smaller pin is no growth"
    assert growth({**CLEAN, "rules": {"N": "UNKNOWN"}}, CLEAN) == [["rule", "N", "UNKNOWN"]]


def test_growth_needs_an_entry_with_a_reason() -> None:
    grown = [["gap", "collection_gap", "a", "r"]]
    assert unlisted(grown, {}) and unlisted(grown, {"raised": [{"entry": grown[0], "reason": ""}]})
    assert unlisted(grown, {"raised": [{"entry": grown[0], "reason": "short"}]})
    reason = "a new collector limit, decided on 2026-11-16 in the decision log"
    assert unlisted(grown, {"raised": [{"entry": grown[0], "reason": reason}]}) == []


def test_write_refuses_a_new_unknown_and_takes_a_listed_one(tmp_path: Path) -> None:
    result, pin, listed = tmp_path / "r.json", tmp_path / "p.json", tmp_path / "g.json"
    result.write_text(json.dumps(_result([GAP])))
    pin.write_text(json.dumps(CLEAN))
    listed.write_text('{"raised": []}')
    run = [str(result), str(pin), "--write", "--growth", str(listed)]
    assert main(run) == 1 and json.loads(pin.read_text()) == CLEAN
    entry = ["gap", "collection_gap", "a", "r"]
    items = [entry, ["rule", "R", "UNKNOWN"], ["unknown", "R", "scope_incomplete"]]
    reason = "a new collector limit, decided on 2026-11-16 in the decision log"
    listed.write_text(json.dumps({"raised": [{"entry": item, "reason": reason} for item in items]}))
    assert main(run) == 0 and json.loads(pin.read_text())["gaps"] == [PIN]


def test_every_growth_entry_of_the_repository_has_a_reason() -> None:
    for path in GROWTH_FILES:
        raised = json.loads(path.read_text(encoding="utf-8"))["raised"]
        for item in raised:
            assert len(str(item.get("reason", "")).strip()) >= 10, (path.name, item)
            assert item.get("entry") and item["entry"][0] in {"gap", "violation", "rule", "unknown"}


def test_a_pin_that_grew_against_its_base_fails_until_its_growth_has_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    pin, listed, result = tmp_path / "pin.json", tmp_path / "growth.json", tmp_path / "r.json"
    pin.write_text(json.dumps(CLEAN))
    for command in (["init", "-q"], ["add", "pin.json"], ["commit", "-q", "-m", "base"]):
        subprocess.run([*git, *command], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    pin.write_text(json.dumps(PINNED))
    result.write_text(json.dumps(_result([GAP])))
    listed.write_text('{"raised": []}')
    run = [str(result), "pin.json", "--growth", str(listed), "--base-ref", "HEAD"]
    assert main(run) == 1
    reason = "a new collector limit, decided on 2026-11-16 in the decision log"
    items = [["gap", "collection_gap", "a", "r"], ["rule", "R", "UNKNOWN"]]
    items.append(["unknown", "R", "scope_incomplete"])
    listed.write_text(json.dumps({"raised": [{"entry": i, "reason": reason} for i in items]}))
    assert main(run) == 0
