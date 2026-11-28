# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1450: `make self-validate-system` reuses a saved result for the same inputs and judges it.

A fake `uv` records each run of the scan. A hit runs no scan and the gate judges the saved result:
a FAIL in it is red as a fresh FAIL is. A miss, and a damaged entry, run the scan as before.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from timeout_support import run_bounded

ROOT = Path(__file__).parents[1]
GOOD: dict[str, Any] = {
    "rules": {"R": ["forbidden_dependency", "PASS"]},
    "details": {},
    "violations": {},
    "topology": {"total": {"modules": 1}, "modules": [{"path": "native/lib.rs"}]},
    "system": {
        "document": "docs/architecture/architecture-system.json",
        "parts": [{"id": "core", "config": "native/archkeel.toml", "rules": ["R"]}],
    },
    "self_test": {"collect": {"contract_files": {"native/archkeel.toml": "0" * 64}}},
}


def environment() -> dict[str, str]:
    return {
        **os.environ,
        "MAKEFLAGS": "",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    uv = tmp_path / "uv"
    scan = json.dumps(GOOD)
    uv.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '  *archkeel\\ report*) echo scan >> "$SCAN_LOG"; for a in "$@"; do '
        '[ "$prev" = --output ] && out=$a; prev=$a; done; '
        f"printf '%s' '{scan}' > \"$out\"; exit 0;;\n"
        f'  *) shift 3; exec "{sys.executable}" "$@";;\n'
        "esac\n"
    )
    uv.chmod(0o755)
    root = tmp_path / "repo"
    for name in ("tools/self_check_gate.py", "tools/self_scan_cache.py"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes((ROOT / name).read_bytes())
    for name, text in {
        ".gitignore": "__pycache__/\ntest-artifacts/\n",
        "native/lib.rs": "// one\n",
        "native/archkeel.toml": "[scan]\n",
        "docs/architecture/architecture-system.json": "{}\n",
    }.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", *step], cwd=root, env=environment(), check=True, capture_output=True)
    return root


def make(repo: Path, cache: Path | None) -> subprocess.CompletedProcess[str]:
    log = repo.parent / "scans.log"
    log.touch()
    env = {**environment(), "SCAN_LOG": str(log)}
    if cache is not None:
        env["ARCHKEEL_SELFSCAN_CACHE"] = str(cache)
    return run_bounded(
        ["make", "-f", str(ROOT / "Makefile"), "-o", "core", "self-validate-system"]
        + [f"UV={repo.parent / 'uv'}"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def scans(repo: Path) -> int:
    return len((repo.parent / "scans.log").read_text().split())


def saved(repo: Path, result: dict[str, Any]) -> Path:
    document = repo.parent / "saved.json"
    document.write_text(json.dumps(result))
    cache = repo.parent / "cache"
    tool = [sys.executable, "tools/self_scan_cache.py", "save", "--result", str(document)]
    done = subprocess.run([*tool, "--dir", str(cache)], cwd=repo, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return cache


def test_without_a_cache_the_scan_runs(repo: Path) -> None:
    done = make(repo, None)
    assert done.returncode == 0 and "GREEN" in done.stdout, done.stdout + done.stderr
    assert scans(repo) == 1


def test_the_saved_result_of_the_same_inputs_runs_no_scan_and_is_judged(repo: Path) -> None:
    done = make(repo, saved(repo, GOOD))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "self-scan: reused the result of" in done.stdout and "GREEN" in done.stdout
    assert scans(repo) == 0


def test_a_saved_fail_is_red_as_a_fresh_fail_is(repo: Path) -> None:
    failing = json.loads(json.dumps(GOOD))
    failing["rules"]["R"][1] = "FAIL"
    done = make(repo, saved(repo, failing))
    assert done.returncode != 0 and "rule R is FAIL" in done.stdout + done.stderr
    assert scans(repo) == 0


def test_a_changed_input_or_a_damaged_entry_runs_the_scan(repo: Path) -> None:
    cache = saved(repo, GOOD)
    (repo / "native/lib.rs").write_text("// two\n")
    assert make(repo, cache).returncode == 0
    assert scans(repo) == 1
    (repo / "native/lib.rs").write_text("// one\n")
    (cache / "entry.json").write_text("{damaged")
    done = make(repo, cache)
    assert done.returncode == 0 and scans(repo) == 2, done.stdout + done.stderr
