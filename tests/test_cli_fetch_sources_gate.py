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
import subprocess
from pathlib import Path

import pytest
from areas import fetch_sources

from tools import select_areas

ROOT = Path(__file__).parents[1]


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


def test_the_selector_exits_non_zero_on_a_bad_ref() -> None:
    done = subprocess.run(
        ["python3", "tools/select_areas.py", "--fetch", "no-such-ref"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0 and done.stdout == ""


def _steps() -> list[str]:
    checks = (ROOT / ".github/workflows/area-checks.yml").read_text(encoding="utf-8")
    return re.split(r"\n(?=      - name: )", checks.split("\n  native:\n")[0])[1:]


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
