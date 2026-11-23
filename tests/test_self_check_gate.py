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


def keep_base(repo: Path, fixture: str, sha: str) -> None:
    """Put a base result for `sha` where the cache restore puts it."""
    sys.path.insert(0, str(GATE.parent))
    from self_check_diff import condense

    path = repo / "test-artifacts/selfcheck/result.json"
    path.parent.mkdir(parents=True)
    result = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    path.write_text(json.dumps(condense(result, sha, "tree")), encoding="utf-8")


def gate(
    repo: Path, fixture: str, *extra: str, old: int = 0, base: str = "HEAD~1", **env: str
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(GATE), "--result", str(FIXTURES / fixture), "--base", base]
    args += ["--old-exit", str(old), "--uv", "true", *extra]
    return subprocess.run(
        args, cwd=repo, env={**GIT_ENV, **env}, capture_output=True, text=True, timeout=120
    )


def test_a_cached_base_is_compared_and_equal_results_pass(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "base.json")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "cache hit" in done.stdout and "grown 0, removed 0" in done.stdout


def test_growth_against_the_cached_base_fails_and_a_disagreement_prints(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "plus-one-gap.json", old=0)
    assert done.returncode == 1, done.stdout
    assert "inventory.stock" in done.stdout
    assert "GATE DISAGREEMENT: the pin gate exits 0, the base comparison exits 1" in done.stdout


def test_the_pin_gate_failing_alone_is_a_disagreement_too(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "base.json", old=1)
    assert done.returncode == 1
    assert "GATE DISAGREEMENT: the pin gate exits 1, the base comparison exits 0" in done.stdout


def test_both_gates_red_is_no_disagreement(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "plus-one-gap.json", old=1)
    assert done.returncode == 1
    assert "DISAGREEMENT" not in done.stdout


def test_report_only_keeps_the_verdict_of_the_pin_gate(repo: Path) -> None:
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    done = gate(repo, "plus-one-gap.json", "--report-only")
    assert done.returncode == 0
    assert "GROWN" in done.stdout and "DISAGREEMENT" in done.stdout


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


def test_no_compare_writes_the_result_and_keeps_the_old_verdict(repo: Path) -> None:
    done = gate(repo, "base.json", "--no-compare", old=0)
    assert done.returncode == 0
    saved = json.loads((repo / "test-artifacts/selfcheck/result.json").read_text())
    assert saved["sha"] == git(repo, "rev-parse", "HEAD") and saved["format"] == "selfcheck-v1"
    assert gate(repo, "base.json", "--no-compare", old=1).returncode == 1


def test_an_unreadable_result_fails(repo: Path) -> None:
    (repo / "empty.json").write_text("")
    args = [
        sys.executable,
        str(GATE),
        "--result",
        "empty.json",
        "--base",
        "HEAD~1",
        "--old-exit",
        "0",
    ]
    done = subprocess.run(args, cwd=repo, env=GIT_ENV, capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "result is unusable" in done.stdout
