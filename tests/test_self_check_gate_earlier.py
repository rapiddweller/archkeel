# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The base result of a missing cache entry (#2077, AD-1145): run on real git and the real gate."""

# ruff: noqa: F811 - the imported fixture `repo` is the parameter of each test
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_self_check_gate import gate, git, keep_base, repo  # noqa: F401

# #2077: main CI has not saved the entry of the base commit yet; the entry of an earlier main
# commit is reused only when no input of the result differs between the two commits.
INPUT_FILES = (
    "native/lib.rs",
    "tools/rustc-facts/driver.rs",
    "src/archkeel/shell.py",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "tools/self_check_diff.py",
)
UNRELATED_FILES = ("docs/guide.md", "tests/test_x.py", "tools/other.py")


def earlier_repo(repo: Path, changed: str, link: bool = False) -> None:
    """Commits: earlier (all inputs), base (`changed` differs), head. The entry is earlier's."""
    for name in (*INPUT_FILES, *UNRELATED_FILES):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "earlier")
    earlier = git(repo, "rev-parse", "HEAD")
    target = repo / changed
    target.parent.mkdir(parents=True, exist_ok=True)
    if link:
        target.symlink_to("docs")
    else:
        target.write_text("two\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    (repo / "head.txt").write_text("h\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "pr")
    saved = json.loads(keep_base(repo, "base.json", earlier).read_text())
    saved["tree"] = git(repo, "rev-parse", f"{earlier}:native")
    (repo / "test-artifacts/selfcheck/base.json").write_text(json.dumps(saved))


@pytest.mark.parametrize("changed", UNRELATED_FILES)
def test_an_earlier_entry_with_equal_inputs_stands_for_the_missing_base(
    repo: Path, changed: str
) -> None:
    earlier_repo(repo, changed)
    done = gate(repo, "base.json")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "reusing the entry of" in done.stdout and "no input differs" in done.stdout
    assert "computing it in a worktree" not in done.stdout
    kept = json.loads((repo / "test-artifacts/selfcheck/compared-base.json").read_text())
    assert kept["sha"] == git(repo, "rev-parse", "HEAD~1")
    assert kept["reused_from"] == git(repo, "rev-parse", "HEAD~2")


@pytest.mark.parametrize("changed", INPUT_FILES)
def test_an_earlier_entry_with_a_different_input_is_never_reused(repo: Path, changed: str) -> None:
    """The base is computed. This repository has no core, so the gate fails: no false green."""
    earlier_repo(repo, changed)
    done = gate(repo, "base.json")
    assert done.returncode == 1, done.stdout
    assert "reusing" not in done.stdout and "computing it in a worktree" in done.stdout
    assert "scan took" in done.stdout


def test_an_earlier_entry_that_names_another_tree_is_never_reused(repo: Path) -> None:
    earlier_repo(repo, "docs/guide.md")
    path = repo / "test-artifacts/selfcheck/base.json"
    saved = json.loads(path.read_text())
    saved["tree"] = "0" * 40
    path.write_text(json.dumps(saved))
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "reusing" not in done.stdout


@pytest.mark.parametrize("sha", ["", "HEAD", "--output=x", "f" * 40, "abc"])
def test_an_entry_of_no_known_commit_is_a_miss(repo: Path, sha: str) -> None:
    earlier_repo(repo, "docs/guide.md")
    path = repo / "test-artifacts/selfcheck/base.json"
    saved = json.loads(path.read_text())
    saved["sha"] = sha
    path.write_text(json.dumps(saved))
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "reusing" not in done.stdout
    assert not (repo / "x").exists() and not (repo / "--output=x").exists()


def test_a_reused_entry_still_finds_growth(repo: Path) -> None:
    earlier_repo(repo, "docs/guide.md")
    done = gate(repo, "plus-one-gap.json")
    assert done.returncode == 1 and "reusing the entry of" in done.stdout
    assert "inventory.stock" in done.stdout


def test_a_cache_hit_and_a_computed_miss_name_their_cost(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    assert "scan took" not in gate(repo, "base.json").stdout
    (repo / "test-artifacts/selfcheck/base.json").unlink()
    assert "scan took" in gate(repo, "base.json").stdout


DEEP = "/".join(["d"] * 101) + "/file.txt"


@pytest.mark.parametrize(
    ("changed", "link"),
    [
        (".cargo/config.toml", False),
        ("fixtures/x/.cargo/config", False),
        ("docs/linked", True),
        (DEEP, False),
    ],
)
def test_a_repository_wide_input_of_the_scan_is_never_reused(
    repo: Path, changed: str, link: bool
) -> None:
    """The Rust walk reads every `.cargo` config and link of the repository (Codex, #2078)."""
    earlier_repo(repo, changed, link)
    done = gate(repo, "base.json")
    assert done.returncode == 1, done.stdout
    assert "reusing" not in done.stdout and "computing it in a worktree" in done.stdout


def test_a_changed_file_name_that_is_not_utf8_does_not_crash_the_gate(repo: Path) -> None:
    earlier_repo(repo, "docs/guide.md")
    # The index holds the name as bytes, so the test needs no file system that accepts it.
    done_blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=repo, input=b"x\n", capture_output=True
    )
    blob = done_blob.stdout.decode().strip()
    name = b"docs/odd-\xff.md"
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", b"100644," + blob.encode() + b"," + name],
        cwd=repo,
        check=True,
    )
    git(repo, "commit", "-qm", "odd name")
    (repo / "after.txt").write_text("a\n")
    git(repo, "add", "after.txt")
    git(repo, "commit", "-qm", "after")
    done = gate(repo, "base.json", base="HEAD~1")
    assert "Traceback" not in done.stderr, done.stderr
    assert "reusing the entry of" in done.stdout, done.stdout
