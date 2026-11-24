# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1061: the gate finds the base result in the cache or computes it, and never skips.

Each case runs `tools/self_check_gate.py` as a process in a small git repository with two commits.
The results are the real ones of `tests/selfcheck_fixtures/`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GATE = ROOT / "tools/self_check_gate.py"
FIXTURES = Path(__file__).parent / "selfcheck_fixtures"
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with a base commit and a head commit; `native/` is the same in both."""
    git(tmp_path, "init", "-q")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/lib.rs").write_text("// one\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "other.txt").write_text("two\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "head")
    return tmp_path


def keep_base(repo: Path, fixture: str, sha: str, name: str = "base.json") -> Path:
    """Put a base result for `sha` where the cache restore puts it."""
    sys.path.insert(0, str(GATE.parent))
    from self_check_diff import condense

    path = repo / "test-artifacts/selfcheck" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    result = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    path.write_text(json.dumps(condense(result, sha, "tree")), encoding="utf-8")
    return path


def gate(
    repo: Path, fixture: str, *extra: str, base: str = "HEAD~1", **env: str
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(GATE), "--result", str(FIXTURES / fixture), "--base", base]
    args += ["--uv", "true", *extra]
    return subprocess.run(
        args, cwd=repo, env={**GIT_ENV, **env}, capture_output=True, text=True, timeout=120
    )


def test_a_cached_base_is_compared_and_equal_results_pass(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "base.json")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "cache hit" in done.stdout and "grown 0, removed 0" in done.stdout


def test_growth_against_the_cached_base_fails_and_the_last_line_says_red(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "plus-one-gap.json")
    assert done.returncode == 1, done.stdout
    assert "inventory.stock" in done.stdout
    assert "DISAGREEMENT" not in done.stdout
    assert done.stdout.splitlines()[-1] == "self-check gate: RED (exit 1)"
    grown = (repo / "test-artifacts/selfcheck/grown.txt").read_text()
    assert "inventory.stock" in grown and grown.count("\n") == 1


def test_a_green_gate_says_green_and_leaves_no_grown_file(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    (repo / "test-artifacts/selfcheck/grown.txt").write_text("stale\n")
    done = gate(repo, "base.json")
    assert done.returncode == 0 and done.stdout.splitlines()[-1] == "self-check gate: GREEN"
    assert not (repo / "test-artifacts/selfcheck/grown.txt").exists()


def test_the_job_summary_gets_the_grown_items(repo: Path, tmp_path: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    summary = tmp_path / "summary.md"
    gate(repo, "plus-one-gap.json", GITHUB_STEP_SUMMARY=str(summary))
    assert "1 grown items" in summary.read_text() and "inventory.stock" in summary.read_text()


def test_report_only_does_not_fail_on_growth_but_fails_on_a_tracked_base(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "plus-one-gap.json", "--report-only")
    assert done.returncode == 0
    assert "inventory.stock" in done.stdout and "make self-validate-native" in done.stdout


def test_a_base_that_cannot_be_computed_fails_and_gives_the_reason(repo: Path) -> None:
    """A cache miss computes the base. This repository has no core to build, so the gate fails."""
    done = gate(repo, "base.json")
    assert done.returncode == 1, done.stdout
    assert "cache miss" in done.stdout
    assert "base unavailable: the core of the base commit does not build" in done.stdout
    assert "missing-base-result.json is missing" in done.stdout


def test_a_cached_base_of_another_commit_is_a_miss(repo: Path) -> None:
    keep_base(repo, "base.json", "f" * 40)
    done = gate(repo, "base.json")
    assert done.returncode == 1
    assert "cache miss" in done.stdout


def test_an_unknown_base_ref_fails_and_names_the_command(repo: Path) -> None:
    done = gate(repo, "base.json", base="origin/nothing")
    assert done.returncode == 1
    assert "base unavailable" in done.stdout and "origin/nothing" in done.stdout


def test_a_base_result_file_replaces_the_cache_and_the_computation(repo: Path) -> None:
    base = FIXTURES / "base.json"
    done = gate(repo, "plus-one-gap.json", BASE_RESULT=str(base))
    assert done.returncode == 1 and "inventory.stock" in done.stdout


def test_a_head_equal_to_the_base_compares_with_itself(repo: Path) -> None:
    done = gate(repo, "base.json", base="HEAD")
    assert done.returncode == 0, done.stdout
    assert "grown 0, removed 0" in done.stdout


def test_no_compare_writes_the_result_and_still_requires_a_clean_one(repo: Path) -> None:
    done = gate(repo, "base.json", "--no-compare")
    assert done.returncode == 0
    saved = json.loads((repo / "test-artifacts/selfcheck/result.json").read_text())
    assert saved["sha"] == git(repo, "rev-parse", "HEAD") and saved["format"] == "selfcheck-v1"
    assert gate(repo, "refused.json", "--no-compare").returncode == 1


def test_an_unreadable_result_fails(repo: Path) -> None:
    (repo / "empty.json").write_text("")
    args = [
        sys.executable,
        str(GATE),
        "--result",
        "empty.json",
        "--base",
        "HEAD~1",
    ]
    done = subprocess.run(args, cwd=repo, env=GIT_ENV, capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "result is unusable" in done.stdout


@pytest.mark.parametrize("name", ["base.json", "result.json"])
def test_a_base_result_that_the_pr_commits_is_red(repo: Path, name: str) -> None:
    """BLOCKER: a fake base with the merge-base sha, added with `git add -f`, is not green."""
    path = keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"), name)
    fake = json.loads(path.read_text())
    fake["gaps"] = []
    path.write_text(json.dumps(fake))
    git(repo, "add", "-f", str(path.relative_to(repo)))
    git(repo, "commit", "-qm", "own base")
    done = gate(repo, "plus-one-gap.json")
    assert done.returncode == 1, done.stdout
    assert "git tracks files under test-artifacts/selfcheck/" in done.stdout
    assert "cache hit" not in done.stdout


def test_a_tracked_file_is_red_also_without_a_comparison(repo: Path) -> None:
    path = keep_base(repo, "base.json", "x" * 40, "other.json")
    git(repo, "add", "-f", str(path.relative_to(repo)))
    git(repo, "commit", "-qm", "own file")
    assert gate(repo, "base.json", "--no-compare").returncode == 1
    assert gate(repo, "base.json", "--report-only").returncode == 1


def test_an_untracked_result_file_is_not_a_base_candidate(repo: Path) -> None:
    """Only `base.json` (the cache restore path) is read; `result.json` is the gate output."""
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"), "result.json")
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "cache miss" in done.stdout


def test_the_label_comes_as_a_boolean_and_label_text_is_ignored(repo: Path, tmp_path: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    body = tmp_path / "body.txt"
    body.write_text("Ratchet growth: 1 items: the scan reads a new public name\n")
    env = {"RATCHET_BODY_FILE": str(body)}
    assert gate(repo, "plus-one-gap.json", **env).returncode == 1
    assert gate(repo, "plus-one-gap.json", RATCHET_LABELS="ratchet-lead", **env).returncode == 1
    assert gate(repo, "plus-one-gap.json", RATCHET_LABELED="yes", **env).returncode == 1
    done = gate(repo, "plus-one-gap.json", RATCHET_LABELED="true", **env)
    assert done.returncode == 0, done.stdout


PIN_NAMES = ("expected-gaps", "expected-growth", "shell-expected", "native_expected")


def test_no_pin_file_exists_and_no_code_path_opens_one() -> None:
    """AD-1064: the base comparison is the only gate, so a pin file must not come back."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    named = [name for name in listed if any(pin in Path(name).name for pin in PIN_NAMES)]
    assert named == [], "a pin file is back; the gate compares with the base commit (AD-1064)"
    code = [*(ROOT / "tools").glob("*.py"), *(ROOT / "src").rglob("*.py"), ROOT / "Makefile"]
    code += (ROOT / ".github/workflows").glob("*.yml")
    readers = [
        str(path.relative_to(ROOT))
        for path in code
        if any(pin in path.read_text(encoding="utf-8") for pin in PIN_NAMES)
    ]
    assert readers == []
