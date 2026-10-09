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
    for test_file in (
        "tests/test_report_pages.py",
        "tests/test_report_interactions.py",
        "tests/test_report_browser.py",
        "tests/test_uml_rendering.py",
        "tests/test_compass_project_report.py",
        "tests/test_python_realworld_project_report.py",
        "tests/test_nest_realworld_project_report.py",
    ):
        assert test_file in command


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


def test_ci_workflow_keeps_pinned_policy_and_required_acceptance() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    assert (
        "if: ${{ (github.event_name == 'pull_request' && always()) || "
        "(github.event_name == 'push' && !cancelled()) }}"
    ) in check
    assert "needs: [changes, pr-core-check, pr-report-check]" in check
    classifier_failure = check.split("- name: Fail if change detection failed\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: ${{ !cancelled() && needs.changes.result != 'success' }}" in classifier_failure
    assert "run: exit 1" in classifier_failure
    aggregate = check.split("- name: Verify PR check results\n", 1)[1].split("\n      - name:", 1)[
        0
    ]
    assert "if: github.event_name == 'pull_request' && always()" in aggregate
    assert "CANCELLED:" not in aggregate
    assert "CHANGES_RESULT: ${{ needs.changes.result }}" in aggregate
    assert "CORE: ${{ needs.changes.outputs.core }}" in aggregate
    assert "REPORT: ${{ needs.changes.outputs.report }}" in aggregate
    assert "CORE_RESULT: ${{ needs.pr-core-check.result }}" in aggregate
    assert "REPORT_RESULT: ${{ needs.pr-report-check.result }}" in aggregate
    assert "run: |" in aggregate
    assert "run: make ci-core-check\n" in check
    assert "run: make ci-report-check\n" in check
    assert "make ci-pr-" not in check
    assert "continue-on-error" not in check
    assert "timeout-minutes: ${{ github.event_name == 'pull_request' && 25 || 90 }}" in check
    for heading in ("Run full core checks", "Run full report checks"):
        step = check.split(f"- name: {heading}\n", 1)[1].split("\n      - name:", 1)[0]
        assert "github.event_name == 'push'" in step
    for heading in (
        "Check out source",
        "Install Node",
        "Install uv and Python",
        "Install Dart SDK",
        "Install supported runtimes",
        "Install locked dependencies",
        "Prepare native Dart analyzer",
        "Clean previous CI artifacts",
        "Upload test timings",
        "Upload report runtime",
        "Upload synthetic report browser evidence",
    ):
        step = check.split(f"- name: {heading}\n", 1)[1].split("\n      - name:", 1)[0]
        assert "github.event_name == 'push'" in step
    assert "Observe Archkeel" not in check
    assert "archkeel-self-observation" not in check
    assert "path: test-artifacts/report-timing/architecture.timing.json" in check
    assert "path: test-artifacts/pytest/*.xml" in check
    assert "path: test-artifacts/report-browser/" in check
    assert "retention-days: 1" in check

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
        assert (
            f"github.event_name == 'pull_request' && needs.changes.outputs.{area} == 'true'" in job
        )
        assert "runs-on: ubuntu-latest" in job
        assert "timeout-minutes: 25" in job
        assert "permissions:\n      contents: read" in job
        assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in job
        assert "actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444" in job
        assert "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9" in job
        assert "dart-lang/setup-dart@6afc89df92d6eb3834022f73cd65adc8cdfcb92d" in job
        assert f"run: make {make_target}" in job
        assert f"name: {junit_name}" in job
        assert junit_path in job
        assert "retention-days: 7" in job
    core_job = workflow.split("  pr-core-check:\n", 1)[1].split("\n  pr-report-check:", 1)[0]
    assert "BASE: ${{ github.event.pull_request.base.sha }}" in core_job
    assert workflow.count("name: report-browser-evidence") == 2
    assert check.count("name: report-browser-evidence") == 1
    pr_report = workflow.split("  pr-report-check:\n", 1)[1].split(
        "\n  prune-report-artifacts:", 1
    )[0]
    assert pr_report.count("name: report-browser-evidence") == 1
    assert "retention-days: 1" in pr_report
    cleanup = workflow.split("  prune-report-artifacts:\n", 1)[1].split(
        "\n  collector-safety-windows:", 1
    )[0]
    assert (
        "if: ${{ !cancelled() && github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
        in cleanup
    )
    assert "needs: check" in cleanup
    assert "github.event_name == 'push'" in cleanup
    assert "github.ref == 'refs/heads/main'" in cleanup
    assert "actions: write" in cleanup
    assert workflow.count("actions: write") == 1
    assert "contents: read" in cleanup
    assert "ref: ${{ github.sha }}" in cleanup
    assert "GH_TOKEN: ${{ github.token }}" in cleanup
    assert "make prune-report-artifacts DELETE=true" in cleanup
    makefile = (ROOT / "Makefile").read_text()
    assert "gh api --paginate --slurp" in makefile
    assert "gh api --method DELETE" in makefile
    assert "DELETE ?= false" in makefile
    assert "artifact_ids=$$(python3 -c" in makefile
    assert "for artifact_id in $$artifact_ids" in makefile
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert (
        "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
        in workflow
    )
    assert "run: make mermaid" in workflow
    mermaid = workflow.split("  mermaid:\n", 1)[1].split("\n    steps:\n", 1)[0]
    assert (
        "if: ${{ !cancelled() && needs.changes.result == 'success' && "
        "needs.changes.outputs.mermaid == 'true' }}"
    ) in mermaid
    native = workflow.split("  typescript-native:\n", 1)[1].split("\n  github-order-report:", 1)[0]
    assert "os: [ubuntu-latest, windows-latest]" in native
    assert 'python: ["3.11.12", "3.12.10"]' in native
    assert "make typescript-native SHELL=bash" in native
    assert "make build smoke SHELL=bash" in native
    assert "if: github.event_name == 'push' && needs.changes.outputs.core == 'true'" in native
    safety = workflow.split("  collector-safety-windows:\n", 1)[1].split(
        "\n  typescript-native:", 1
    )[0]
    assert "if: needs.changes.outputs.core == 'true'" in safety
    dart = workflow.split("  dart-native:\n", 1)[1].split("\n  github-order-report:", 1)[0]
    assert "if: needs.changes.outputs.core == 'true'" in dart
    assert "if: github.event_name == 'push' && needs.changes.outputs.core == 'true'" not in dart
    assert "collector-runtimes:" not in workflow
    makefile = (ROOT / "Makefile").read_text()
    pr_tests = makefile.split("pr-test:\n", 1)[1].split("\npr-report-test:", 1)[0]
    dart_tests = makefile.split("dart-native:\n", 1)[1].split("\n# Compare against", 1)[0]
    assert "tests/test_flutter_demo.py" in pr_tests
    assert "tests/test_flutter_demo.py" not in dart_tests
    pr_report_tests = makefile.split("pr-report-test:\n", 1)[1].split("\nci-typescript:", 1)[0]
    assert "tests/test_compass_project_report.py" in pr_report_tests
    assert "tests/test_python_realworld_project_report.py" in pr_report_tests
    assert "tests/test_nest_realworld_project_report.py" in pr_report_tests


def test_pr_aggregate_executes_exact_workflow_script_fail_closed() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    step = check.split("- name: Verify PR check results\n", 1)[1].split("\n      - name:", 1)[0]
    script = dedent(step.split("        run: |\n", 1)[1])
    baseline = {
        "EVENT": "pull_request",
        "CHANGES_RESULT": "success",
        "CORE": "true",
        "REPORT": "true",
        "CORE_RESULT": "success",
        "REPORT_RESULT": "success",
    }
    cases = (
        ("both selected", {}, 0),
        ("core only", {"REPORT": "false", "REPORT_RESULT": "skipped"}, 0),
        ("report only", {"CORE": "false", "CORE_RESULT": "skipped"}, 0),
        (
            "neither selected",
            {
                "CORE": "false",
                "REPORT": "false",
                "CORE_RESULT": "skipped",
                "REPORT_RESULT": "skipped",
            },
            0,
        ),
        ("classifier failed", {"CHANGES_RESULT": "failure"}, 1),
        ("malformed core flag", {"CORE": "yes"}, 1),
        ("malformed report flag", {"REPORT": "TRUE"}, 1),
        ("missing core flag", {"CORE": None}, 1),
        ("missing report flag", {"REPORT": None}, 1),
        ("required child failed", {"CORE_RESULT": "failure"}, 1),
        ("required child cancelled", {"REPORT_RESULT": "cancelled"}, 1),
        ("required child skipped", {"CORE_RESULT": "skipped"}, 1),
        (
            "unselected child unexpectedly ran",
            {
                "CORE": "false",
                "REPORT": "false",
                "CORE_RESULT": "success",
                "REPORT_RESULT": "skipped",
            },
            1,
        ),
        ("missing child result", {"CORE_RESULT": None}, 1),
    )
    for label, overrides, expected in cases:
        values = {
            **baseline,
            **{key: value for key, value in overrides.items() if value is not None},
        }
        missing_values = [key for key, value in overrides.items() if value is None]
        for missing in missing_values:
            values.pop(missing)
        env = {**os.environ, **values}
        for missing in missing_values:
            env.pop(missing, None)
        result = subprocess.run(
            ["bash", "-eu", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True
        )
        assert (result.returncode == 0) == (expected == 0), (
            label,
            result.stdout,
            result.stderr,
        )


def test_pr_workflow_cancellation_has_a_fail_step() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  pr-core-check:", 1)[0]
    step = check.split("- name: Fail PR aggregate on workflow cancellation\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: github.event_name == 'pull_request' && cancelled()" in step
    script = step.split("        run: ", 1)[1].strip()
    result = subprocess.run(["bash", "-eu", "-c", script], cwd=ROOT, capture_output=True, text=True)
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
