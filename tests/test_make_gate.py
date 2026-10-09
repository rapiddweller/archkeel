# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Policy and release failures stop later Make steps, including parallel invocations."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).parents[1]
GATE_STEPS = ["self-validate", "check", "build", "smoke"]
CI_CHECK_STEPS = [
    "ci-artifacts-clean",
    "browser-install",
    *GATE_STEPS,
    "demo-typescript",
    "report-timing",
    "report-browser-proof",
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
        elif name == "report-browser-proof":
            output_guard = '\t@test -z "$(OUTPUT)"\n'
        recipes.append(
            f'{name}:\n\t@echo {name} >> "{steps}"\n\t@sleep 0.05\n\t@exit {int(name == failed)}\n'
            + output_guard
        )
    overrides.write_text(
        ("" if separate_override else f"include {ROOT / 'Makefile'}\n")
        + ".PHONY: "
        + " ".join([*names, "lint", "typecheck", "test"])
        + "\nlint typecheck test:\n\t@:\n"
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
    expected = ["against", "check", "build", "smoke"]
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
        "demo-typescript",
        "browser-install",
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
        "run --locked --with playwright==1.62.0 python -m playwright install --with-deps chromium",
        f"run --locked python -m tools.against --base {'a' * 40}",
    ]


@pytest.mark.parametrize("failed", [None, "against", "pr-test"])
def test_pr_gate_keeps_policy_and_stops_before_later_checks(tmp_path, failed):
    result, steps = _run_gate(tmp_path, "ci-pr-check", failed, 2, False, base="a" * 40)
    assert steps == (["against"] if failed == "against" else ["against", "pr-test"])
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
        "tests/test_flutter_demo.py::test_flutter_target_owns_three_meaningful_component_levels_and_all_modules",
        "tests/test_flutter_demo.py::test_flutter_target_pins_journey_signatures_member_scopes_and_flutter_inheritance",
    ):
        assert selector in command
    assert "tests/test_dart_unknowns.py " not in command
    assert "tests/test_flutter_demo.py " not in command
    assert (
        "test_flutter_variant_reports_keep_pass_fail_unknown_and_coverage_distinct" not in command
    )


@pytest.mark.parametrize("failed", [None, "browser-install", "pr-report-test"])
def test_pr_report_gate_runs_its_browser_sample_and_propagates_failure(tmp_path, failed):
    result, steps = _run_gate(tmp_path, "ci-pr-report-check", failed, 2, False)
    assert steps == (
        ["browser-install"]
        if failed == "browser-install"
        else ["browser-install", "pr-report-test"]
    )
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
    assert "--with playwright==1.62.0" in command
    assert "python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 -q" in command
    assert "--junitxml=test-artifacts/pytest/pr-report.xml" in command
    for selector in (
        "tests/test_report_renderer_units.py",
        "tests/test_report_interactions.py::test_native_card_drag_reroutes_all_hits_and_keeps_architecture_unchanged",
        "tests/test_uml_rendering.py::test_standard_uml_ignores_stale_layout_and_retries_rejected_layout",
        "tests/test_atlas_report.py::test_target_content_is_independent_of_observed_evidence",
        "tests/test_atlas_report.py::test_atlas_browser_keeps_positions_and_unknown_cells_across_lenses",
        "tests/test_atlas_report.py::test_atlas_component_layout_keeps_union_geometry_and_active_edges",
        "tests/test_report_interactions.py::test_atlas_component_routes_select_leafs_and_open_inside_scopes",
        "tests/test_python_realworld_project_report.py::test_python_http_module_scope_preserves_nested_ownership_and_target_routes",
        "tests/test_python_realworld_project_report.py::test_python_realworld_module_overview_uses_actual_edges_and_keeps_isolated_routes",
        "tests/test_own_uml_target.py::test_own_filtered_calls_keep_clear_routes_and_readable_arrow_endpoints",
    ):
        assert selector in command
    assert "tests/test_compass_project_report.py" not in command
    assert "tests/test_nest_realworld_project_report.py" not in command


@pytest.mark.parametrize("fail_pytest", [False, True])
def test_report_browser_runs_report_tests_before_evidence(
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
        "    and '-m' in sys.argv\n"
        "    and 'pytest' in sys.argv\n"
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
    assert invocations[0][:10] == [
        "run",
        "--locked",
        "--with",
        "playwright==1.62.0",
        "python",
        "-m",
        "pytest",
        "-n",
        "2",
        "--dist=loadfile",
    ]
    assert "--max-worker-restart=0" in invocations[0]
    if fail_pytest:
        assert len(invocations) == 1
        assert result.returncode == 2
    else:
        assert len(invocations) == 2
        assert invocations[1] == [
            "run",
            "--locked",
            "--with",
            "playwright==1.62.0",
            "python",
            "-m",
            "tools.report_browser",
        ]
        assert result.returncode == 0, result.stderr


def test_main_core_uses_pinned_playwright_once_and_report_stage_only_runs_proof() -> None:
    result = subprocess.run(
        ["make", "-n", "-j8", "ci-check"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": "", "OUTPUT": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    commands = result.stdout
    browser_install = commands.index("python -m playwright install --with-deps chromium")
    pytest_run = commands.index("run --locked --with playwright==1.62.0 python -m pytest -n 2")
    report_proof = commands.index("python -m tools.report_browser")
    report_timing = commands.index("python -m tools.report_timing")
    assert browser_install < pytest_run < report_proof
    assert report_timing < report_proof
    assert commands.count("python -m playwright install --with-deps chromium") == 1
    assert "tests/test_*report*.py" not in commands
    assert "make report-browser-tests" not in commands


def test_ci_workflow_keeps_fast_required_checks_and_routes_full_verification() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    assert "needs: [changes, pr-core-check, pr-report-check, mermaid]" in check
    assert "if: ${{ always() }}" in check
    assert (
        "- name: Fail required check after workflow cancellation\n        if: cancelled()" in check
    )
    assert "needs.changes.result" in check
    for result in ("CORE_RESULT", "REPORT_RESULT", "MERMAID_RESULT"):
        assert f"{result}: ${{{{ needs." in check
    assert "verify_area core" in check
    assert "verify_area report" in check
    assert "verify_area mermaid" in check
    assert "Selected $area check did not succeed" in check
    assert "Unselected $area check was not skipped" in check
    assert "continue-on-error" not in check
    assert "make ci-core-check" not in check
    assert "make ci-report-check" not in check
    assert "make report-pages" not in workflow
    assert "collector-safety-windows:" not in workflow
    assert "typescript-native:" not in workflow
    assert "dart-native:" not in workflow

    for job_id, next_job, area, make_target, junit_name, junit_path in (
        (
            "pr-core-check",
            "pr-report-check",
            "core",
            "ci-pr-check",
            "pytest-results-pr-core",
            "pr-core.xml",
        ),
        (
            "pr-report-check",
            "prune-report-artifacts",
            "report",
            "ci-pr-report-check",
            "pytest-results-pr-report",
            "pr-report.xml",
        ),
    ):
        job = workflow.split(f"  {job_id}:\n", 1)[1].split(f"\n  {next_job}:\n", 1)[0]
        assert "needs: changes" in job
        assert "github.event_name == 'pull_request' || github.event_name == 'push'" in job
        assert f"needs.changes.outputs.{area} == 'true'" in job
        assert "runs-on: ubuntu-latest" in job
        assert "timeout-minutes: 25" in job
        assert "permissions:\n      contents: read" in job
        assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in job
        assert "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9" in job
        assert f"run: make {make_target}" in job
        assert f"name: {junit_name}" in job
        assert junit_path in job
        assert "retention-days: 7" in job
    core_job = workflow.split("  pr-core-check:\n", 1)[1].split("\n  pr-report-check:", 1)[0]
    assert "BASE: ${{ github.event.pull_request.base.sha }}" in core_job
    report_job = workflow.split("  pr-report-check:\n", 1)[1].split(
        "\n  prune-report-artifacts:", 1
    )[0]
    assert "Install Dart SDK" not in report_job
    assert "Prepare native Dart analyzer" not in report_job

    cleanup = workflow.split("  prune-report-artifacts:\n", 1)[1].split(
        "\n  github-order-report:", 1
    )[0]
    assert "needs: check" in cleanup
    assert "github.ref == 'refs/heads/main'" in cleanup
    assert "actions: write" in cleanup
    assert "ref: ${{ github.sha }}" in cleanup
    assert "make prune-report-artifacts DELETE=true" in cleanup
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    mermaid = workflow.split("  mermaid:\n", 1)[1].split("\n    steps:", 1)[0]
    assert "needs.changes.outputs.mermaid == 'true'" in mermaid
    assert "run: make mermaid" in workflow

    full = (ROOT / ".github/workflows/full-verification.yml").read_text()
    for trigger in ("workflow_call:", "workflow_dispatch:", "schedule:"):
        assert trigger in full
    assert "make ci-check" in full
    assert "make mermaid" in full
    assert "make report-pages" in full
    assert "test-artifacts/report-timing/architecture.timing.json" in full
    assert "test-artifacts/report-browser/" in full
    evidence = full.split("name: report-browser-evidence", 1)[1].split("      - name:", 1)[0]
    assert "retention-days: 1" in evidence
    assert 'matrix:\n        python: ["3.11.12", "3.12.10"]' in full
    assert "matrix:\n        os: [ubuntu-latest, windows-latest]\n        python:" in full
    assert "setup-dart@" not in full
    assert "dart-setup" not in full
    assert "dart-native:" not in full
    assert "make dart-test SHELL=bash" in full
    assert "setup-dart@" not in workflow
    assert "dart-setup" not in workflow
    assert "if: always()" in full
    assert (
        "needs:\n      - full-suite-and-reports\n      - collector-safety-windows\n"
        "      - language-collectors" in full
    )
    assert "${{ needs.full-suite-and-reports.result }}" in full
    assert "${{ needs.collector-safety-windows.result }}" in full
    assert "${{ needs.language-collectors.result }}" in full
    prune = full.split("  prune-report-artifacts:\n", 1)[1].split("\n  deploy-report-pages:", 1)[0]
    assert "needs: [verified, deploy-report-pages]" in prune
    assert "make prune-report-artifacts DELETE=true" in prune
    assert "needs: [full-suite-and-reports, verified]" in full
    assert "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full
    assert "name: report-browser-evidence" in full
    assert "name: scheduled-report-site" not in full
    pages_upload = full.split("- name: Upload report site for deployment\n", 1)[1].split(
        "      - name:", 1
    )[0]
    assert "github.ref == 'refs/heads/main'" in pages_upload
    assert "retention-days: 1" in pages_upload
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


def test_check_aggregate_executes_exact_workflow_script_fail_closed() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    step = check.split("- name: Verify selected checks and fail closed\n", 1)[1]
    script = dedent(step.split("        run: |\n", 1)[1])
    baseline = {
        "EVENT": "pull_request",
        "CHANGES_RESULT": "success",
        "CORE": "true",
        "REPORT": "true",
        "MERMAID": "true",
        "CORE_RESULT": "success",
        "REPORT_RESULT": "success",
        "MERMAID_RESULT": "success",
    }
    cases = (
        ("PR selected", {}, 0),
        ("Main selected", {"EVENT": "push"}, 0),
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
    )
    for label, overrides, expected in cases:
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
    assert command.count("python -m pytest") == 1
    assert ("--maxfail=1" in command) == (target != "test")
    assert "--dist=loadfile" in command and "--max-worker-restart=0" in command
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
