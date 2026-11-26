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


def test_a_changed_test_file_selects_its_own_area_and_nothing_else() -> None:
    assert areas_of_change(["tests/test_cli_help.py"]) == ["CLI and core"]
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
    assert areas_of_change(["native/report/src/html.rs"]) == ["CLI and core", "reports"]


def test_parallel_jobs_follow_the_changed_paths() -> None:
    assert parallel_areas(["docs/readme.md"]) == []
    assert not rust_checks(["docs/readme.md"])
    assert parallel_areas(["native/report/src/html.rs"]) == ["CLI and core", "reports"]
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


def test_pr_and_main_share_jobs_and_the_required_gate_needs_them() -> None:
    workflows = ROOT / ".github/workflows"
    main = (workflows / "ci.yml").read_text()
    pr = (workflows / "pr-gate.yml").read_text()
    shared = (workflows / "area-checks.yml").read_text()
    assert "uses: ./.github/workflows/area-checks.yml" in main
    assert "uses: ./.github/workflows/area-checks.yml" in pr
    assert "name: PR gate\n    needs: [base, area-checks, windows-native]\n    if: always()" in pr
    assert shared.count("python3 tools/select_areas.py --job") == 2


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


def test_the_main_failures_are_in_the_fast_selection() -> None:
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:xdist",
            "-m",
            "not native_wheel and not slow",
            "tests/test_native_self_core_rows.py",
            "tests/test_cli_native_core_scan_work.py",
            "tests/test_cli_report_output.py",
            "tests/test_collector_false_pass_rust_own_file_method.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    for name in (
        "test_collect_hands_core_no_value_of_a_collector_type",
        "test_release_scan_at_64_mib_keeps_a_full_frame_under_300_mib",
        "test_native_static_page_stays_below_the_review_size_budget",
        "test_requires_receipt_distinguishes_matching_and_wrong_ports",
    ):
        assert name in done.stdout


def test_every_slow_file_is_in_an_area() -> None:
    assert all(area_of(name) is not None for name in SLOW_FILES)


def test_each_area_meets_its_floor_of_fast_tests() -> None:
    """The floor check of conftest runs in this collection; an unknown area is a usage error."""
    options = ["--collect-only", "-q", "--tier", "fast", "-m", "not native_wheel and not slow"]
    options += ["-p", "no:xdist"]
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
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--area",
            area,
            "--tier",
            "fast",
            "-m",
            "not slow",
        ],
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


def test_a_shared_test_helper_the_area_table_and_its_floors_select_every_area() -> None:
    """AD-736: they can change any area, so no area may be left out."""
    for path in (
        "tests/conftest.py",
        "tests/areas.py",
        "tests/area_floors.json",
        "tests/core_support.py",
        "tests/python_site_plants.py",
        "tests/rust_param_review_plants.py",
    ):
        assert areas_of_change([path]) == list(AREAS), path
    assert areas_of_change(["tests/test_cli_help.py"]) == ["CLI and core"]


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


def _collect(
    tier: list[str], area: str, plus: str = "0", markers: str = "not slow"
) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:xdist", "--area", area]
        + tier
        + ["-m", markers],
        cwd=ROOT,
        env={"ARCHKEEL_FLOOR_PLUS": plus, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


def test_the_tier_option_decides_which_floor_applies_not_a_substring_of_the_marker_expression() -> (
    None
):
    """AD-736: --tier pr|fast|full. Without a tier, or with full, no floor is checked."""
    pr = "not slow and not debug_build and not heavy"
    assert _collect(["--tier", "pr"], "reports", markers=pr)[0] == 0
    code, text = _collect(["--tier", "pr"], "reports", plus="1000000", markers=pr)
    assert code != 0 and "pr tests" in text
    code, text = _collect(["--tier", "fast"], "reports", plus="1000000")
    assert code != 0 and "fast tests" in text
    # The marker expression says "not slow" in each case below; the tier alone decides.
    assert _collect([], "reports", plus="1000000")[0] == 0
    assert _collect(["--tier", "full"], "reports", plus="1000000")[0] == 0
    assert _collect(["--tier", "other"], "reports")[0] != 0


def test_the_make_targets_pass_their_tier() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    full = (ROOT / "tools/full.mk").read_text(encoding="utf-8")
    assert "$(FAST_TEST) --tier fast" in makefile and "--tier pr -m" in makefile
    assert "--tier full" in full
