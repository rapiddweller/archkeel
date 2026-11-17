# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-676: the merge tool refuses unless every required check of the head is a success."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from merge_pr import main, refusals  # noqa: E402

PR = {
    "state": "OPEN",
    "isDraft": False,
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "headRefOid": "a" * 40,
    "baseRefName": "main",
    "changedFiles": 2,
}


@pytest.mark.parametrize("state", ["failure", "skipped", "in_progress", "cancelled", "neutral"])
def test_a_required_check_that_is_not_a_success_blocks_the_merge(state: str) -> None:
    assert refusals(PR, ["PR gate"], {"PR gate": state}) != []
    assert refusals(PR, ["PR gate"], {}) == ["required check 'PR gate' is missing, not success"]
    assert refusals(PR, ["PR gate"], {"PR gate": "success"}) == []


def test_a_draft_a_conflict_a_stale_head_or_a_closed_request_blocks_the_merge() -> None:
    assert refusals({**PR, "isDraft": True}, [], {})
    assert refusals({**PR, "mergeable": "CONFLICTING"}, [], {})
    assert refusals({**PR, "mergeStateStatus": "BEHIND"}, [], {})
    assert refusals({**PR, "state": "MERGED"}, [], {})


class Fake:
    """A `gh` that answers from a table and records each call."""

    def __init__(self, pr: dict, runs: str, files: list[str], protection: str | None) -> None:
        self.pr, self.runs, self.files, self.protection = pr, runs, files, protection
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        text = " ".join(args)
        if args[:2] == ("pr", "view") and "mergeCommit" in text:
            return json.dumps({"mergeCommit": {"oid": "b" * 40}})
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


def test_a_green_head_merges_without_admin_and_with_the_head_commit() -> None:
    fake = Fake(PR, "PR gate\tsuccess\n", ["a.py"], '{"contexts": ["PR gate"]}')
    assert main(["7"], fake) == 0
    merge = next(call for call in fake.calls if call[:2] == ("pr", "merge"))
    assert "--admin" not in merge and "--match-head-commit" in merge and "a" * 40 in merge


def test_a_red_head_does_not_merge() -> None:
    fake = Fake(PR, "PR gate\tfailure\n", ["a.py"], None)
    assert main(["7"], fake) == 1
    assert not any(call[:2] == ("pr", "merge") for call in fake.calls)


def test_an_empty_landing_is_an_error() -> None:
    fake = Fake(PR, "PR gate\tsuccess\n", [], '{"contexts": ["PR gate"]}')
    assert main(["7"], fake) == 2


def test_the_tool_never_names_admin_or_no_verify() -> None:
    source = (Path(__file__).parents[1] / "tools/merge_pr.py").read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]
    assert "--admin" not in code and "--no-verify" not in code
