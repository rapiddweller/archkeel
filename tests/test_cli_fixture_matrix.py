# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each project of `fixtures/` has a pinned result of the release core (AD-462).

A refused project is pinned as refused with its reason. When a collector starts to serve it, this
test fails and the author must update `fixtures/matrix.json`: the table shows the progress.
Never weaken a pinned verdict to make this test pass.
"""

from __future__ import annotations

import os
import tomllib
from contextlib import nullcontext
from pathlib import Path

import pytest
from core_support import run

from archkeel.cli import core_only
from tools import fixture_source
from tools.fixture_tree import fixture_tree, needs_copy
from tools.report_gallery import MATRIX, load_runs, summarize

FIXTURES = MATRIX.parent
RUNS = load_runs()
CACHE = Path(os.environ["ARCHKEEL_SOURCE_CACHE"]) if "ARCHKEEL_SOURCE_CACHE" in os.environ else None


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
    source = FIXTURES / entry["root"]
    if fixture_source.load(source) and not os.environ.get("ARCHKEEL_FETCH_SOURCES"):
        pytest.skip("the pinned source needs the network: the nightly run and the gallery fetch it")
    edits = entry.get("plant", {}).get("edits")
    # A fixture with resolver inputs or a planted change runs in a copy, as the gallery runs it.
    with (
        fixture_tree(source, edits, CACHE)
        if needs_copy(source, edits)
        else nullcontext(source) as root
    ):
        arguments = [entry["command"], "--root", str(root)]
        if entry.get("config"):
            arguments += ["--config", entry["config"]]
        code, envelope = run(*arguments)
    found = summarize(envelope)
    assert found == entry["expect"], "the core result changed: update fixtures/matrix.json"
    assert code == entry["expect"]["exit"]


def test_the_scope_line_counts_the_gaps_that_the_report_lists(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-644: the scope line and `holds` read the one class of each gap; the numbers agree.

    Truth of the fixture: three files that the collector cannot analyse leave the whole scope
    unknown; the loader call states its effect (`every_module`, AD-634).
    """
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _, envelope = run("report", "--root", str(FIXTURES / "golden-python" / "synthetic-gaps"))
    frame = envelope["frame"]
    reported = frame["explain"]["holds"]["gaps_total"]
    kinds = [gap["kind"] for gap in frame["collection_gaps"]]
    assert reported == len(kinds) == 4, kinds
    whole = kinds.count("exception_gap")
    assert frame["scope"] == (
        f"incomplete scope: the collector reports {reported} coverage gaps; "
        f"{whole} of them leave the whole scope unknown"
    )
