# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-676, AD-736: the decision table of the merge tool (MERGE, WAIT, REFUSE) and its exit codes."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from merge_pr import decide, main  # noqa: E402

PR = {
    "state": "OPEN",
    "isDraft": False,
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "headRefOid": "a" * 40,
    "baseRefName": "main",
    "changedFiles": 2,
}
GREEN = {"PR gate": ("completed", "success")}


def codes(decision) -> list[str]:
    return [reason.code for reason in decision.reasons]


def test_a_green_head_merges() -> None:
    decision = decide(PR, ["PR gate"], GREEN)
    assert (decision.verdict, decision.reasons) == ("MERGE", [])


@pytest.mark.parametrize("status", ["queued", "in_progress", "pending", "waiting"])
def test_a_check_that_is_not_completed_is_wait_never_a_refusal(status: str) -> None:
    decision = decide(PR, ["PR gate"], {"PR gate": (status, "")})
    assert decision.verdict == "WAIT" and codes(decision) == ["check_pending"]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", "timed_out"])
def test_a_completed_check_that_is_not_a_success_is_refused_with_its_conclusion(
    conclusion: str,
) -> None:
    decision = decide(PR, ["PR gate"], {"PR gate": ("completed", conclusion)})
    assert decision.verdict == "REFUSE" and codes(decision) == ["check_failed"]
    assert conclusion in decision.reasons[0].detail


def test_a_missing_check_is_refused_with_the_next_step() -> None:
    decision = decide(PR, ["PR gate"], {})
    assert decision.verdict == "REFUSE" and codes(decision) == ["check_missing"]
    assert "re-run" in decision.reasons[0].detail


@pytest.mark.parametrize(
    "state",
    [{"mergeable": "UNKNOWN"}, {"mergeStateStatus": "UNKNOWN"}],
)
def test_an_unknown_merge_state_is_wait_never_resolve_the_conflict(state: dict) -> None:
    decision = decide({**PR, **state}, ["PR gate"], GREEN)
    assert decision.verdict == "WAIT" and codes(decision) == ["mergeability_unknown"]
    assert "conflict" not in decision.reasons[0].detail


@pytest.mark.parametrize("state", [{"mergeable": "CONFLICTING"}, {"mergeStateStatus": "DIRTY"}])
def test_a_conflict_is_refused(state: dict) -> None:
    decision = decide({**PR, **state}, ["PR gate"], GREEN)
    assert decision.verdict == "REFUSE" and codes(decision) == ["conflict"]


def test_a_draft_a_closed_request_and_a_blocked_state_are_refused() -> None:
    assert codes(decide({**PR, "isDraft": True}, [], {})) == ["draft"]
    assert codes(decide({**PR, "state": "MERGED"}, [], {})) == ["not_open"]
    assert codes(decide({**PR, "mergeStateStatus": "BLOCKED"}, ["PR gate"], GREEN)) == ["blocked"]


def test_a_head_behind_its_base_may_merge_when_the_gate_is_green() -> None:
    """Non-strict protection (owner decision 2026-11-17): BEHIND alone is no reason to refuse."""
    behind = {**PR, "mergeStateStatus": "BEHIND"}
    assert decide(behind, ["PR gate"], GREEN).verdict == "MERGE"
    assert decide(behind, ["PR gate"], {"PR gate": ("completed", "failure")}).verdict == "REFUSE"


def test_refuse_beats_wait_and_wait_beats_merge() -> None:
    decision = decide({**PR, "mergeable": "UNKNOWN"}, ["A", "B"], {"A": ("queued", "")})
    assert decision.verdict == "REFUSE" and set(codes(decision)) == {
        "mergeability_unknown",
        "check_pending",
        "check_missing",
    }


class Fake:
    """A `gh` that answers from a table and records each call."""

    def __init__(
        self,
        pr: dict,
        runs: str,
        files: list[str],
        protection: str | None,
        merge_oid: str | None = "b" * 40,
    ) -> None:
        self.pr, self.runs, self.files, self.protection = pr, runs, files, protection
        self.merge_oid = merge_oid
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        text = " ".join(args)
        if args[:2] == ("pr", "view") and "mergeCommit" in text:
            return json.dumps({"mergeCommit": {"oid": self.merge_oid} if self.merge_oid else None})
        if args[:2] == ("pr", "view"):
            return json.dumps(self.pr)
        if "required_status_checks" in text:
            if self.protection is None:
                raise SystemExit("not protected")
            return self.protection
        if "check-runs" in text:
            return self.runs
        if args[:2] == ("pr", "merge"):
            return ""
        return json.dumps({"files": self.files})

    def merged(self) -> bool:
        return any(call[:2] == ("pr", "merge") for call in self.calls)


DONE = "PR gate\tcompleted\tsuccess\n"


def test_a_green_head_merges_without_admin_and_with_the_head_commit() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    assert main(["7"], fake) == 0
    merge = next(call for call in fake.calls if call[:2] == ("pr", "merge"))
    assert "--admin" not in merge and "--match-head-commit" in merge and "a" * 40 in merge


def test_a_red_head_exits_1_and_a_pending_head_exits_3_without_a_merge(capsys) -> None:
    red = Fake(PR, "PR gate\tcompleted\tfailure\n", ["a.py"], None)
    assert main(["7"], red) == 1 and not red.merged()
    pending = Fake(PR, "PR gate\tin_progress\t\n", ["a.py"], None)
    assert main(["7"], pending) == 3 and not pending.merged()
    assert "check_pending" in capsys.readouterr().err


def test_the_json_output_names_the_verdict_the_reasons_the_required_set_and_the_head(
    capsys,
) -> None:
    fake = Fake(PR, "PR gate\tqueued\t\n", ["a.py"], '{"contexts": ["PR gate"]}')
    assert main(["7", "--json"], fake) == 3
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "verdict": "WAIT",
        "reasons": [{"code": "check_pending", "detail": document["reasons"][0]["detail"]}],
        "required": {"names": ["PR gate"], "source": "protection"},
        "head": "a" * 40,
    }
    fallback = Fake(PR, DONE, ["a.py"], None)
    main(["7", "--json"], fallback)
    assert json.loads(capsys.readouterr().out)["required"]["source"] == "default"


def test_wait_loops_while_the_verdict_is_wait_and_then_merges() -> None:
    states = iter(["PR gate\tin_progress\t\n", "PR gate\tin_progress\t\n", DONE])
    fake = Fake(PR, "", ["a.py"], None)
    original = fake.__call__

    def with_changing_runs(*args: str) -> str:
        if "check-runs" in " ".join(args):
            fake.calls.append(args)
            return fake.runs
        return original(*args)

    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake.runs = next(states)

    fake.runs = next(states)
    assert main(["7", "--wait", "600"], with_changing_runs, sleep) == 0
    assert len(sleeps) == 2 and fake.merged()


def test_wait_zero_does_not_loop() -> None:
    fake = Fake(PR, "PR gate\tqueued\t\n", ["a.py"], None)
    assert main(["7"], fake, lambda _s: pytest.fail("slept")) == 3


def test_an_empty_landing_exits_2_and_a_landing_not_yet_visible_exits_4() -> None:
    empty = Fake(PR, DONE, [], '{"contexts": ["PR gate"]}')
    assert main(["7"], empty) == 2
    hidden = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}', merge_oid=None)
    assert main(["7"], hidden) == 4 and hidden.merged()


def test_the_tool_never_names_admin_or_no_verify() -> None:
    source = (Path(__file__).parents[1] / "tools/merge_pr.py").read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]
    assert "--admin" not in code and "--no-verify" not in code
