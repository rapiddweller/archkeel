# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Policy and release failures stop later Make steps, including parallel invocations."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from textwrap import dedent

import pytest
from areas import AREAS, area_of

ROOT = Path(__file__).parents[1]
GATE_STEPS = ["self-validate", "browser-architecture-check", "check", "build", "smoke"]
CI_CHECK_STEPS = [
    "ci-artifacts-clean",
    *GATE_STEPS,
    "typescript-compiler-check",
    "browser-graph-check",
    "demo-typescript",
    "browser-runtime-check",
    "typescript-libs-check",
    "report-timing",
]
CI_STEPS = [*CI_CHECK_STEPS, "mermaid"]


def _run_gate(
    tmp_path: Path,
    target: str,
    failed: str | None,
    jobs: int,
    separate_override: bool,
    base: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    steps = tmp_path / "steps"
    overrides = tmp_path / "Makefile"
    names = [*CI_STEPS, "against", "pr-test", "pr-report-test", "report-browser-tests"]
    recipes = []
    for name in names:
        output_guard = ""
        if name == "demo-typescript":
            output_guard = '\t@test "$(OUTPUT)" = test-artifacts/typescript-demo\n'
        recipes.append(
            f'{name}:\n\t@echo {name} >> "{steps}"\n\t@sleep 0.05\n\t@exit {int(name == failed)}\n'
            + output_guard
        )
    overrides.write_text(
        ("" if separate_override else f"include {ROOT / 'Makefile'}\n")
        + ".PHONY: "
        + " ".join([*names, "lint", "typecheck", "test"])
        + "\nlint typecheck test browser-runtime-install:\n\t@:\n"
        + "".join(recipes)
    )
    args = ["make", f"-j{jobs}"]
    if separate_override:
        args.extend(["-f", str(ROOT / "Makefile")])
    args.extend(["-f", str(overrides), target, f"BASE={base}"])
    result = subprocess.run(
        args,
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": "", "OUTPUT": "", "UV": "false", "NPM": "false"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result, steps.read_text().splitlines() if steps.exists() else []


@pytest.mark.parametrize("jobs", [1, 2])
@pytest.mark.parametrize("separate_override", [False, True])
@pytest.mark.parametrize("failed", [None, *GATE_STEPS])
def test_gate_validates_first_and_stops_after_each_failure(
    tmp_path: Path, jobs: int, separate_override: bool, failed: str | None
) -> None:
    result, steps = _run_gate(tmp_path, "gate", failed, jobs, separate_override)
    expected = GATE_STEPS if failed is None else GATE_STEPS[: GATE_STEPS.index(failed) + 1]
    assert steps == expected, result.stderr
    assert result.returncode == (0 if failed is None else 2), result.stderr


@pytest.mark.parametrize("jobs", [1, 2])
@pytest.mark.parametrize("failed", [None, "against", "check"])
def test_gate_uses_pinned_base_instead_of_duplicate_self_validation(
    tmp_path: Path, jobs: int, failed: str | None
) -> None:
    result, steps = _run_gate(tmp_path, "gate", failed, jobs, True, base="a" * 40)
    expected = ["against", "browser-architecture-check", "check", "build", "smoke"]
    if failed is not None:
        expected = expected[: expected.index(failed) + 1]
    assert steps == expected, result.stderr
    assert result.returncode == (0 if failed is None else 2), result.stderr


@pytest.mark.parametrize("jobs", [1, 2])
@pytest.mark.parametrize(
    "failed",
    [
        None,
        "self-validate",
        "ci-artifacts-clean",
        "report-timing",
        "typescript-compiler-check",
        "demo-typescript",
        "mermaid",
    ],
)
def test_ci_runs_acceptance_only_after_a_successful_gate(
    tmp_path: Path, jobs: int, failed: str | None
) -> None:
    result, steps = _run_gate(tmp_path, "ci", failed, jobs, True)
    expected = CI_STEPS if failed is None else CI_STEPS[: CI_STEPS.index(failed) + 1]
    assert steps == expected, result.stderr
    assert result.returncode == (0 if failed is None else 2), result.stderr


@pytest.mark.parametrize("jobs", [1, 2])
def test_ci_check_leaves_mermaid_to_its_parallel_workflow_job(tmp_path: Path, jobs: int) -> None:
    result, steps = _run_gate(tmp_path, "ci-check", None, jobs, True)
    assert result.returncode == 0, result.stderr
    assert steps == CI_CHECK_STEPS


@pytest.mark.parametrize("compiler_exit", [0, 1])
def test_uml_demo_checks_typescript_before_generating_reports(tmp_path: Path, compiler_exit: int):
    steps = tmp_path / "steps"
    overrides = tmp_path / "Makefile"
    overrides.write_text(
        f"include {ROOT / 'Makefile'}\n"
        "typescript-compiler-check:\n"
        f'\t@echo compiler >> "{steps}"\n'
        f"\t@exit {compiler_exit}\n"
    )
    runner = tmp_path / "uv"
    runner.write_text(f'#!/bin/sh\necho report >> "{steps}"\n')
    runner.chmod(0o755)
    result = subprocess.run(
        ["make", "-j2", "-f", str(overrides), "demo-uml", f"OUTPUT={tmp_path / 'reports'}"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": "", "UV": str(runner)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert steps.read_text().splitlines() == (
        ["compiler", "report"] if compiler_exit == 0 else ["compiler"]
    ), result.stderr
    assert result.returncode == (0 if compiler_exit == 0 else 2), result.stderr


def test_against_receives_the_exact_ci_base_and_stops_before_tests(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    runner = tmp_path / "uv"
    runner.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{steps}"\n'
        'case "$*" in *tools.against*) exit 1;; esac\n'
    )
    runner.chmod(0o755)
    result = subprocess.run(
        ["make", "-j2", "ci", f"BASE={'a' * 40}"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": "", "UV": str(runner)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert steps.read_text().splitlines() == [
        f"run --locked python -m tools.against --base {'a' * 40}",
    ]


@pytest.mark.parametrize("failed", [None, "against", "browser-architecture-check", "pr-test"])
def test_pr_gate_keeps_policy_and_stops_before_later_checks(tmp_path, failed):
    result, steps = _run_gate(tmp_path, "ci-pr-check", failed, 2, False, base="a" * 40)
    expected = ["against", "browser-architecture-check", "pr-test"]
    if failed is not None:
        expected = expected[: expected.index(failed) + 1]
    assert steps == expected
    assert result.returncode == (0 if failed is None else 2)


def test_pr_core_uses_representative_dart_and_flutter_checks() -> None:
    result = subprocess.run(
        ["make", "-n", "pr-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    command = result.stdout
    for selector in (
        "tests/test_dart_uml_acceptance.py::test_checkout_cli_report_fulfills_independent_target",
        "tests/test_dart_unknowns.py::test_no_show_import_hiding_a_real_crossing_is_unknown_not_pass",
        "tests/test_flutter_demo.py::test_flutter_target_has_agent_owned_responsibilities_and_closed_permissions",
        "tests/test_flutter_demo.py::test_flutter_mutations_keep_target_identical_and_change_only_dart_sources",
        "tests/test_flutter_demo.py::test_flutter_variant_reports_keep_pass_fail_unknown_and_coverage_distinct",
        "tests/test_flutter_demo.py::test_flutter_target_owns_three_meaningful_component_levels_and_all_modules",
        "tests/test_flutter_demo.py::test_flutter_target_pins_journey_signatures_member_scopes_and_flutter_inheritance",
    ):
        assert selector in command
    assert "tests/test_dart_unknowns.py " not in command
    assert "tests/test_flutter_demo.py " not in command


@pytest.mark.parametrize(
    "failed",
    [None, "browser-runtime-check", "browser-graph-check", "pr-report-test"],
)
def test_pr_report_gate_runs_logic_sample_and_propagates_failure(tmp_path, failed):
    result, steps = _run_gate(tmp_path, "ci-pr-report-check", failed, 2, False)
    expected = ["browser-runtime-check", "browser-graph-check", "pr-report-test"]
    if failed is not None:
        expected = expected[: expected.index(failed) + 1]
    assert steps == expected
    assert result.returncode == (0 if failed is None else 2)


def test_pr_report_sample_uses_two_loadfile_workers_and_keeps_selected_tests() -> None:
    result = subprocess.run(
        ["make", "-n", "pr-report-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    command = result.stdout
    assert "python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 -q" in command
    assert "--junitxml=test-artifacts/pytest/pr-report.xml" in command
    for selector in (
        "tests/test_graph_scene_protocol.py",
        "tests/test_atlas_deviation_boundary.py",
    ):
        assert selector in command
    core = subprocess.run(
        ["make", "-n", "pr-test"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    for selector in ("tests/test_saved_report.py", "tests/test_report_agent_json.py"):
        assert selector in core and selector not in command
    assert "tests/test_compass_project_report.py" not in command
    assert "tests/test_nest_realworld_project_report.py" not in command


@pytest.mark.parametrize("fail_pytest", [False, True])
def test_local_browser_target_installs_and_runs_only_the_smokes(
    tmp_path: Path, fail_pytest: bool
) -> None:
    calls = tmp_path / "uv-calls.jsonl"
    runner = tmp_path / "uv"
    runner.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['UV_CALLS'], 'a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if (\n"
        "    os.environ.get('FAIL_REPORT_PYTEST') == '1'\n"
        "    and 'pytest' in sys.argv\n"
        "    and 'browser' in sys.argv\n"
        "):\n"
        "    raise SystemExit(7)\n"
    )
    runner.chmod(0o755)
    result = subprocess.run(
        ["make", "report-browser"],
        cwd=ROOT,
        env={
            **os.environ,
            "OUTPUT": "",
            "UV": str(runner),
            "UV_CALLS": str(calls),
            "FAIL_REPORT_PYTEST": "1" if fail_pytest else "0",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    invocations = [json.loads(line) for line in calls.read_text().splitlines()]
    assert invocations[0] == [
        "run",
        "--locked",
        "--with",
        "playwright==1.62.0",
        "python",
        "-m",
        "playwright",
        "install",
        "--with-deps",
        "chromium",
    ]
    assert len(invocations) == 2
    assert invocations[1][:7] == [
        "run",
        "--locked",
        "--with",
        "playwright==1.62.0",
        "python",
        "-m",
        "pytest",
    ]
    assert "-m" in invocations[1] and "browser" in invocations[1]
    assert result.returncode == (2 if fail_pytest else 0), result.stderr


def test_ci_paths_avoid_playwright_and_browser_proof_but_local_report_tests_opt_in() -> None:
    for target in (
        "ci",
        "ci-check",
        "ci-core-check",
        "ci-report-check",
        "ci-pr-check",
        "ci-pr-static",
        "ci-pr-report-check",
        "pr-test",
        "pr-report-test",
        "full-test",
    ):
        result = subprocess.run(
            ["make", "-n", target],
            cwd=ROOT,
            env={**os.environ, "MAKEFLAGS": "", "OUTPUT": ""},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "playwright" not in result.stdout.lower(), target
        assert "tools.report_browser" not in result.stdout, target

    local = subprocess.run(
        ["make", "-n", "report-browser-tests"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert local.returncode == 0, local.stderr
    assert "playwright install --with-deps chromium" in local.stdout
    assert "pytest -m browser" in local.stdout

    full_shard = subprocess.run(
        ["make", "-n", "full-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert full_shard.returncode == 0, full_shard.stderr
    runtime_install = full_shard.stdout.index("npm ci --prefix tools/browser-runtime")
    test_run = full_shard.stdout.index("python -m pytest")
    assert runtime_install < test_run


def test_workflow_files_require_an_explicit_governance_change() -> None:
    assert {path.name for path in (ROOT / ".github/workflows").iterdir() if path.is_file()} == {
        "ci.yml",
        "full-verification.yml",
        "release.yml",
        "github-opened.yml",
        "github-opened-receipt.yml",
    }


def test_ci_workflow_keeps_fast_required_checks_and_routes_full_verification() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    parts = re.split(r"^  ([\w-]+):\n", workflow.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    jobs = dict(zip(parts[1::2], parts[2::2], strict=True))
    check = jobs["check"]
    assert "name: All checks passed" in check
    needs = "[changes, lint, architecture, tests, pr-report-check, mermaid, full-verification]"
    assert f"needs: {needs}" in check
    assert "if: ${{ always() }}" in check
    assert (
        "- name: Fail required check after workflow cancellation\n        if: cancelled()" in check
    )
    for area in ("lint", "architecture", "tests", "report", "mermaid", "full"):
        assert f"verify_area {area} " in check
    assert "continue-on-error" not in check
    assert "make report-pages" not in workflow
    full_call = jobs["full-verification"]
    assert "needs: changes" in full_call
    assert (
        "github.event_name == 'pull_request' && needs.changes.outputs.full == 'true'" in full_call
    )
    assert "uses: ./.github/workflows/full-verification.yml" in full_call
    assert "collector-safety-windows:" not in workflow
    assert "prune-report-artifacts:" not in workflow
    for job_id, area, command in (
        ("lint", "core", "make lint typecheck browser-architecture-check"),
        ("architecture", "core", "make against; else make self-validate"),
        ("tests", "core", 'make pr-test AREA="$AREA"'),
        ("pr-report-check", "report", "make pr-report-test"),
    ):
        job = jobs[job_id]
        assert "needs: changes" in job
        assert "github.event_name == 'pull_request' || github.event_name == 'push'" in job
        assert f"needs.changes.outputs.{area} == 'true'" in job
        assert "permissions:\n      contents: read" in job
        assert command in job
    assert "fail-fast: false" in jobs["tests"]
    assert "BASE: ${{ github.event.pull_request.base.sha }}" in jobs["architecture"]
    assert "Install Dart SDK" not in jobs["pr-report-check"]
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "needs.changes.outputs.mermaid == 'true'" in jobs["mermaid"]
    assert "run: make mermaid" in workflow

    full = (ROOT / ".github/workflows/full-verification.yml").read_text()
    for trigger in ("workflow_call:", "workflow_dispatch:", "schedule:"):
        assert trigger in full
    assert "run: make demos" in full
    assert "test-artifacts/report-timing/architecture.timing.json" in full
    assert "test-artifacts/report-browser/" not in full
    evidence = full.split("name: report-check-evidence", 1)[1].split("      - name:", 1)[0]
    assert "retention-days: 1" in evidence
    assert "test-artifacts/report-browser/" not in evidence
    safety = full.split("  collector-safety-windows:\n", 1)[1].split("\n  language-collectors:", 1)[
        0
    ]
    assert "runs-on: windows-latest" in safety
    assert 'UV_PYTHON: "3.11.12"' in safety
    assert "matrix:" not in safety
    collectors = full.split("  language-collectors:\n", 1)[1].split("\n  verified:", 1)[0]
    assert "runs-on: ubuntu-latest" in collectors
    assert 'UV_PYTHON: "3.12.10"' in collectors
    assert "matrix:" not in collectors
    assert "windows" not in collectors.lower()
    assert "setup-dart@" not in full
    assert "dart-setup" not in full
    assert "dart-native:" not in full
    assert "make dart-test TEST_WORKERS=4 SHELL=bash" in full
    assert "setup-dart@" not in workflow
    assert "dart-setup" not in workflow
    assert "if: always()" in full
    assert (
        "needs:\n      - full-suite-and-reports\n      - tests\n"
        "      - demos\n      - python-compat\n"
        "      - collector-safety-windows\n      - language-collectors" in full
    )
    assert "${{ needs.full-suite-and-reports.result }}" in full
    # The full suite runs as parallel area jobs; the gate job skips it (SHARDED_TESTS=1).
    assert "${{ needs.tests.result }}" in full
    assert "make gate SHARDED_TESTS=1" in full
    assert 'make full-test AREA="$AREA"' in full
    assert "${{ needs.collector-safety-windows.result }}" in full
    assert "${{ needs.language-collectors.result }}" in full
    assert "${{ needs.python-compat.result }}" in full
    prune = full.split("  prune-report-artifacts:\n", 1)[1].split("\n  deploy-report-pages:", 1)[0]
    assert "needs: [verified, deploy-report-pages]" in prune
    assert "make prune-report-artifacts DELETE=true" in prune
    assert "make prune-workflows DISABLE=true" in prune
    assert "group: actions-maintenance" in prune
    assert "workflow-prune/plan.json" in prune
    assert "needs: [full-suite-and-reports, verified]" in full
    assert "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full
    gallery_step = full.split("- name: Measure report and build gallery for Pages", 1)[1].split(
        "      - name:", 1
    )[0]
    assert "report-pages" in gallery_step
    assert "name: report-browser-evidence" not in full
    assert "name: scheduled-report-site" not in full
    pages_upload = full.split("- name: Upload report site for deployment\n", 1)[1].split(
        "      - name:", 1
    )[0]
    assert "github.ref == 'refs/heads/main'" in pages_upload
    assert "retention-days: 1" in pages_upload
    assert "startsWith(github.ref, 'refs/tags/')" not in pages_upload
    assert "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9" in full
    assert "name: scheduled-report-site" not in full

    prune = full.split("  prune-report-artifacts:\n", 1)[1].split("\n  deploy-report-pages:", 1)[0]
    assert "needs: [verified, deploy-report-pages]" in prune
    assert "!cancelled()" in prune
    assert "make prune-report-artifacts DELETE=true" in prune

    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert "uses: ./.github/workflows/full-verification.yml" in release
    verify = release.split("  verify:\n", 1)[1].split("\n  build:", 1)[0]
    assert "actions: write" in verify
    build = release.split("  build:\n", 1)[1].split("\n  publish:", 1)[0]
    assert "needs: verify" in build
    assert "run: make build" in build
    assert "run: make release-check" not in build
    publish = release.split("  publish:\n", 1)[1]
    assert "needs: build" in publish
    refreshed = release.split("  refresh-report-gallery:\n", 1)[1]
    assert "needs: publish" in refreshed
    assert "actions: write" in refreshed
    assert 'main_sha=$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"' in refreshed
    assert '"$main_sha" != "$GITHUB_SHA"' in refreshed
    assert (
        'gh workflow run full-verification.yml --ref main --repo "$GITHUB_REPOSITORY"' in refreshed
    )


def test_check_aggregate_executes_exact_workflow_script_fail_closed() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  lint:", 1)[0]
    step = check.split("- name: Verify selected checks and fail closed\n", 1)[1]
    script = dedent(step.split("        run: |\n", 1)[1])
    baseline = {
        "EVENT": "pull_request",
        "CHANGES_RESULT": "success",
        "CORE": "true",
        "REPORT": "true",
        "MERMAID": "true",
        "FULL": "false",
        "LINT_RESULT": "success",
        "ARCHITECTURE_RESULT": "success",
        "TESTS_RESULT": "success",
        "REPORT_RESULT": "success",
        "MERMAID_RESULT": "success",
        "FULL_RESULT": "skipped",
    }
    cases = (
        ("PR selected", {}, 0),
        ("Main selected", {"EVENT": "push"}, 0),
        ("Main full stays scheduled", {"EVENT": "push", "FULL": "true"}, 0),
        (
            "core only",
            {
                "REPORT": "false",
                "REPORT_RESULT": "skipped",
                "MERMAID": "false",
                "MERMAID_RESULT": "skipped",
            },
            0,
        ),
        (
            "report only",
            {
                "CORE": "false",
                "CORE_RESULT": "skipped",
                "MERMAID": "false",
                "MERMAID_RESULT": "skipped",
            },
            0,
        ),
        (
            "Mermaid only",
            {
                "CORE": "false",
                "CORE_RESULT": "skipped",
                "REPORT": "false",
                "REPORT_RESULT": "skipped",
            },
            0,
        ),
        (
            "nothing selected",
            {
                "CORE": "false",
                "CORE_RESULT": "skipped",
                "REPORT": "false",
                "REPORT_RESULT": "skipped",
                "MERMAID": "false",
                "MERMAID_RESULT": "skipped",
            },
            0,
        ),
        ("classifier failed", {"CHANGES_RESULT": "failure"}, 1),
        ("unexpected event", {"EVENT": "workflow_dispatch"}, 1),
        ("malformed core flag", {"CORE": "yes"}, 1),
        ("malformed report flag", {"REPORT": "TRUE"}, 1),
        ("malformed Mermaid flag", {"MERMAID": "yes"}, 1),
        ("missing report flag", {"REPORT": None}, 1),
        ("required core failed", {"CORE_RESULT": "failure"}, 1),
        ("required report cancelled", {"REPORT_RESULT": "cancelled"}, 1),
        ("required Mermaid skipped", {"MERMAID_RESULT": "skipped"}, 1),
        ("unselected child ran", {"CORE": "false", "CORE_RESULT": "success"}, 1),
        ("missing child result", {"CORE_RESULT": None}, 1),
        ("full selected", {"FULL": "true", "FULL_RESULT": "success"}, 0),
        ("required full failed", {"FULL": "true", "FULL_RESULT": "failure"}, 1),
        ("required full cancelled", {"FULL": "true", "FULL_RESULT": "cancelled"}, 1),
        ("required full skipped", {"FULL": "true"}, 1),
        ("unselected full ran", {"FULL_RESULT": "success"}, 1),
        ("malformed full flag", {"FULL": "yes"}, 1),
        ("missing full flag", {"FULL": None}, 1),
        ("missing full result", {"FULL": "true", "FULL_RESULT": None}, 1),
        ("one core job failed", {"TESTS_RESULT": "failure"}, 1),
        ("one core job skipped", {"LINT_RESULT": "skipped"}, 1),
    )
    for label, overrides, expected in cases:
        # CORE_RESULT stands for the three core jobs unless a case sets one of them.
        if "CORE_RESULT" in overrides:
            core = overrides.pop("CORE_RESULT")
            overrides |= dict.fromkeys(("LINT_RESULT", "ARCHITECTURE_RESULT", "TESTS_RESULT"), core)
        values = {
            **baseline,
            **{key: value for key, value in overrides.items() if value is not None},
        }
        env = {**os.environ, **values}
        for missing in (key for key, value in overrides.items() if value is None):
            env.pop(missing, None)
        result = subprocess.run(
            ["bash", "-eu", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True
        )
        assert (result.returncode == 0) == (expected == 0), (
            label,
            result.stdout,
            result.stderr,
        )


def test_typescript_compatibility_reuses_fixtures_and_keeps_windows_path_check() -> None:
    result = subprocess.run(
        ["make", "-n", "typescript-native", "TEST_WORKERS=4"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    command = result.stdout
    assert "--dist=loadfile" in command
    assert "test_typescript_control_target.py" not in command
    assert "tests/test_typescript_collect.py" in command
    assert (
        "tests/test_browser_architecture.py::"
        "test_browser_runner_serializes_windows_config_as_a_posix_port"
    ) in command


def test_python_classifiers_name_exactly_the_versions_the_full_workflow_tests() -> None:
    """A classifier is a claim (#724): it needs a pinned job, and a pinned job needs its claim."""
    classifiers = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["classifiers"]
    claimed = {
        classifier.rsplit(" ", 1)[1]
        for classifier in classifiers
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", classifier)
    }
    workflow = (ROOT / ".github/workflows/full-verification.yml").read_text()
    assert claimed == set(re.findall(r'"(3\.\d+)\.\d+"', workflow))


def test_full_aggregate_requires_collector_compatibility_outside_prs() -> None:
    workflow = (ROOT / ".github/workflows/full-verification.yml").read_text()
    collectors = workflow.split("  language-collectors:\n", 1)[1].split("\n  verified:", 1)[0]
    assert "if: ${{ github.event_name != 'pull_request' }}" in collectors
    aggregate = workflow.split("  verified:\n", 1)[1].split("\n  prune-report-artifacts:", 1)[0]
    script = dedent(aggregate.split("        run: |\n", 1)[1])
    baseline = {
        "FULL_RESULT": "success",
        "TESTS_RESULT": "success",
        "SAFETY_RESULT": "success",
        "DEMOS_RESULT": "success",
    }
    for event in ("pull_request", "schedule", "workflow_dispatch", "push"):
        expected = "skipped" if event == "pull_request" else "success"
        for matrix in ("success", "skipped", "failure", "cancelled", ""):
            result = subprocess.run(
                ["bash", "-eu", "-c", script],
                env={
                    **os.environ,
                    **baseline,
                    "EVENT": event,
                    "COLLECTORS_RESULT": matrix,
                    "COMPAT_RESULT": expected,
                },
                capture_output=True,
            )
            assert (result.returncode == 0) == (matrix == expected), (event, matrix)
            # The Python compatibility job follows the same rule as the collector job.
            result = subprocess.run(
                ["bash", "-eu", "-c", script],
                env={
                    **os.environ,
                    **baseline,
                    "EVENT": event,
                    "COLLECTORS_RESULT": expected,
                    "COMPAT_RESULT": matrix,
                },
                capture_output=True,
            )
            assert (result.returncode == 0) == (matrix == expected), (event, "compat", matrix)
        for required in baseline:
            result = subprocess.run(
                ["bash", "-eu", "-c", script],
                env={
                    **os.environ,
                    **baseline,
                    required: "skipped",
                    "EVENT": event,
                    "COLLECTORS_RESULT": expected,
                    "COMPAT_RESULT": expected,
                },
                capture_output=True,
            )
            assert result.returncode != 0, (event, required)


def test_required_check_script_explicitly_fails_when_workflow_cancelled() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    step = check.split("- name: Fail required check after workflow cancellation\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: cancelled()" in step
    result = subprocess.run(
        ["bash", "-eu", "-c", step.split("        run: ", 1)[1].strip()],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("renderer_exit", [0, 1])
def test_mermaid_renders_every_block_and_propagates_renderer_failure(
    tmp_path: Path, renderer_exit: int
) -> None:
    renderer = tmp_path / "npx"
    invocations = tmp_path / "renders"
    renderer.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{invocations}"\nexit {renderer_exit}\n'
    )
    renderer.chmod(0o755)
    result = subprocess.run(
        ["make", "mermaid"],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    extracted = [line for line in result.stdout.splitlines() if ".mmd\t" in line]
    rendered = invocations.read_text().splitlines()
    assert len(rendered) == len(extracted) > 1
    assert all("@mermaid-js/mermaid-cli@11.17.0" in line for line in rendered)
    assert result.returncode == (0 if renderer_exit == 0 else 2), result.stderr
    if renderer_exit:
        assert result.stdout.count("::error::") == len(rendered)
        assert all(line.split("\t", 1)[1] in result.stdout for line in extracted)


def test_ci_cleanup_preserves_test_evidence(tmp_path: Path) -> None:
    output = tmp_path / "test-artifacts/typescript-demo"
    output.mkdir(parents=True)
    (output / "stale.ts").write_text("previous demo")
    browser = tmp_path / "test-artifacts/report-browser"
    browser.mkdir()
    (browser / "tour.json").write_text("previous catalog")
    evidence = tmp_path / "test-artifacts/pytest/results.xml"
    evidence.parent.mkdir()
    evidence.write_text("keep")
    run = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "ci-artifacts-clean"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert run.returncode == 0, run.stderr
    assert not output.exists()
    assert not browser.exists()
    assert evidence.read_text() == "keep"


@pytest.mark.parametrize("target", ["test", "ci-core-check", "ci-check", "ci"])
def test_only_full_ci_stops_pytest_after_first_failure(target):
    result = subprocess.run(
        ["make", "-n", target],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": "", "PYTEST_STOP": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    command = result.stdout
    assert command.count("python -m pytest") == (1 if target == "test" else 2)
    assert ("--maxfail=1" in command) == (target != "test")
    assert "--dist=loadgroup" in command and "--max-worker-restart=0" in command
    assert "--junitxml=test-artifacts/pytest/results.xml" in command


@pytest.mark.parametrize("exit_code", [0, 2])
def test_self_observation_generates_ignored_output_and_preserves_failure(tmp_path, exit_code):
    arguments = tmp_path / "arguments"
    runner = tmp_path / "uv"
    runner.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > "{arguments}"\nexit {exit_code}\n')
    runner.chmod(0o755)
    result = subprocess.run(
        ["make", "self-observation", f"UV={runner}"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
    )
    assert arguments.read_text().split() == [
        "run",
        "--locked",
        "archkeel",
        "report",
        "--root",
        ".",
        "--output",
        "test-artifacts/self-observation/architecture.json",
    ]
    assert result.returncode == exit_code


def test_browser_runtime_gate_installs_before_running_the_actual_publication_tests() -> None:
    result = subprocess.run(
        ["make", "-n", "browser-runtime-check"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    command = result.stdout
    install = command.index("npm ci --prefix tools/browser-runtime")
    publication = command.index("python -m pytest -q tests/test_flow_runtime_publication.py")
    assert install < publication


def _collected(*arguments: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, [line for line in result.stdout.splitlines() if "::" in line]


def test_every_test_file_belongs_to_one_area_and_ci_runs_every_area() -> None:
    files = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    assert [name for name in files if area_of(name) is None] == []
    for workflow in ("ci.yml", "full-verification.yml"):
        text = (ROOT / ".github/workflows" / workflow).read_text()
        listed = re.search(r"\n        area:\n((?:          - .+\n)+)", text)
        assert listed is not None, workflow
        assert [line.split("- ", 1)[1].strip('"') for line in listed[1].splitlines()] == list(AREAS)
    pr_test = subprocess.run(
        ["make", "-n", "pr-test"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert {area_of(name) for name in re.findall(r"tests/(test_\w+\.py)", pr_test)} == set(AREAS)


def test_an_area_selects_only_its_files_and_fails_closed_when_empty() -> None:
    result, selected = _collected(
        "--area=dependency rules", "tests/test_layers.py", "tests/test_cli.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert selected and all(test.startswith("tests/test_layers.py::") for test in selected)
    result, _ = _collected("--area=demo catalog", "tests/test_layers.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "selects no tests" in result.stderr


def test_ci_pr_static_runs_policy_without_tests(tmp_path) -> None:
    result, steps = _run_gate(tmp_path, "ci-pr-static", None, 2, False, base="a" * 40)
    assert steps == ["against", "browser-architecture-check"]
    assert result.returncode == 0


@pytest.mark.parametrize("exit_code", [0, 2])
def test_self_validation_keeps_json_and_shows_failures(tmp_path: Path, exit_code: int) -> None:
    uv = tmp_path / "uv"
    uv.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' \'{"declared_rules":"UNKNOWN","diagnostics":[{"claim":"example"}]}\'\n'
        f"exit {exit_code}\n"
    )
    uv.chmod(0o755)
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "self-validate", f"UV={uv}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    payload = json.loads((tmp_path / "test-artifacts/validation/result.json").read_text())
    assert payload["declared_rules"] == "UNKNOWN"
    assert (result.returncode == 0) == (exit_code == 0)
    assert "UNKNOWN" in result.stdout
    assert "example" in result.stdout if exit_code else "example" not in result.stdout
