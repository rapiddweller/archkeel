# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each project of `fixtures/` has a pinned result of the release core (AD-462).

A refused project is pinned as refused with its reason. When a collector starts to serve it, this
test fails and the author must update `fixtures/matrix.json`: the table shows the progress.
Never weaken a pinned verdict to make this test pass.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from core_support import run

from archkeel.cli import core_only
from tools.report_gallery import MATRIX, load_runs, summarize

FIXTURES = MATRIX.parent
RUNS = load_runs()


def _scan(run_entry: dict) -> dict:
    return tomllib.loads((FIXTURES / run_entry["root"] / _config(run_entry)).read_text())["scan"]


def _config(run_entry: dict) -> str:
    return run_entry.get("config") or "archkeel.toml"


def test_the_table_has_one_key_for_each_fixture_directory() -> None:
    on_disk = sorted(path.name for path in FIXTURES.iterdir() if path.is_dir())
    assert on_disk == sorted({run["fixture"] for run in RUNS})


def test_run_names_are_unique_and_safe_as_directory_names() -> None:
    names = [run["name"] for run in RUNS]
    assert len(names) == len(set(names))
    assert all(name.replace("-", "").replace("_", "").isalnum() for name in names)


@pytest.mark.parametrize("entry", RUNS, ids=lambda entry: entry["name"])
def test_language_and_contract_follow_the_project_config(entry: dict) -> None:
    scan = _scan(entry)
    assert entry["language"] == scan.get("language", "python")
    assert entry["contract"] == [scan["contract"]]
    assert all((FIXTURES / entry["root"] / path).is_file() for path in entry["contract"])


@pytest.mark.parametrize("entry", RUNS, ids=lambda entry: entry["name"])
def test_the_release_core_gives_the_pinned_result(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, entry: dict
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    arguments = [entry["command"], "--root", str(FIXTURES / entry["root"])]
    if entry.get("config"):
        arguments += ["--config", entry["config"]]
    code, envelope = run(*arguments)
    found = summarize(envelope)
    assert found == entry["expect"], "the core result changed: update fixtures/matrix.json"
    assert code == entry["expect"]["exit"]
