# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-360: a case pinned at a commit that a shallow checkout lacks fetches it."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools import dual_run


def _git(*arguments: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_a_pinned_commit_that_a_shallow_checkout_lacks_is_fetched(tmp_path: Path) -> None:
    # The nightly Demos job checks out one commit; a case pinned at an older one needs a fetch.
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", cwd=origin)
    (origin / "native").mkdir()
    (origin / "native" / "a.txt").write_text("old\n")
    _git("add", ".", cwd=origin)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "old", cwd=origin)
    pinned = _git("rev-parse", "HEAD", cwd=origin)
    (origin / "native" / "a.txt").write_text("new\n")
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "new", cwd=origin)
    clone = tmp_path / "clone"
    _git("clone", "-q", "--depth=1", origin.as_uri(), str(clone), cwd=tmp_path)
    case = dual_run.Case(id="pinned", fixture="native", commit=pinned)
    lacking = subprocess.run(
        ["git", "archive", pinned, "native"], cwd=clone, capture_output=True, check=False
    )
    assert lacking.returncode == 128
    dual_run.ensure_commits([case], clone)
    archive = subprocess.run(
        ["git", "archive", pinned, "native"], cwd=clone, capture_output=True, check=True
    )
    assert b"old" in archive.stdout
