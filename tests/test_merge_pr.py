# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-676, AD-736: the decision table of the merge tool (MERGE, WAIT, REFUSE) and its exit codes."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from merge_pr import Changes, decide, deletions, entry_counts, main, moved_files  # noqa: E402

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


def test_a_draft_a_closed_request_is_refused_and_a_blocked_state_with_green_checks_waits() -> None:
    assert codes(decide({**PR, "isDraft": True}, [], {})) == ["draft"]
    assert codes(decide({**PR, "state": "MERGED"}, [], {})) == ["not_open"]

    blocked = decide({**PR, "mergeStateStatus": "BLOCKED"}, ["PR gate"], GREEN)
    assert (blocked.verdict, codes(blocked)) == ("WAIT", ["blocked"])  # GitHub lags a few seconds


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
        self.changed = [{"filename": "a.py", "status": "modified", "additions": 3, "deletions": 1}]
        self.labels: list[str] = []
        self.contents = {"base": "{}", "head": "{}"}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        text = " ".join(args)
        if "/compare/" in text:
            return json.dumps({"sha": "base-sha"})
        if "/contents/" in text:
            return self.contents["base" if "ref=base-sha" in text else "head"]
        if "/files" in text:
            return "\n".join(json.dumps(item) for item in self.changed)
        if args[:3] == ("pr", "view", "7") and "labels" in text:
            return json.dumps({"labels": [{"name": name} for name in self.labels]})
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


DONE = "1\tPR gate\tcompleted\tsuccess\n"


def test_a_green_head_merges_without_admin_and_with_the_head_commit() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    assert main(["7"], fake) == 0
    merge = next(call for call in fake.calls if call[:2] == ("pr", "merge"))
    assert "--admin" not in merge and "--match-head-commit" in merge and "a" * 40 in merge


def test_a_red_head_exits_1_and_a_pending_head_exits_3_without_a_merge(capsys) -> None:
    red = Fake(PR, "1\tPR gate\tcompleted\tfailure\n", ["a.py"], None)
    assert main(["7"], red) == 1 and not red.merged()
    pending = Fake(PR, "1\tPR gate\tin_progress\t\n", ["a.py"], None)
    assert main(["7"], pending) == 3 and not pending.merged()
    assert "check_pending" in capsys.readouterr().err


def test_the_json_output_names_the_verdict_the_reasons_the_required_set_and_the_head(
    capsys,
) -> None:
    fake = Fake(PR, "1\tPR gate\tqueued\t\n", ["a.py"], '{"contexts": ["PR gate"]}')
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
    states = iter(["1\tPR gate\tin_progress\t\n", "1\tPR gate\tin_progress\t\n", DONE])
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
    fake = Fake(PR, "1\tPR gate\tqueued\t\n", ["a.py"], None)
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


def _file(name: str, status: str = "modified", add: int = 0, delete: int = 0) -> dict:
    return {"filename": name, "status": status, "additions": add, "deletions": delete}


def test_a_deleted_file_is_refused_without_the_label_and_allowed_with_it() -> None:
    changes = Changes(files=[_file("a.py", "removed", 0, 5), _file("b.py", add=9)])
    refused = decide(PR, ["PR gate"], GREEN, changes)
    assert refused.verdict == "REFUSE" and codes(refused) == ["deletion_unapproved"]
    assert "a.py" in refused.reasons[0].detail and "deletion-approved" in refused.reasons[0].detail
    changes.labels = {"deletion-approved"}
    assert decide(PR, ["PR gate"], GREEN, changes).verdict == "MERGE"


def test_a_net_removal_over_300_lines_is_refused_like_the_reverts_of_1636() -> None:
    """#1636 removed 19,516 lines of other pull requests while it added 178."""
    changes = Changes(files=[_file("native/x.rs", add=178, delete=19_516)])
    assert codes(decide(PR, ["PR gate"], GREEN, changes)) == ["deletion_unapproved"]
    edge = Changes(files=[_file("a.rs", add=100, delete=400)])  # net 300 is allowed
    assert decide(PR, ["PR gate"], GREEN, edge).verdict == "MERGE"
    over = Changes(files=[_file("a.rs", add=100, delete=401)])
    assert decide(PR, ["PR gate"], GREEN, over).verdict == "REFUSE"
    assert (
        decide(PR, ["PR gate"], GREEN, Changes(files=[_file("a.rs", add=900, delete=700)])).verdict
        == "MERGE"
    )


def test_a_ratchet_file_that_loses_more_than_50_entries_needs_the_lead_label() -> None:
    changes = Changes(files=[_file("native/expected-growth.json", add=1, delete=2)])
    changes.entries["native/expected-growth.json"] = 51
    refused = decide(PR, ["PR gate"], GREEN, changes)
    assert codes(refused) == ["ratchet_removal_unapproved"]
    changes.labels = {"ratchet-lead"}
    assert decide(PR, ["PR gate"], GREEN, changes).verdict == "MERGE"
    changes.entries["native/expected-growth.json"] = 50
    changes.labels = set()
    assert decide(PR, ["PR gate"], GREEN, changes).verdict == "MERGE"


def test_both_guards_can_refuse_together_and_the_deletion_label_does_not_open_the_ratchet() -> None:
    changes = Changes(files=[_file("a.py", "removed", 0, 5)], labels={"deletion-approved"})
    changes.entries["native/expected-gaps.json"] = 90
    assert codes(decide(PR, ["PR gate"], GREEN, changes)) == ["ratchet_removal_unapproved"]


def test_the_entries_of_a_ratchet_file_are_its_lists_and_maps() -> None:
    assert (
        sum(entry_counts(json.dumps({"name": "n", "rules": {"A": "PASS"}, "gaps": []})).values())
        == 1
    )
    assert not entry_counts(json.dumps({"raised": []}))
    assert deletions(Changes()) == []


def test_main_reads_the_files_and_the_labels_and_refuses_an_unapproved_deletion() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("a.py", "removed", 0, 400)]
    assert main(["7"], fake) == 1 and not fake.merged()
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("a.py", "removed", 0, 400)]
    fake.labels = ["deletion-approved"]
    assert main(["7"], fake) == 0


def test_main_counts_the_entries_of_a_ratchet_file_at_the_merge_base_and_at_the_head() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("native/expected-growth.json", add=0, delete=6)]
    fake.contents = {
        "base": json.dumps({"raised": list(range(80))}),
        "head": json.dumps({"raised": list(range(20))}),
    }
    assert main(["7", "--json"], fake) == 1 and not fake.merged()
    fake.labels = ["ratchet-lead"]
    assert main(["7"], fake) == 0


@pytest.mark.parametrize("path", ["native/expected-gaps.json", "native/expected-growth.json"])
def test_replacements_do_not_hide_removed_gap_entries(path: str) -> None:
    def pin(start: int) -> str:
        gaps = [["collection_gap", f"module.{i}", "reason"] for i in range(start, start + 100)]
        if path.endswith("expected-growth.json"):
            return json.dumps(
                {"raised": [{"entry": ["gap", *gap], "reason": "approved"} for gap in gaps]}
            )
        return json.dumps({"gaps": gaps})

    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file(path, add=100, delete=100)]
    fake.contents = {"base": pin(0), "head": pin(100)}
    assert main(["7"], fake) == 1 and not fake.merged()
    fake.labels = ["ratchet-lead"]
    assert main(["7"], fake) == 0


@pytest.mark.parametrize("path", ["native/expected-gaps.json", "native/expected-growth.json"])
def test_removed_gap_entries_count_duplicate_occurrences(path: str) -> None:
    gap = ["collection_gap", "module", "reason"]

    def pin(gaps: list[list[str]]) -> str:
        if path.endswith("expected-growth.json"):
            return json.dumps(
                {"raised": [{"entry": ["gap", *item], "reason": "ok"} for item in gaps]}
            )
        return json.dumps({"gaps": gaps})

    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file(path, add=1, delete=1)]
    fake.contents = {
        "base": pin([gap] * 101),
        "head": pin([gap] * 50 + [["collection_gap", "other", "reason"]] * 51),
    }
    assert main(["7"], fake) == 1 and not fake.merged()
    fake.contents["head"] = pin([gap] * 51)
    assert main(["7"], fake) == 0


def test_raised_entry_identity_ignores_its_reason_and_order() -> None:
    old = {
        "raised": [
            {"entry": ["gap", str(i), "subject", "reason"], "reason": "old"} for i in range(60)
        ]
    }
    new = {"raised": [{**item, "reason": "new"} for item in reversed(old["raised"])]}
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("native/expected-growth.json", add=60, delete=60)]
    fake.contents = {"base": json.dumps(old), "head": json.dumps(new)}
    assert main(["7"], fake) == 0


def test_issue_numbers_and_rule_statuses_do_not_change_entry_identity() -> None:
    before = {
        "rules": {"R": "UNKNOWN"},
        "unknown": {"R": "gap"},
        "violations": [{"rule": "R", "source": "a", "target": "b", "cause": "c", "issue": 1}],
    }
    after = {
        "rules": {"R": "PASS"},
        "unknown": {"R": "other"},
        "violations": [{"rule": "R", "source": "a", "target": "b", "cause": "c", "issue": 2}],
    }
    assert not entry_counts(json.dumps(before)) - entry_counts(json.dumps(after))


def test_the_newest_run_of_a_check_name_counts_after_a_re_run() -> None:
    """#1653: a fresh green re-run is not hidden by an older red run, nor the reverse."""
    red_then_green = "1\tPR gate\tcompleted\tfailure\n9\tPR gate\tcompleted\tsuccess\n"
    fake = Fake(PR, red_then_green, ["a.py"], '{"contexts": ["PR gate"]}')
    assert main(["7"], fake) == 0
    green_then_red = "1\tPR gate\tcompleted\tsuccess\n9\tPR gate\tcompleted\tfailure\n"
    assert main(["7"], Fake(PR, green_then_red, ["a.py"], None)) == 1
    running = "1\tPR gate\tcompleted\tsuccess\n9\tPR gate\tin_progress\t\n"
    assert main(["7"], Fake(PR, running, ["a.py"], None)) == 3
    unordered = "9\tPR gate\tcompleted\tsuccess\n1\tPR gate\tcompleted\tfailure\n"
    assert main(["7"], Fake(PR, unordered, ["a.py"], None)) == 0


def test_a_renamed_file_counts_by_its_line_delta_not_as_a_deletion() -> None:
    """#1699: GitHub lists `status: renamed` for a rename, with or without edits."""
    plain = Changes(
        files=[{**_file("new_tests.rs", "renamed", 0, 0), "previous_filename": "old.rs"}]
    )
    assert decide(PR, ["PR gate"], GREEN, plain).verdict == "MERGE"
    edited = Changes(files=[_file("new_tests.rs", "renamed", add=540, delete=21)])
    assert decide(PR, ["PR gate"], GREEN, edited).verdict == "MERGE"
    shrunk = Changes(files=[_file("new_tests.rs", "renamed", add=10, delete=400)])
    assert codes(decide(PR, ["PR gate"], GREEN, shrunk)) == ["deletion_unapproved"]  # net 390


def test_a_removed_file_whose_lines_went_to_an_added_file_is_a_move() -> None:
    old = "\n".join(f"fn test_{i}() {{}}" for i in range(100))
    new = old + "\nfn extra() {}\n"
    assert moved_files(["a.rs"], ["b.rs"], lambda _p: old, lambda _p: new) == {"a.rs"}
    assert moved_files(["a.rs"], ["b.rs"], lambda _p: old, lambda _p: "fn other() {}\n") == set()
    changes = Changes(files=[_file("a.rs", "removed", 0, 519), _file("b.rs", "added", 540, 0)])
    changes.moved = {"a.rs"}
    assert decide(PR, ["PR gate"], GREEN, changes).verdict == "MERGE"


def test_main_treats_a_removed_and_added_pair_with_the_same_lines_as_a_rename() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("a.rs", "removed", 0, 519), _file("b.rs", "added", 540, 0)]
    fake.contents = {
        "base": "\n".join(f"line {i}" for i in range(50)),
        "head": "\n".join(f"line {i}" for i in range(60)),
    }
    assert main(["7"], fake) == 0


def test_a_real_deletion_still_refuses_and_the_message_never_prints_a_negative_net() -> None:
    fake = Fake(PR, DONE, ["a.py"], '{"contexts": ["PR gate"]}')
    fake.changed = [_file("a.rs", "removed", 0, 519), _file("b.rs", "added", 540, 0)]
    fake.contents = {
        "base": "\n".join(f"old {i}" for i in range(50)),
        "head": "\n".join(f"new {i}" for i in range(60)),
    }
    assert main(["7"], fake) == 1
    refused = decide(
        PR,
        ["PR gate"],
        GREEN,
        Changes(files=[_file("a.rs", "removed", 0, 519), _file("b.rs", "added", 540, 0)]),
    )
    detail = refused.reasons[0].detail
    assert (
        "deletes 1 file(s) (a.rs)" in detail
        and "-" not in detail.split("(a.rs)", 1)[1].split(":")[0]
    )
    assert "lines net" not in detail
