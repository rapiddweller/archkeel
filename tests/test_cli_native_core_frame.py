# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390: the shell reads the frame of the core into typed values and fails closed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from archkeel.cli.core_frame import CoreError, GapKind, RuleStatus, Status, read_frame
from archkeel.cli.native_core import Decided, FellBack, PythonRule, read_inside, stage_one

RULES = {"A": "complete_assignment", "B": "no_component_cycles"}


def raw(
    statuses: dict[str, str] | None = None, status: str = "PASS", **fields: Any
) -> dict[str, Any]:
    found = {"A": "PASS", "B": "PASS"} if statuses is None else statuses
    value: dict[str, Any] = {
        "engine": "archkeel-core abc",
        "status": status,
        "rules": {rule: [RULES.get(rule, "x"), verdict] for rule, verdict in found.items()},
        "explained": {},
        "violations": {},
        "beyond": {},
        "scope": "complete",
        "sections": {},
        "unsupported": {"rules": {}, "sections": {}, "report": None},
        "self_test": {"contract": {"rules": RULES}, "reply": {"files": 3}},
    }
    value.update(fields)
    return value


def read(value: dict[str, Any] | str, exit_code: int = 0) -> Any:
    text = value if isinstance(value, str) else json.dumps(value)
    return read_frame(text.encode(), exit_code)


def python(**statuses: str) -> list[PythonRule]:
    return [
        PythonRule(rule, RuleStatus(status), 1 if status == "FAIL" else 0)
        for rule, status in statuses.items()
    ]


def test_a_decided_frame_reads_into_typed_values() -> None:
    frame = read(raw())
    assert frame.decided
    assert frame.status == "PASS"
    assert {rule: verdict.status for rule, verdict in frame.rules.items()} == {
        "A": "PASS",
        "B": "PASS",
    }


def test_a_named_rule_is_a_gap_with_its_kind() -> None:
    reason = "unsupported: rule kind CallOwner: the slice of its family ports it"
    value = raw(
        {"A": "PASS"},
        "UNKNOWN",
        unsupported={"rules": {"B": reason}, "sections": {}, "report": None},
    )
    frame = read(value, 3)
    assert not frame.decided
    assert [(gap.kind, gap.subject) for gap in frame.gaps] == [(GapKind.RULE_KIND_NOT_PORTED, "B")]


def test_a_refused_reply_and_a_whole_contract_reason_are_gaps() -> None:
    value = raw(
        {},
        "UNKNOWN",
        unsupported={"rules": "producer not verified: x", "sections": {}, "report": None},
        self_test={"contract": {"rules": RULES}, "reply": {"refused": "bad"}},
    )
    kinds = [gap.kind for gap in read(value, 3).gaps]
    assert kinds == [GapKind.PRODUCER_NOT_VERIFIED, GapKind.REPLY_REFUSED]


HOSTILE = [
    ("not JSON", "{", 0),
    ("truncated", json.dumps(raw())[:-5], 0),
    ("two frames", json.dumps(raw()) + json.dumps(raw()), 0),
    ("trailing text", json.dumps(raw()) + " x", 0),
    ("a list", "[]", 0),
    ("a missing field", {k: v for k, v in raw().items() if k != "scope"}, 0),
    ("an unknown field", raw(producer="trusted"), 0),
    ("a trust field", raw(standard_library=["os"]), 0),
    ("an unknown status", raw(status="MAYBE"), 0),
    ("an unknown rule status", raw({"A": "OK"}), 0),
    ("PASS with zero rules", raw({}), 0),
    (
        "PASS with an UNKNOWN row and a beyond rule",
        raw({"A": "PASS", "B": "UNKNOWN"}, explained={"B": "x"}, beyond={"A": "y"}),
        0,
    ),
    ("PASS with only declarations", raw({"A": "DECLARATION"}), 0),
    (
        "PASS with a named rule",
        raw(unsupported={"rules": {"C": "x"}, "sections": {}, "report": None}),
        3,
    ),
    (
        "PASS with a refused reply",
        raw(self_test={"contract": {"rules": RULES}, "reply": {"refused": "x"}}),
        3,
    ),
    (
        "exit 0 with a named rule",
        raw(
            {"A": "PASS"},
            "UNKNOWN",
            unsupported={"rules": {"B": "x"}, "sections": {}, "report": None},
        ),
        0,
    ),
    ("exit 3 without a named part", raw(), 3),
    ("exit 1", raw(), 1),
    ("exit 2", raw(), 2),
    ("FAIL without violations", raw({"A": "FAIL"}, "FAIL"), 0),
    ("UNKNOWN without its reason", raw({"A": "UNKNOWN"}, "UNKNOWN"), 0),
    ("PASS with a reason", raw({"A": "PASS"}, explained={"A": "why"}), 0),
    ("a row without a rule", raw(violations={"Z": 1}), 0),
    ("a negative count", raw({"A": "FAIL"}, "FAIL", violations={"A": -1}), 0),
    ("a count that is a flag", raw({"A": "FAIL"}, "FAIL", violations={"A": True}), 0),
    (
        "a beyond rule that is not PASS",
        raw({"A": "FAIL"}, "FAIL", violations={"A": 1}, beyond={"A": "x"}),
        0,
    ),
    ("an engine that is not a text", raw(engine=7), 0),
    (
        "two reply states",
        raw(self_test={"contract": {"rules": RULES}, "reply": {"files": 1, "absent": "x"}}),
        0,
    ),
    ("an unknown unsupported part", raw(unsupported={"rules": {}, "sections": {}}), 0),
]


def test_a_contract_without_rules_is_refused_by_name() -> None:
    """Both engines give PASS; #1096 decides one policy, and until then the reader refuses."""
    with pytest.raises(CoreError, match="PASS with zero rules"):
        read(raw({}))


@pytest.mark.parametrize(("name", "value", "exit_code"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a_hostile_frame_is_refused(name: str, value: dict[str, Any] | str, exit_code: int) -> None:
    with pytest.raises(CoreError):
        read(value, exit_code)


def test_the_stage_one_rule_takes_a_decided_frame_that_python_agrees_with() -> None:
    outcome = stage_one(read(raw()), python(A="PASS", B="PASS"), Status.PASS)
    assert isinstance(outcome, Decided)
    assert outcome.beyond == ()


def test_a_named_frame_falls_back_and_keeps_its_reasons() -> None:
    value = raw(
        {"A": "PASS"}, "UNKNOWN", unsupported={"rules": {"B": "x"}, "sections": {}, "report": None}
    )
    outcome = stage_one(read(value, 3), python(A="PASS", B="PASS"), Status.PASS)
    assert isinstance(outcome, FellBack)
    assert [gap.subject for gap in outcome.gaps] == ["B"]


def test_a_rule_beyond_the_reference_is_shown_and_is_no_difference() -> None:
    value = raw(beyond={"B": "no one of the 1 kept pair gaps can change the rule"})
    outcome = stage_one(read(value), python(A="PASS", B="UNKNOWN"), Status.UNKNOWN)
    assert isinstance(outcome, Decided)
    assert outcome.beyond == ("B",)


@pytest.mark.parametrize(
    ("name", "value", "rows", "status"),
    [
        ("a rule status", raw(), python(A="PASS", B="FAIL"), "FAIL"),
        (
            "two rule statuses under one run status",
            raw({"A": "FAIL", "B": "PASS"}, "FAIL", violations={"A": 1}),
            python(A="PASS", B="FAIL"),
            "FAIL",
        ),
        ("a run status", raw(), python(A="PASS", B="PASS"), "UNKNOWN"),
        (
            "a PASS over an UNKNOWN that is not beyond",
            raw(),
            python(A="PASS", B="UNKNOWN"),
            "UNKNOWN",
        ),
        (
            "a beyond rule that Python passes",
            raw(beyond={"B": "x"}),
            python(A="PASS", B="PASS"),
            "PASS",
        ),
        ("a rule in one engine", raw(), python(A="PASS"), "PASS"),
        (
            "a violation count",
            raw({"A": "FAIL", "B": "PASS"}, "FAIL", violations={"A": 2}),
            python(A="FAIL", B="PASS"),
            "FAIL",
        ),
    ],
)
def test_a_difference_is_raised(
    name: str, value: dict[str, Any], rows: list[PythonRule], status: str
) -> None:
    with pytest.raises(CoreError, match="the core and the Python engine differ"):
        stage_one(read(value), rows, Status(status))


def test_read_inside_refuses_a_path_outside_the_repository(tmp_path: Path) -> None:
    """Review S2, fault M5: an inside contract outside the root is not sent, by path or link."""
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.json").write_text("{}")
    (root / "inside.json").write_text("{}")
    (root / "link.json").symlink_to(tmp_path / "outside.json")
    assert read_inside(root, "../outside.json", 1 << 20) is None
    assert read_inside(root, "link.json", 1 << 20) is None
    assert read_inside(root, "inside.json", 1 << 20) == ("inside.json", b"{}")
