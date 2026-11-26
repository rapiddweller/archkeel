# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1062: the PR gate fetches the pinned real projects only when a change can alter their result.

Consumer: a PR author whose collector change turns a real project from PASS into UNKNOWN. The
fixture matrix pins that result, but the two network fixtures need the fetch. Only the paths below
turn the fetch on, and the area job of the CLI tests is the only one that receives it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from areas import fetch_sources

from tools import select_areas

ROOT = Path(__file__).parents[1]
AREA_CHECKS = (ROOT / ".github/workflows/area-checks.yml").read_text(encoding="utf-8")
FETCHING = "steps.fetch.outputs.decision == 'fetch'"


def test_a_change_that_can_alter_a_real_project_fetches_its_source() -> None:
    for path in (
        "native/python/src/survey/hazards_comprehension.rs",
        "native/dart/src/lib.rs",
        "fixtures/matrix.json",
        "fixtures/N-fastapi-realworld/SOURCE.json",
        "tools/fixture_source.py",
        ".github/workflows/area-checks.yml",
    ):
        assert fetch_sources([path]), path


def test_other_changes_stay_offline() -> None:
    for path in ("docs/known-limits.md", "src/archkeel/cli/main.py", "tests/areas.py", "README.md"):
        assert not fetch_sources([path]), path
    assert not fetch_sources([])


def test_the_selector_prints_the_decision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for paths, expected in ((["native/core/src/main.rs"], "fetch"), (["docs/a.md"], "skip")):
        monkeypatch.setattr(select_areas, "changed", lambda base, paths=paths: paths)
        assert select_areas.main(["--fetch", "base"]) == 0
        assert capsys.readouterr().out == f"{expected}\n"


def _steps() -> list[str]:
    return re.split(r"\n(?=      - name: )", AREA_CHECKS.split("\n  native:\n")[0])[1:]


def test_the_fetch_variable_is_set_in_one_step_that_follows_the_decision() -> None:
    setting = [step for step in _steps() if "ARCHKEEL_FETCH_SOURCES" in step]
    assert len(setting) == 1
    assert f"if: {FETCHING}" in setting[0]
    assert AREA_CHECKS.count("ARCHKEEL_FETCH_SOURCES") == 1


def test_the_decision_runs_for_a_pull_request_in_the_cli_area_only() -> None:
    [decision] = [step for step in _steps() if "id: fetch" in step]
    assert "matrix.area == 'CLI and core'" in decision
    assert "inputs.base != ''" in decision
    assert 'select_areas.py --fetch "$BASE"' in decision
    # The answer is checked: a crash or a stray text never skips the fetch silently.
    assert "set -euo pipefail" in decision and "fetch | skip) ;;" in decision


def test_the_sources_come_from_the_cache_that_the_gallery_fills() -> None:
    # `restore` only: a miss in a PR saves no second copy in its scope (`pages.yml` saves).
    [restore] = [step for step in _steps() if "name: Restore the pinned sources" in step]
    assert "actions/cache/restore@" in restore
    assert not [step for step in _steps() if "actions/cache@" in step]
    pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert f"if: {FETCHING}" in restore
    for line in (
        "path: test-artifacts/source-cache",
        "key: gallery-sources-${{ hashFiles('fixtures/*/SOURCE.json') }}",
    ):
        assert line in restore and line in pages


def test_the_selector_exits_non_zero_on_a_bad_ref() -> None:
    done = subprocess.run(
        ["python3", "tools/select_areas.py", "--fetch", "no-such-ref"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0 and done.stdout == ""


def _decide(base: str, tmp_path: Path) -> tuple[int, str]:
    """Run the `run:` script of the decision step as the job does."""
    [decision] = [step for step in _steps() if "id: fetch" in step]
    script = decision.split("run: |\n", 1)[1]
    script = "\n".join(line[10:] for line in script.splitlines())
    output = tmp_path / "output"
    output.touch()
    env = {**os.environ, "BASE": base, "GITHUB_OUTPUT": str(output)}
    done = subprocess.run(
        ["bash", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    return done.returncode, output.read_text()


def test_the_decision_step_fails_when_the_selector_fails(tmp_path: Path) -> None:
    code, written = _decide("no-such-ref", tmp_path)
    assert code != 0 and written == ""


def test_the_decision_step_writes_exactly_fetch_or_skip(tmp_path: Path) -> None:
    code, written = _decide("HEAD", tmp_path)
    assert code == 0 and written == "decision=skip\n"
