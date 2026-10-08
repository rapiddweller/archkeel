# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Policy and release failures stop later Make steps, including parallel invocations."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GATE_STEPS = ["self-validate", "check", "build", "smoke"]
CI_CHECK_STEPS = [
    "ci-artifacts-clean",
    *GATE_STEPS,
    "demo-typescript",
    "report-timing",
    "browser-install",
    "report-browser",
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
    names = [*CI_STEPS, "against", "pr-test", "pr-report-test"]
    recipes = []
    for name in names:
        output_guard = ""
        if name == "demo-typescript":
            output_guard = '\t@test "$(OUTPUT)" = test-artifacts/typescript-demo\n'
        elif name == "report-browser":
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
    runner.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{steps}"\nexit 1\n')
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
        f"run --locked python -m tools.against --base {'a' * 40}"
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


def test_ci_workflow_keeps_pinned_policy_and_required_acceptance() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = workflow.split("  check:\n", 1)[1].split("\n  collector-safety-windows:", 1)[0]
    assert "if: ${{ !cancelled() }}" in check
    classifier_failure = check.split("- name: Fail if change detection failed\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: ${{ !cancelled() && needs.changes.result != 'success' }}" in classifier_failure
    assert "run: exit 1" in classifier_failure
    assert "BASE: ${{ github.event.pull_request.base.sha }}" in check
    assert "run: make ci-core-check\n" in check
    assert "run: make ci-report-check\n" in check
    assert "continue-on-error" not in check
    assert "timeout-minutes: ${{ github.event_name == 'pull_request' && 25 || 60 }}" in check
    assert "run: make ci-pr-check\n" in check
    assert "run: make ci-pr-report-check\n" in check
    for heading in ("Run full core checks", "Run full report checks"):
        step = check.split(f"- name: {heading}\n", 1)[1].split("\n      - name:", 1)[0]
        assert "github.event_name == 'push'" in step
    for heading in ("Run PR core checks", "Run PR report checks"):
        step = check.split(f"- name: {heading}\n", 1)[1].split("\n      - name:", 1)[0]
        assert "github.event_name == 'pull_request'" in step
    assert "Observe Archkeel" not in check
    assert "archkeel-self-observation" not in check
    assert "path: test-artifacts/report-timing/architecture.timing.json" in check
    assert "path: test-artifacts/pytest/*.xml" in check
    assert "path: test-artifacts/report-browser/" in check
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
