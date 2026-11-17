# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A fixture in a temporary Git repository, the way the tests run it (AD-462).

A TypeScript fixture keeps its resolver inputs in `resolver-inputs/`. The scan reads them as
`node_modules/`, so the copy renames them and commits them although `.gitignore` excludes the
folder (`tests/corpus_support.materialized` does the same). A planted change (an overlay of
files) is committed on top of that base, so the scan sees it as tracked source.
The tool decides nothing: it only prepares a tree for the core.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

RESOLVER_INPUTS = "resolver-inputs"
MODULES = "node_modules"
# A fixed date gives the same commit each time.
DATE = "2026-01-01T00:00:00+00:00"


def needs_copy(source: Path, overlay: Sequence[Mapping[str, str]] | None = None) -> bool:
    """True when the fixture cannot be scanned in place: resolver inputs or a planted change."""
    return bool(overlay) or (source / RESOLVER_INPUTS).is_dir()


def _git(root: Path, *arguments: str) -> None:
    git = ["git", "-c", "user.email=qa@example.invalid", "-c", "user.name=QA"]
    git += ["-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
    env = {**os.environ, "GIT_AUTHOR_DATE": DATE, "GIT_COMMITTER_DATE": DATE}
    subprocess.run([*git, *arguments], cwd=root, check=True, capture_output=True, env=env)


def _commit(root: Path, message: str, *forced: str) -> None:
    _git(root, "add", "-A")
    for path in forced:
        _git(root, "add", "--force", path)
    _git(root, "commit", "-q", "--allow-empty", "-m", message)


def apply_edit(root: Path, edit: Mapping[str, str]) -> None:
    """One planted change in the copy: `{"path", "append"}` adds text (it makes a missing file),
    `{"path", "old", "new"}` replaces the one place where `old` stands. Anything else is an error,
    so a plant that no longer fits its fixture fails loudly and never changes nothing."""
    target = root / edit["path"]
    if "append" in edit:
        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        text = before + edit["append"]
    elif "old" in edit and "new" in edit:
        before = target.read_text(encoding="utf-8")
        if before.count(edit["old"]) != 1:
            raise ValueError(f"{edit['path']}: the text to replace must stand once")
        text = before.replace(edit["old"], edit["new"])
    else:
        raise ValueError(f"unknown edit {sorted(edit)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@contextmanager
def fixture_tree(
    source: Path, overlay: Sequence[Mapping[str, str]] | None = None
) -> Iterator[Path]:
    """A copy of `source` in a new Git repository, with the planted edits committed on top.

    The source is never written.
    """
    with tempfile.TemporaryDirectory(prefix="archkeel-gallery-") as temporary:
        root = Path(temporary) / source.name
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(".dart_tool", "build"))
        modules = (root / RESOLVER_INPUTS).is_dir()
        if modules:
            shutil.copytree(root / RESOLVER_INPUTS, root / MODULES)
        _git(root, "init", "-q", "-b", "main")
        _commit(root, "base", *([MODULES] if modules else []))
        if overlay:
            for edit in overlay:
                apply_edit(root, edit)
            _commit(root, "plant")
        yield root
