# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The corpus of the dual run (AD-360): the cases and their trees.

A case is a fixture, a report variant of the demo catalog, a golden case root or an entry of
`tests/dual_run/cases.json` (the false-PASS probes and the Rust cases). The oracle keeps the case,
so it runs without the code that made it.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from tools.dual_run_oracle import ORACLE_DIR, oracle_file

REPOSITORY = Path(__file__).resolve().parent.parent
BENCH_DIR = REPOSITORY / "test-artifacts" / "dual-run" / "bench"
CASES_FILE = ORACLE_DIR / "cases.json"


@dataclass(frozen=True, slots=True)
class Case:
    """One project of the corpus: a fixture tree (or `""`: an empty tree, or a path at a pinned
    `commit`), its scan configuration, an overlay and an optional collector of its own."""

    id: str
    fixture: str
    config: str = "archkeel.toml"
    baseline: str | None = None
    base_files: dict[str, str | None] = field(default_factory=dict)
    files: dict[str, str | None] = field(default_factory=dict)
    bench: bool = False
    commit: str | None = None
    # `{python}`, `{repository}` and `{rust_collector}` are replaced before the run.
    collector_argv: list[str] | None = None
    pinned: bool = False


# --- Corpus ----------------------------------------------------------------------------------


def corpus_cases() -> list[Case]:
    """Every fixture with a scan configuration, every report variant of the demo catalog, every
    golden case root that is not a fixture and each case of `tests/dual_run/cases.json` (the
    false-PASS probes and the Rust cases). The oracle keeps each case's overlay."""
    catalog = importlib.import_module("fixtures.architecture_demo").CATALOG
    cases: list[Case] = []
    fixture_roots: set[str] = set()
    for directory in sorted((REPOSITORY / "fixtures").iterdir()):
        if (directory / "archkeel.toml").is_file():
            fixture_roots.add(f"fixtures/{directory.name}")
            cases.append(Case(f"fixture/{directory.name}", f"fixtures/{directory.name}"))
    for variant in catalog:
        if variant.evidence or variant.check or variant.view or variant.explore:
            continue
        against = variant.against
        if against is not None and against.root != ".":
            continue
        cases.append(
            Case(
                f"demo/{variant.id}",
                str(variant.fixture.resolve().relative_to(REPOSITORY)),
                variant.config,
                variant.baseline,
                dict(against.base_files) if against is not None else {},
                dict(variant.files),
            )
        )
    for language in ("python", "typescript"):
        for entry in json.loads((REPOSITORY / f"tests/golden/{language}/cases.json").read_text()):
            root = entry["root"]
            if root in fixture_roots or not (REPOSITORY / root / "archkeel.toml").is_file():
                continue
            fixture_roots.add(root)
            cases.append(Case(f"golden/{language}-{Path(root).name}", root))
    return [*cases, *listed_cases()]


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


def bench_case(value: str) -> Case:
    """`NAME=PATH[:CONFIG]` of a local bench project; its oracle is never committed."""
    name, _, location = value.partition("=")
    path, _, config = location.partition(":")
    resolved = str(Path(path).expanduser().resolve())
    return Case(f"bench/{name}", resolved, config or "archkeel.toml", bench=True)


def oracle_path(case: Case) -> Path:
    return oracle_file(BENCH_DIR if case.bench else ORACLE_DIR, case.id)


def _apply(root: Path, files: Mapping[str, str | None]) -> None:
    for relative, content in files.items():
        target = root / relative
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _source_tree(case: Case, root: Path) -> None:
    if case.commit is not None:
        root.mkdir()
        archive = subprocess.run(
            ["git", "archive", case.commit, case.fixture],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
        ).stdout
        subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    elif case.fixture:
        ignore = shutil.ignore_patterns(".dart_tool", "build")
        shutil.copytree(REPOSITORY / case.fixture, root, ignore=ignore)
    else:
        root.mkdir()


@contextmanager
def materialized(case: Case) -> Iterator[Path]:
    """The fixture in a new Git repository: base files committed, then the overlay applied."""
    if case.bench:
        yield Path(case.fixture)
        return
    with tempfile.TemporaryDirectory(prefix="archkeel-dual-") as temporary:
        root = Path(temporary) / (Path(case.fixture).name or "case")
        _source_tree(case, root)
        modules = (root / "resolver-inputs").is_dir()
        if modules:
            shutil.copytree(root / "resolver-inputs", root / "node_modules")
        _apply(root, case.base_files)
        git = ["git", "-c", "user.email=dual@example.invalid", "-c", "user.name=Dual"]
        git += ["-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
        # A fixed date gives the same commit, so a binding to the source identity is stable.
        date = "2026-01-01T00:00:00+00:00"
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run([*git, "init", "-q", "-b", "main"], cwd=root, check=True)
        subprocess.run([*git, "add", "-A"], cwd=root, check=True)
        if modules:
            subprocess.run([*git, "add", "--force", "node_modules"], cwd=root, check=True)
        subprocess.run(
            [*git, "commit", "-q", "--allow-empty", "-m", case.id], cwd=root, check=True, env=env
        )
        _apply(root, case.files)
        yield root
