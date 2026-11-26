# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1061: the gate finds the base result in the cache or computes it, and never skips.

Each case runs `tools/self_check_gate.py` as a process in a small git repository with two commits.
The results are the real ones of `tests/selfcheck_fixtures/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def with_topology(result: dict[str, Any]) -> dict[str, Any]:
    frame = result.get("frame")
    if not isinstance(frame, dict):
        return result
    count = frame["self_test"]["reply"]["files"]
    digest = hashlib.sha256((FIXTURES / "tiny/architecture-contract.json").read_bytes()).hexdigest()
    frame["contract_digest"] = digest
    frame["self_test"]["collect"]["contract_files"] = {"architecture-contract.json": digest}
    frame["topology"] = {
        "total": {"modules": count, "components": 0},
        "modules": [
            {"path": str(n), "name": str(n), "component": None, "ownership": "unowned"}
            for n in range(count)
        ],
        "components": [],
    }
    return result


def test_contract_scope_change_is_red_with_the_same_scanned_paths(
    tmp_path: Path, release_core: Path
) -> None:
    repo = tmp_path / "project"
    shutil.copytree(FIXTURES / "tiny", repo)
    (repo / "native").mkdir()
    (repo / "native" / "stub").write_text("")
    git(repo, "init", "-q")
    contract_file = repo / "architecture-contract.json"
    contract = json.loads(contract_file.read_text())
    contract["components"][0]["public"] = []
    contract["rules"][0]["kind"] = "no_component_cycles"
    results = []
    for name, package in [("base", "inventory.inventory"), ("pr", "inventory.inventory.stock")]:
        contract["components"][0]["packages"] = [package]
        contract_file.write_text(json.dumps(contract))
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", name)
        request = {
            "protocol": "archkeel-core-scan-1",
            "root": str(repo.resolve()),
            "config": "archkeel.toml",
            "topology": True,
        }
        done = subprocess.run(
            [str(release_core), "scan"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=120,
        )
        frame = json.loads(done.stdout)
        assert frame["status"] == "PASS", frame
        results.append({"frame": frame, "gaps": frame["gaps"], "exit_code": 0})
    before, after = (result["frame"]["topology"]["modules"] for result in results)
    assert [row["path"] for row in before] == [row["path"] for row in after]
    paths = []
    for name, result in zip(("base", "pr"), results, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(result))
        paths.append(path)
    done = subprocess.run(
        [sys.executable, str(GATE), "--result", str(paths[1]), "--base", "HEAD~1"],
        cwd=repo,
        env={**GIT_ENV, "BASE_RESULT": str(paths[0])},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "scope changed" in done.stdout
    results[1]["frame"]["contract_digest"] = results[0]["frame"]["contract_digest"]
    paths[1].write_text(json.dumps(results[1]))
    unchanged_digest = subprocess.run(
        done.args,
        cwd=repo,
        env={**GIT_ENV, "BASE_RESULT": str(paths[0])},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert unchanged_digest.returncode == 1, unchanged_digest.stdout
    assert "scope changed" in unchanged_digest.stdout


def test_equal_count_path_swap_is_growth(tmp_path: Path) -> None:
    base = with_topology(json.loads((FIXTURES / "base.json").read_text()))
    pr = json.loads(json.dumps(base))
    pr["frame"]["topology"]["modules"][0]["path"] = "another.rs"
    files = []
    for name, result in (("base", base), ("pr", pr)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(result))
        files.append(str(path))
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools/self_check_diff.py"), *files],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 1, done.stdout
    assert "scanned paths or contract scope differ" in done.stdout
    body = tmp_path / "body.txt"
    body.write_text("Ratchet growth: 1 items: the scanned paths changed on purpose\n")
    approved = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/self_check_diff.py"),
            *files,
            "--labels",
            "ratchet-lead",
            "--body-file",
            str(body),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert approved.returncode == 0, approved.stdout


def test_topology_row_order_does_not_change_scope() -> None:
    sys.path.insert(0, str(GATE.parent))
    from self_check_diff import condense

    base = with_topology(json.loads((FIXTURES / "base.json").read_text()))
    reordered = json.loads(json.dumps(base))
    reordered["frame"]["topology"]["modules"].reverse()
    assert condense(base)["scope"] == condense(reordered)["scope"]


def test_incomplete_topology_cannot_pass_the_gate(repo: Path) -> None:
    result = with_topology(json.loads((FIXTURES / "base.json").read_text()))
    result["frame"]["topology"]["total"]["modules"] += 1
    path = repo / "incomplete.json"
    path.write_text(json.dumps(result))
    done = subprocess.run(
        [sys.executable, str(GATE), "--result", str(path), "--no-compare"],
        cwd=repo,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 1, done.stdout
    assert "no complete scanned scope" in done.stdout


def test_missing_topology_cannot_pass_the_gate(repo: Path) -> None:
    result = json.loads((FIXTURES / "base.json").read_text())
    path = repo / "missing.json"
    path.write_text(json.dumps(result))
    for mode in ("--no-compare", "--report-only"):
        done = subprocess.run(
            [sys.executable, str(GATE), "--result", str(path), mode],
            cwd=repo,
            env=GIT_ENV,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert done.returncode == 1, done.stdout
        assert "no complete scanned scope" in done.stdout
    result = with_topology(result)
    result["frame"]["self_test"]["collect"]["contract_files"] = {}
    path.write_text(json.dumps(result))
    done = subprocess.run(
        [sys.executable, str(GATE), "--result", str(path), "--no-compare"],
        cwd=repo,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 1 and "no complete scanned scope" in done.stdout


def test_a_legacy_cached_base_uses_the_old_comparison(repo: Path) -> None:
    path = keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    result = json.loads(path.read_text())
    result["format"] = "selfcheck-v1"
    del result["scope"], result["contract_files"]
    path.write_text(json.dumps(result))
    done = gate(repo, "base.json", GITHUB_STEP_SUMMARY=str(repo / "summary.md"))
    message = (
        "scope comparison: base scope not in the v1 cache; it starts when main writes the v2 cache"
    )
    assert done.returncode == 0, done.stdout
    assert done.stdout.count(message) == 1 and "grown 0" in done.stdout
    assert (repo / "summary.md").read_text().strip() == message
    assert gate(repo, "plus-one-gap.json").returncode == 1
    result.update(format="selfcheck-v2", scope={})
    path.write_text(json.dumps(result))
    assert gate(repo, "base.json").returncode == 1


def test_a_base_without_scope_is_not_silently_accepted(repo: Path) -> None:
    done = gate(repo, "base.json", BASE_RESULT=str(FIXTURES / "base.json"))
    assert done.returncode == 1, done.stdout
    assert "scope changed" in done.stdout


def test_removed_gaps_with_changed_contract_inputs_are_growth(repo: Path) -> None:
    path = keep_base(repo, "plus-one-gap.json", git(repo, "rev-parse", "HEAD~1"))
    result = json.loads(path.read_text())
    result["contract_files"]["old-doc.md"] = "old"
    path.write_text(json.dumps(result))
    done = gate(repo, "base.json")
    assert done.returncode == 1
    assert "contract inputs changed while gaps were removed" in done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with a base commit and a head commit; `native/` is the same in both."""
    git(tmp_path, "init", "-q")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/lib.rs").write_text("// one\n")
    shutil.copy2(FIXTURES / "tiny/architecture-contract.json", tmp_path)
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
    result = with_topology(json.loads((FIXTURES / fixture).read_text(encoding="utf-8")))
    path.write_text(json.dumps(condense(result, sha, "tree")), encoding="utf-8")
    return path


def gate(
    repo: Path, fixture: str, *extra: str, base: str = "HEAD~1", **env: str
) -> subprocess.CompletedProcess[str]:
    result = with_topology(json.loads((FIXTURES / fixture).read_text(encoding="utf-8")))
    input_file = repo / "input-result.json"
    input_file.write_text(json.dumps(result))
    args = [sys.executable, str(GATE), "--result", str(input_file), "--base", base]
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
    assert done.stdout.splitlines()[-1] == "self-check gate: RED (exit 1)"


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
    base = repo / "input-base.json"
    base.write_text(json.dumps(with_topology(json.loads((FIXTURES / "base.json").read_text()))))
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
    assert saved["sha"] == git(repo, "rev-parse", "HEAD") and saved["format"] == "selfcheck-v2"
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


def test_a_symlinked_artifact_directory_is_red_and_its_base_is_not_read(repo: Path) -> None:
    """#1980: `git ls-files` shows nothing through a symlink, the path holds a planted base."""
    keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"), "base.json")
    (repo / "x").mkdir()
    (repo / "test-artifacts").rename(repo / "x/test-artifacts")
    (repo / "test-artifacts").symlink_to("x/test-artifacts")
    done = gate(repo, "plus-one-gap.json")
    assert done.returncode == 1, done.stdout
    assert "is a symlink" in done.stdout and "cache hit" not in done.stdout


def test_a_changed_scan_table_is_growth_against_the_cached_base(repo: Path) -> None:
    """#1980: the cached base keeps the `[scan]` table of its commit; the PR differs."""
    (repo / "native/archkeel.toml").write_text('[scan]\nroots = ["native"]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "scan")
    sha = git(repo, "rev-parse", "HEAD~1")
    base = json.loads(keep_base(repo, "base.json", sha).read_text())
    base["scan"] = {"roots": ["native", "src"]}
    (repo / "test-artifacts/selfcheck/base.json").write_text(json.dumps(base))
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "scope changed: the [scan] table differs" in done.stdout
    base["scan"] = {"roots": ["native"]}
    (repo / "test-artifacts/selfcheck/base.json").write_text(json.dumps(base))
    assert gate(repo, "base.json").returncode == 0


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
