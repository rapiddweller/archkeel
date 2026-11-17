# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-674: the PR tier selects test areas from the changed paths, and no area may run empty."""

import subprocess
import sys
from pathlib import Path

import pytest
from areas import AREAS, SLOW_FILES, area_of, areas_of_change

ROOT = Path(__file__).parents[1]


def test_a_changed_test_file_selects_its_own_area_and_nothing_else() -> None:
    assert areas_of_change(["tests/test_cli_help.py"]) == ["CLI and core"]
    assert areas_of_change(["tests/test_report_gallery.py"]) == ["reports"]


def test_a_path_that_no_rule_names_selects_every_area() -> None:
    assert areas_of_change(["something/new.bin"]) == list(AREAS)
    assert areas_of_change(["tests/test_not_in_any_area.py"]) == list(AREAS)
    assert areas_of_change(["uv.lock"]) == list(AREAS)


def test_a_source_change_selects_the_areas_that_it_can_reach() -> None:
    assert areas_of_change(["native/python/src/lib.rs"]) == ["native collectors", "collectors"]
    assert areas_of_change(["native/core/src/main.rs"]) == ["CLI and core", "self-check and CI"]
    assert areas_of_change(["docs/readme.md", "native/report/src/html.rs"]) == [
        "CLI and core",
        "reports",
        "self-check and CI",
    ]


def test_every_slow_file_is_in_an_area() -> None:
    assert all(area_of(name) is not None for name in SLOW_FILES)


def test_each_area_meets_its_floor_of_fast_tests() -> None:
    """The floor check of conftest runs in this collection; an unknown area is a usage error."""
    options = ["--collect-only", "-q", "-m", "not native_wheel and not slow", "-p", "no:xdist"]
    areas = [item for area in AREAS for item in ("--area", area)]
    done = subprocess.run(
        [sys.executable, "-m", "pytest", *options, *areas],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
    wrong = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--area", "no such area"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert wrong.returncode != 0 and "not an area" in wrong.stdout + wrong.stderr


@pytest.mark.parametrize("area", sorted(AREAS))
def test_the_floor_of_an_area_fails_a_selection_that_falls_short(area: str) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--area", area, "-m", "not slow"],
        cwd=ROOT,
        env={"ARCHKEEL_FLOOR_PLUS": "1000000", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0 and "fast tests" in done.stdout + done.stderr


def test_a_test_session_under_make_never_builds_the_shared_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1205: with `ARCHKEEL_PREBUILT_CORE` a missing core fails the test; it is never rebuilt."""
    from core_support import prebuilt_core

    binary = tmp_path / "archkeel-core"
    monkeypatch.delenv("ARCHKEEL_PREBUILT_CORE", raising=False)
    assert prebuilt_core(binary) is None
    monkeypatch.setenv("ARCHKEEL_PREBUILT_CORE", "1")
    with pytest.raises(pytest.fail.Exception, match="make core"):
        prebuilt_core(binary)
    binary.write_text("x")
    assert prebuilt_core(binary) == binary
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ARCHKEEL_PREBUILT_CORE=1 $(UV) run" in makefile
    assert "fast-test: core" in makefile and "pr-selected-test: core" in makefile
