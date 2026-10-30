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
        ["make", "-n", "pr-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        check=True,
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
        ["make", "report-browser-tests"],
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

    full_test = subprocess.run(
        ["make", "-n", "full-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert full_test.returncode == 0, full_test.stderr
    runtime_install = full_test.stdout.index("npm ci --prefix tools/browser-runtime")
    test_run = full_test.stdout.index("python -m pytest")
    assert runtime_install < test_run


def test_workflow_files_require_an_explicit_governance_change() -> None:
    assert {path.name for path in (ROOT / ".github/workflows").iterdir() if path.is_file()} == {
        "ci.yml",
        "full-verification.yml",
        "full-on-ci-change.yml",
        "pages.yml",
        "release.yml",
    }


def _jobs(workflow: str) -> dict[str, str]:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_every_job_runs_on_a_pinned_runner_image() -> None:
    # A -latest label moves to a new image without a change in this repository.
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for job, body in _jobs(path.name).items():
            assert not re.search(r"runs-on: .*-latest", body), (path.name, job)


def test_no_job_is_skipped_by_a_condition() -> None:
    # A job-level if: shows a skipped check; only an aggregate runs always, so it never skips.
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for job, body in _jobs(path.name).items():
            conditions = re.findall(r"^    if: (.+)$", body, flags=re.MULTILINE)
            assert conditions in ([], ["always()"]), (path.name, job, conditions)


@pytest.mark.parametrize(
    ("workflow", "aggregate"),
    [("ci.yml", "check"), ("full-verification.yml", "verified")],
)
def test_each_aggregate_needs_every_job_and_fails_closed(workflow: str, aggregate: str) -> None:
    jobs = _jobs(workflow)
    body = jobs[aggregate]
    assert "if: always()" in body
    needs = re.search(r"needs: \[(.+)\]|needs:\n((?:      - .+\n)+)", body)
    assert needs is not None
    listed = re.findall(r"\w[\w-]*", needs[1] or needs[2])
    assert set(listed) == set(jobs) - {aggregate}
    script = dedent(body.split("        run: |\n", 1)[1])
    ok = " ".join(["success"] * len(listed))

    def run(results: str) -> int:
        env = {**os.environ, "RESULTS": results}
        return subprocess.run(
            ["bash", "-eu", "-c", script], env=env, capture_output=True
        ).returncode

    assert run(ok) == 0
    for bad in ("failure", "cancelled", "skipped"):
        assert run(ok.replace("success", bad, 1)) != 0, bad
    assert run("") != 0


def test_pull_requests_run_one_fixed_job_set_and_full_runs_on_its_own_triggers() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert ci.split("\non:\n", 1)[1].split("\n\n", 1)[0] == "  pull_request:"
    assert not re.search(r"^    uses:", ci, flags=re.MULTILINE)
    jobs = _jobs("ci.yml")
    assert 'make ci-pr-static BASE="$BASE"' in jobs["lint"]
    assert 'make pr-test AREA="$AREA"' in jobs["tests"]
    assert "make ci-pr-report-check" in jobs["pr-report-check"]
    assert "run: make mermaid" in jobs["mermaid"]
    assert "run: make demos" in jobs["demos"]

    full = (ROOT / ".github/workflows/full-verification.yml").read_text()
    for trigger in ("workflow_call:", "workflow_dispatch:", "schedule:"):
        assert trigger in full
    assert "pages: write" not in full and "id-token: write" not in full
    full_jobs = _jobs("full-verification.yml")
    assert "make ci-core-check SKIP_TESTS=1" in full_jobs["full-suite-and-reports"]
    assert "run: make report-timing" in full_jobs["full-suite-and-reports"]
    assert "report-pages" not in full
    assert 'make full-test AREA="$AREA"' in full_jobs["tests"]
    assert "name: report-gallery" in full_jobs["demos"]
    assert "runs-on: windows-2025" in full_jobs["collector-safety-windows"]
    assert "make dart-test TEST_WORKERS=4 SHELL=bash" in full_jobs["language-collectors"]

    caller = (ROOT / ".github/workflows/full-on-ci-change.yml").read_text()
    assert "uses: ./.github/workflows/full-verification.yml" in caller
    for path in (".github/workflows/**", "Makefile", "tests/areas.py", "tests/conftest.py"):
        assert f"      - {path}\n" in caller or f'      - "{path}"\n' in caller
    release = _jobs("release.yml")
    assert "uses: ./.github/workflows/full-verification.yml" in release["verify"]
    assert "needs: verify" in release["build"]
    assert "gh workflow run full-verification.yml --ref main" in release["refresh-report-gallery"]


def test_pages_publish_only_a_passed_full_run_of_the_current_main(tmp_path: Path) -> None:
    pages = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "workflow_run:\n    workflows: [Full verification]" in pages
    assert "branches: [main]" in pages
    step = pages.split("- name: Check that Full passed on the current Main\n", 1)[1]
    script = dedent(step.split("        run: |\n", 1)[1].split("\n\n", 1)[0])
    main = "a" * 40
    for number, (conclusion, run_sha, event, head_repo, published) in enumerate(
        (
            ("success", main, "schedule", "o/r", True),
            ("success", main, "workflow_dispatch", "o/r", True),
            ("failure", main, "schedule", "o/r", False),
            ("success", "b" * 40, "schedule", "o/r", False),
            ("success", main, "pull_request", "o/r", False),
            ("success", main, "schedule", "fork/r", False),
        )
    ):
        output = tmp_path / str(number)
        fake = f"gh() {{ echo {main}; }}; export -f gh; "
        subprocess.run(
            ["bash", "-eu", "-c", fake + script],
            env={
                **os.environ,
                "CONCLUSION": conclusion,
                "RUN_SHA": run_sha,
                "EVENT": event,
                "HEAD_REPO": head_repo,
                "GITHUB_OUTPUT": str(output),
                "GITHUB_REPOSITORY": "o/r",
            },
            check=True,
            capture_output=True,
        )
        assert output.read_text() == f"publish={str(published).lower()}\n"
    for step_name in (
        "Download the current report",
        "Download the demo gallery",
        "Deploy the site",
    ):
        body = pages.split(f"- name: {step_name}\n", 1)[1].split("\n\n", 1)[0]
        assert "if: steps.verified.outputs.publish == 'true'" in body


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
    files = sorted(path.name for path in (ROOT / "tests").rglob("test_*.py"))
    assert [name for name in files if area_of(name) is None] == []
    for workflow in ("ci.yml", "full-verification.yml"):
        text = (ROOT / ".github/workflows" / workflow).read_text()
        listed = re.search(r"\n        area:\n((?:          - .+\n)+)", text)
        assert listed is not None, workflow
        assert [line.split("- ", 1)[1].strip('"') for line in listed[1].splitlines()] == list(AREAS)
    pr_test = subprocess.run(
        ["make", "-n", "pr-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert {area_of(name) for name in re.findall(r"tests/(test_\w+\.py)", pr_test)} == set(AREAS)


def test_an_area_selects_only_its_files_and_fails_closed_when_empty() -> None:
    result, selected = _collected("--area=reports", "tests/test_trace.py", "tests/test_layers.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert selected and all(test.startswith("tests/test_trace.py::") for test in selected)
    result, _ = _collected("--area=demo catalog", "tests/test_layers.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "selects no tests" in result.stderr
    result, _ = _collected("--area=no such area", "tests/test_layers.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "is not an area" in result.stderr


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
