# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The project corpus of the core tests: each case is a small project tree in a Git repository.

A case is a fixture with a scan configuration or an entry of `tests/corpus/cases.json` (the
false-PASS probes and the Rust cases). An entry names a fixture tree, or no tree, and the files
that replace or add to it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
CASES_FILE = REPOSITORY / "tests" / "corpus" / "cases.json"


@dataclass(frozen=True, slots=True)
class Case:
    """One project: a fixture tree (or `""`: an empty tree), its committed files and an overlay."""

    id: str
    fixture: str
    base_files: dict[str, str | None] = field(default_factory=dict)
    files: dict[str, str | None] = field(default_factory=dict)


def corpus_cases() -> list[Case]:
    """Every fixture with a scan configuration, then each case of `tests/corpus/cases.json`."""
    fixtures = [
        Case(f"fixture/{directory.name}", f"fixtures/{directory.name}")
        for directory in sorted((REPOSITORY / "fixtures").iterdir())
        if (directory / "archkeel.toml").is_file()
    ]
    return [*fixtures, *listed_cases()]


def listed_cases() -> list[Case]:
    """The cases of `cases.json`; a file text `{"text": key}` is in its shared `texts` table."""
    stored = json.loads(CASES_FILE.read_text())
    texts = stored["texts"]
    cases = []
    for entry in stored["cases"]:
        for key in ("base_files", "files"):
            entry[key] = {
                path: texts[text["text"]] if isinstance(text, dict) else text
                for path, text in entry.get(key, {}).items()
            }
        cases.append(Case(**entry))
    return cases


def case(name: str) -> Case:
    return next(found for found in corpus_cases() if found.id == name)


def _apply(root: Path, files: Mapping[str, str | None]) -> None:
    for relative, content in files.items():
        target = root / relative
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def commit_tree(root: Path, *forced: str) -> str:
    """Commit every file below `root` in a new Git repository and return the commit.

    A path in `forced` is added although a rule of `.gitignore` excludes it.
    """
    git = ["git", "-c", "user.email=qa@example.invalid", "-c", "user.name=QA"]
    git += ["-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
    # A fixed date gives the same commit, so a binding to the source identity is stable.
    date = "2026-01-01T00:00:00+00:00"
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    steps = [["init", "-q", "-b", "main"], ["add", "-A"]]
    steps += [["add", "--force", path] for path in forced]
    steps += [["commit", "-q", "--allow-empty", "-m", "base"]]
    for arguments in steps:
        subprocess.run([*git, *arguments], cwd=root, check=True, capture_output=True, env=env)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


@contextmanager
def materialized(case: Case) -> Iterator[Path]:
    """The case in a new Git repository: base files committed, then the overlay applied."""
    with tempfile.TemporaryDirectory(prefix="archkeel-corpus-") as temporary:
        root = Path(temporary) / (Path(case.fixture).name or "case")
        if case.fixture:
            ignore = shutil.ignore_patterns(".dart_tool", "build")
            shutil.copytree(REPOSITORY / case.fixture, root, ignore=ignore)
        else:
            root.mkdir()
        modules = (root / "resolver-inputs").is_dir()
        if modules:
            shutil.copytree(root / "resolver-inputs", root / "node_modules")
        _apply(root, case.base_files)
        commit_tree(root, *(["node_modules"] if modules else []))
        _apply(root, case.files)
        yield root
