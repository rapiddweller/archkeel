# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The merge check fails on a conflict or a file set that differs from GitHub. Behind main warns."""

import os
import subprocess
from pathlib import Path

import pytest

from tools import merge_check
from tools.merge_check import check

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, env=ENV, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, {"a.txt": "1\n", "b.txt": "1\n"}, "Add the base files")
    return tmp_path


def test_clean_pull_request_has_no_finding(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"new.txt": "2\n"}, "Add the new file")
    report = check(repo, "main", "feature", ["new.txt"])
    assert report.errors == []
    assert report.warnings == []


def test_conflict_names_the_file_and_a_moved_main_is_a_warning(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"a.txt": "feature\n"}, "Change a in the feature")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"a.txt": "main\n"}, "Change a on main")
    report = check(repo, "main", "feature", ["a.txt"])
    assert [e for e in report.errors if "conflict" in e and "a.txt" in e]
    assert [w for w in report.warnings if "not an ancestor" in w]
    assert report.failed


def test_a_branch_behind_main_without_a_conflict_is_a_warning_only(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"new.txt": "2\n"}, "Add the new file")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"b.txt": "main\n"}, "Change b on main")
    report = check(repo, "main", "feature", ["new.txt"])
    assert report.errors == []
    assert [w for w in report.warnings if "not an ancestor" in w]
    assert not report.failed


def test_file_changed_only_on_the_branch_is_an_error_when_github_omits_it(repo: Path) -> None:
    # The branch reverts main's change to b.txt. GitHub lists only a.txt, so the branch differs.
    commit(repo, {"b.txt": "2\n"}, "Change b on main")
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"a.txt": "feature\n", "b.txt": "1\n"}, "Change a and revert b")
    report = check(repo, "main", "feature", ["a.txt"])
    assert len(report.errors) == 1
    assert "b.txt" in report.errors[0]
    assert "a.txt" not in report.errors[0]


def test_file_listed_by_github_but_absent_from_the_branch_is_an_error(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"new.txt": "2\n"}, "Add the new file")
    report = check(repo, "main", "feature", ["new.txt", "b.txt"])
    assert len(report.errors) == 1
    assert "b.txt" in report.errors[0]


def test_an_append_to_a_file_changed_on_recent_main_gives_no_warning(repo: Path) -> None:
    commit(repo, {"a.txt": "1\nmain\n"}, "Append to a on main")
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"a.txt": "1\nmain\nfeature\n"}, "Append to a again")
    report = check(repo, "main", "feature", ["a.txt"])
    assert report.errors == []
    assert report.warnings == []


def test_removed_lines_in_a_file_changed_on_recent_main_are_a_warning_not_an_error(
    repo: Path,
) -> None:
    commit(repo, {"a.txt": "main\n"}, "Change a on main")
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"a.txt": "feature\n"}, "Change a again")
    report = check(repo, "main", "feature", ["a.txt"])
    assert report.errors == []
    assert [w for w in report.warnings if "a.txt" in w]


@pytest.fixture
def pr_on_main(repo: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    head = commit(repo, {"new.txt": "2\n"}, "Add the new file")
    git(repo, "checkout", "-q", "main")
    monkeypatch.setattr(merge_check, "fetch_pr", lambda repo_, number: head)
    return head


def test_main_exits_zero_for_a_clean_pull_request(
    repo: Path, pr_on_main: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(merge_check, "pr_view", lambda number: (pr_on_main, ["new.txt"]))
    assert merge_check.main(["7"], repo=repo) == 0
    assert "0 error(s)" in capsys.readouterr().out


def test_main_exits_one_when_the_fetched_head_is_not_the_github_head(
    repo: Path, pr_on_main: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(merge_check, "pr_view", lambda number: ("0" * 40, ["new.txt"]))
    assert merge_check.main(["7"], repo=repo) == 1
    assert "moved" in capsys.readouterr().err


def test_main_exits_one_when_the_pull_request_conflicts(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    head = commit(repo, {"a.txt": "feature\n"}, "Change a in the feature")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"a.txt": "main\n"}, "Change a on main")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    monkeypatch.setattr(merge_check, "fetch_pr", lambda repo_, number: head)
    monkeypatch.setattr(merge_check, "pr_view", lambda number: (head, ["a.txt"]))
    assert merge_check.main(["7"], repo=repo) == 1
    assert "conflict" in capsys.readouterr().out
