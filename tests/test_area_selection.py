# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-674: the PR tier selects test areas from the changed paths, and no area may run empty."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from areas import AREAS, SLOW_FILES, area_of, areas_of_change, parallel_areas, rust_checks

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("cli_selection", ["run", "no matching paths"])
def test_parallel_area_jobs_replace_the_base_area_tests(tmp_path: Path, cli_selection: str) -> None:
    calls = tmp_path / "calls"
    uv = tmp_path / "uv"
    uv.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{calls}"\n'
        'case "$*" in\n'
        f'  *"--job CLI and core"*) echo "{cli_selection}";;\n'
        '  *"tools/select_areas.py"*) echo "--area reports --area \\"self-check and CI\\"";;\n'
        "esac\n"
    )
    uv.chmod(0o755)
    overrides = tmp_path / "Makefile"
    overrides.write_text(
        ".PHONY: core browser-runtime-install\ncore browser-runtime-install:\n\t@:\n"
    )
    command = [
        "make",
        "-f",
        str(ROOT / "Makefile"),
        "-f",
        str(overrides),
        "pr-selected-test",
        f"UV={uv}",
    ]
    parallel = subprocess.run(
        [*command, "PR_PARALLEL=1"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert parallel.returncode == 0, parallel.stderr
    assert not calls.exists()
    local = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert local.returncode == 0, local.stderr
    assert "python -m pytest" in calls.read_text()


def test_a_changed_test_file_selects_its_own_area_and_nothing_else() -> None:
    assert areas_of_change(["tests/test_cli_help.py"]) == ["CLI and core"]
    assert areas_of_change(["tests/test_collector_native_rust_impl_oracle.py"]) == [
        "native collector evidence"
    ]
    assert areas_of_change(["tests/test_collector_native_catalog.py"]) == [
        "native collector evidence"
    ]
    assert areas_of_change(["tests/test_collector_native_scaling.py"]) == ["native collectors"]
    assert areas_of_change(["tests/test_collector_native_scaling_sites.py"]) == [
        "native collector evidence"
    ]
    assert areas_of_change(["tests/test_native_self_core_rows.py"]) == ["core scans"]
    assert areas_of_change(["tests/test_cli_native_core_scan_large.py"]) == ["core scans"]
    assert areas_of_change(["tests/test_report_gallery.py"]) == ["reports"]


def test_a_path_that_no_rule_names_selects_every_area() -> None:
    assert areas_of_change(["something/new.bin"]) == list(AREAS)
    assert areas_of_change(["tests/test_not_in_any_area.py"]) == list(AREAS)
    assert areas_of_change(["uv.lock"]) == list(AREAS)


def test_a_source_change_selects_the_areas_that_it_can_reach() -> None:
    for path in (
        "native/python/src/lib.rs",
        "native/core/src/main.rs",
        "native/model/src/direction.rs",
        "native/eval/src/scoped_requires_tests.rs",
        "src/archkeel/cli/native_scan.py",
        "Makefile",
        ".github/workflows/pr-gate.yml",
    ):
        assert areas_of_change([path]) == list(AREAS)
    assert areas_of_change(["native/report/src/html.rs"]) == [
        "core scans",
        "CLI and core",
        "reports",
    ]


def test_parallel_jobs_follow_the_changed_paths() -> None:
    assert parallel_areas(["docs/readme.md"]) == ["self-check and CI"]
    assert parallel_areas(["tools/self_check_summary.py"]) == ["reports", "self-check and CI"]
    assert parallel_areas([]) == ["self-check and CI"]
    assert not rust_checks(["docs/readme.md"])
    assert parallel_areas(["native/report/src/html.rs"]) == [
        "core scans",
        "CLI and core",
        "reports",
    ]
    assert rust_checks(["native/report/assets/explorer/explorer.html"])
    assert "collectors" in parallel_areas(["native/model/src/direction.rs"])
    assert "CLI and core" in parallel_areas(["native/collect/src/lib.rs"])
    assert parallel_areas(["Makefile"]) == list(AREAS)
    assert rust_checks(["Makefile"])


def test_job_selector_reports_empty_and_rejects_unknown_areas(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import select_areas

    monkeypatch.setattr(select_areas, "changed", lambda base: ["docs/readme.md"])
    assert select_areas.main(["--job", "reports", "base"]) == 0
    assert capsys.readouterr().out == "no matching paths\n"
    with pytest.raises(ValueError, match="unknown test area"):
        select_areas.main(["--job", "missing", "base"])


@pytest.mark.parametrize("area", ["reports", "self-check and CI"])
def test_tool_changes_run_each_selected_area_job(
    area: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import select_areas

    monkeypatch.setattr(select_areas, "changed", lambda base: ["tools/self_check_summary.py"])
    assert select_areas.main(["--job", area, "base"]) == 0
    assert capsys.readouterr().out == "run\n"


def test_pr_aggregate_refuses_failed_or_skipped_jobs() -> None:
    workflow = (ROOT / ".github/workflows/pr-gate.yml").read_text()
    script = workflow.split("      - name: Require every check\n", 1)[1].split(
        "        run: |\n", 1
    )[1]
    for results, expected in (
        ("success success", 0),
        ("success failure", 1),
        ("success skipped", 1),
    ):
        done = subprocess.run(
            ["bash", "-c", script],
            env={**os.environ, "RESULTS": results},
            capture_output=True,
            check=False,
        )
        assert done.returncode == expected


def _collect(*arguments: str) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:xdist", *arguments],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


def test_an_area_that_is_empty_after_the_marker_filter_fails_also_beside_a_full_one() -> None:
    """AD-1250: `-m slow` leaves tests only in the areas that own a slow file."""
    slow = sorted({area_of(name) for name in SLOW_FILES})
    quiet = sorted(set(AREAS) - set(slow))
    assert slow and quiet
    code, text = _collect("--area", slow[0], "-m", "slow")
    assert code == 0, text[-600:]
    code, text = _collect("--area", quiet[0], "-m", "slow")
    assert code != 0 and "selects no tests" in text
    code, text = _collect("--area", slow[0], "--area", quiet[0], "-m", "slow")
    assert code != 0 and f"{quiet[0]}" in text and "selects no tests" in text


def test_a_test_session_under_make_never_builds_the_shared_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1205: with `ARCHKEEL_REQUIRE_PREBUILT` a missing core fails; it is never rebuilt."""
    from core_support import prebuilt_core

    binary = tmp_path / "archkeel-core"
    monkeypatch.delenv("ARCHKEEL_REQUIRE_PREBUILT", raising=False)
    assert prebuilt_core(binary) is None
    monkeypatch.setenv("ARCHKEEL_REQUIRE_PREBUILT", "1")
    with pytest.raises(pytest.fail.Exception, match="make core"):
        prebuilt_core(binary)
    binary.write_text("x")
    assert prebuilt_core(binary) == binary
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ARCHKEEL_REQUIRE_PREBUILT=1 $(UV) run" in makefile
    assert "fast-test: core" in makefile and "pr-selected-test: core" in makefile


def test_a_shared_test_helper_and_the_area_table_select_every_area() -> None:
    """AD-736: they can change any area, so no area may be left out."""
    for path in (
        "tests/conftest.py",
        "tests/areas.py",
        "tests/core_support.py",
        "tests/python_site_plants.py",
        "tests/rust_param_review_plants.py",
    ):
        assert areas_of_change([path]) == list(AREAS), path


def test_select_areas_reads_the_diff_without_rename_detection(tmp_path: Path) -> None:
    """AD-736: a rename of a helper lists the old and the new path, so each one selects."""
    sys.path.insert(0, str(ROOT / "tools"))
    from select_areas import changed

    def run(*arguments: str) -> None:
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, *arguments], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q", "-b", "main")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/core_support.py").write_text("x = 1\n" * 30)
    run("add", "-A")
    run("commit", "-q", "-m", "base")
    run("checkout", "-q", "-b", "topic")
    run("mv", "tests/core_support.py", "tests/core_help.py")
    run("commit", "-q", "-am", "rename")
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert sorted(changed("main")) == ["tests/core_help.py", "tests/core_support.py"]
    finally:
        os.chdir(previous)
