# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1222: a PR job with a checkout of depth 1 gets its merge base, or it fails loud."""

import subprocess
from pathlib import Path

import pytest

from tools import fetch_history


def git(cwd: Path, *arguments: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def pull(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """A shallow checkout of a merge commit, and a base that is 10 commits behind main."""
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    git(origin, "config", "uploadpack.allowFilter", "true")
    git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    for number in range(5):
        commit(origin, f"m{number}")
    git(origin, "checkout", "-q", "-b", "topic")
    commit(origin, "b1")
    commit(origin, "b2")
    git(origin, "checkout", "-q", "main")
    base = commit(origin, "m5")
    for number in range(6, 16):
        commit(origin, f"m{number}")
    git(origin, "checkout", "-q", "-b", "merge")
    git(origin, "merge", "-q", "--no-edit", "topic")
    work = tmp_path / "work"
    url = f"file://{origin}"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--no-tags", "--branch", "merge", url, str(work)],
        check=True,
    )
    monkeypatch.chdir(work)
    return work, base


def test_a_shallow_checkout_gets_its_merge_base_and_origin_main(
    pull: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    work, base = pull
    assert git(work, "rev-parse", "--is-shallow-repository") == "true"
    assert fetch_history.main([base], depths=(40,)) == 0
    assert "(40)" in capsys.readouterr().out
    assert git(work, "merge-base", base, "HEAD") == base
    git(work, "rev-parse", "--verify", "origin/main")


def test_a_depth_that_hides_the_base_is_not_enough(
    pull: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # At depth 4 a common ancestor exists (an older commit of main), but the base is not yet an
    # ancestor of HEAD in the shallow graph: the merge base would be wrong. The loop goes on.
    work, base = pull
    assert fetch_history.main([base], depths=(4,)) == 1
    assert git(work, "merge-base", base, "HEAD") != base
    assert fetch_history.main([base], depths=(2, 4, 64)) == 0
    assert "(64)" in capsys.readouterr().out
    assert git(work, "merge-base", base, "HEAD") == base


def test_a_base_outside_the_history_gets_the_exact_merge_base_from_the_whole_graph(
    pull: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work, _ = pull
    origin = tmp_path / "origin"
    git(origin, "checkout", "-q", "-b", "side", "main~14")
    side = commit(origin, "side")
    expected = git(origin, "merge-base", side, "merge")
    assert fetch_history.main([side], depths=(2, None)) == 0
    assert "whole graph" in capsys.readouterr().out
    assert git(work, "merge-base", side, "HEAD") == expected


def test_a_base_with_no_common_history_fails_loud(
    pull: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = tmp_path / "origin"
    git(origin, "checkout", "-q", "--orphan", "alien")
    alien = commit(origin, "alien")
    assert fetch_history.main([alien], depths=(2, None)) == 1
    assert "wrong base" in capsys.readouterr().err


def test_the_tool_asks_for_one_full_sha() -> None:
    assert fetch_history.main(["origin/main"]) == 2
    assert fetch_history.main([]) == 2
