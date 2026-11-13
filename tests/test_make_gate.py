# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Policy and release failures stop later Make steps, including parallel invocations."""

from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from textwrap import dedent

import pytest
from areas import AREAS, area_of

ROOT = Path(__file__).parents[1]
GATE_STEPS = ["browser-architecture-check", "check", "build", "smoke"]
CI_CHECK_STEPS = [
    "ci-artifacts-clean",
    *GATE_STEPS,
    "typescript-compiler-check",
    "browser-graph-check",
    "browser-runtime-check",
    "typescript-libs-check",
    "self-validate-native",
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
    names = [*CI_STEPS, "pr-test", "pr-report-test"]
    recipes = []
    for name in names:
        recipes.append(
            f'{name}:\n\t@echo {name} >> "{steps}"\n\t@sleep 0.05\n\t@exit {int(name == failed)}\n'
        )
    overrides.write_text(
        ("" if separate_override else f"include {ROOT / 'Makefile'}\n")
        + ".PHONY: "
        + " ".join([*names, "lint", "typecheck", "test"])
        + "\nlint typecheck test browser-runtime-install core:\n\t@:\n"
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
@pytest.mark.parametrize(
    "failed",
    [
        None,
        "ci-artifacts-clean",
        "self-validate-native",
        "typescript-compiler-check",
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


@pytest.mark.parametrize("failed", [None, "browser-architecture-check", "pr-test"])
def test_pr_gate_keeps_policy_and_stops_before_later_checks(tmp_path, failed):
    result, steps = _run_gate(tmp_path, "ci-pr-check", failed, 2, False, base="a" * 40)
    expected = ["browser-architecture-check", "pr-test"]
    if failed is not None:
        expected = expected[: expected.index(failed) + 1]
    assert steps == expected
    assert result.returncode == (0 if failed is None else 2)


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


def test_workflow_files_require_an_explicit_governance_change() -> None:
    assert {path.name for path in (ROOT / ".github/workflows").iterdir() if path.is_file()} == {
        "ci.yml",
        "full-verification.yml",
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


def test_full_report_job_allows_the_browser_suite_to_finish() -> None:
    body = _jobs("full-verification.yml")["full-suite-and-reports"]
    timeout = re.search(r"^    timeout-minutes: (\d+)$", body, re.MULTILINE)
    assert timeout is not None
    assert int(timeout.group(1)) >= 30


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


def _needs(body: str) -> set[str]:
    found = re.search(
        r"^    needs: \[(.+)\]$|^    needs: (\S+)$|^    needs:\n((?:      - .+\n)+)", body, re.M
    )
    return (
        set(re.findall(r"\w[\w-]*", "".join(part or "" for part in found.groups())))
        if found
        else set()
    )


def test_each_release_job_runs_after_full_verification() -> None:
    """AD-280 decision 3: a release runs Full first. Only the gate of AD-432 is before Full."""
    jobs = _jobs("release.yml")
    assert "uses: ./.github/workflows/full-verification.yml" in jobs["verify"]

    def after_verify(job: str) -> bool:
        return any(need == "verify" or after_verify(need) for need in _needs(jobs[job]))

    assert [job for job in jobs if job != "verify" and not after_verify(job)] == ["core-in-wheel"]


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


def test_no_test_branches_on_the_python_version() -> None:
    # The area jobs run Python 3.11, so a version branch hides its newer branch from each CI job.
    readers = [
        path.name
        for path in sorted((ROOT / "tests").glob("*.py"))
        if path.name != "conftest.py"
        and any(
            isinstance(node, ast.Attribute) and node.attr == "version_info"
            for node in ast.walk(ast.parse(path.read_text()))
        )
    ]
    assert readers == []


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
    output = tmp_path / "test-artifacts/validation-native"
    output.mkdir(parents=True)
    (output / "result.json").write_text("previous result")
    browser = tmp_path / "test-artifacts/validation"
    browser.mkdir()
    (browser / "studio-ui.json").write_text("previous result")
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


def _collected(
    *arguments: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
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
        env=os.environ if path is None else {**os.environ, "PYTHONPATH": path},
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


def _triggers(workflow: str) -> set[str]:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    block = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    return set(re.findall(r"^  (\w+):", block, flags=re.MULTILINE))


def test_ci_runs_on_main_and_dispatch_and_full_runs_nightly_dispatch_or_called() -> None:
    # AD-348: no pull_request trigger; a PR merges on its review and the local gate.
    assert _triggers("ci.yml") == {"push", "workflow_dispatch"}
    assert _triggers("full-verification.yml") == {"workflow_call", "workflow_dispatch", "schedule"}
    assert "branches: [main]" in (ROOT / ".github/workflows/ci.yml").read_text()


def test_a_test_added_to_the_pr_test_list_does_not_run_full() -> None:
    """Full runs every area (make full-test), never the pr-test list: it is not a Full input."""
    makefile = (ROOT / "Makefile").read_text()
    recipe = re.search(r"^pr-test:.*?\n\n", makefile, re.DOTALL | re.MULTILINE)
    assert recipe is not None
    assert "tests/test_" not in recipe[0]
    listed = (ROOT / "tests/pr-test.mk").read_text().split(":=", 1)[1]
    dry_run = subprocess.run(
        ["make", "-n", "-o", "browser-runtime-install", "pr-test"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    resolved = [a for a in shlex.split(dry_run.replace("\\\n", " ")) if a.startswith("tests/")]
    assert resolved == shlex.split(listed.replace("\\\n", " "))
    assert len(resolved) > 80


FULL_MK = "tools/full.mk"
# CI runs these on each PR, so a break in them shows before the merge. Full needs no run for them.
SHARED_WITH_CI = {"mermaid", "self-validate-native"}


def _called_targets(workflow: str) -> set[str]:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    return {
        t
        for run in re.findall(r"\bmake ((?:[a-z][\w-]*(?: |$))+)", text, re.M)
        for t in run.split()
    }


def _closure(targets: set[str]) -> set[str]:
    database = subprocess.run(
        ["make", "-pn"],
        cwd=ROOT,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
    ).stdout
    needs: dict[str, set[str]] = {}
    for name, rest in re.findall(r"^([a-z][\w-]*):(?!=)[ \t]*(.*)$", database, re.M):
        # GNU make prints a target-specific variable (`name: VAR := value`) in the same form.
        if not re.match(r"[\w-]+\s*[:+?]?=", rest):
            needs.setdefault(name, set()).update(rest.split())
    seen: set[str] = set()
    todo = list(targets)
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(needs.get(name, ()))
    return seen


def test_each_make_target_that_only_full_runs_is_in_the_full_fragment() -> None:
    """Full watches `tools/full.mk`, so a recipe that CI does not run must be defined there."""
    fragment = set(re.findall(r"^([a-z][\w-]*):", (ROOT / FULL_MK).read_text(), re.M))
    makefile = (ROOT / "Makefile").read_text()
    assert "include $(MAKEFILE_DIR)tools/full.mk" in makefile
    called = _called_targets("full-verification.yml")
    assert called - fragment == SHARED_WITH_CI
    assert SHARED_WITH_CI <= _called_targets("ci.yml")
    assert [t for t in SHARED_WITH_CI if re.search(rf"^{t}:", makefile, re.M) is None] == []
    only_full = _closure(called) - _closure(_called_targets("ci.yml"))
    assert only_full - fragment == set()
    assert fragment - only_full == set(), "a recipe in the fragment that Full never runs"


def test_every_area_has_files() -> None:
    """An edit of tests/areas.py that changes the Full job set fails here, not in the Full run."""
    files = [path.name for path in (ROOT / "tests").rglob("test_*.py")]
    assert [area for area in AREAS if not any(area_of(name) == area for name in files)] == []


def test_an_area_selects_only_its_files_and_fails_closed_when_empty() -> None:
    result, selected = _collected(
        "--area=reports", "tests/test_report_schema.py", "tests/test_skill.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert selected and all(test.startswith("tests/test_report_schema.py::") for test in selected)
    result, _ = _collected("--area=CLI and core", "tests/test_skill.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "selects no tests" in result.stderr
    result, _ = _collected("--area=no such area", "tests/test_skill.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "is not an area" in result.stderr


def test_ci_pr_static_runs_policy_without_tests(tmp_path) -> None:
    result, steps = _run_gate(tmp_path, "ci-pr-static", None, 2, False, base="a" * 40)
    assert steps == ["browser-architecture-check"]
    assert result.returncode == 0


REFUSED = '{"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_error", "message": "x"}}'


@pytest.mark.parametrize(
    ("target", "printed", "shown"),
    [
        ("self-validate-native", REFUSED, "refused: core_error: x"),
        ("self-validate-native", "", "JSONDecodeError"),
        ("browser-architecture-check", REFUSED, "core_error"),
    ],
)
def test_a_self_check_without_the_pinned_core_result_fails(
    tmp_path: Path, target: str, printed: str, shown: str
) -> None:
    """AD-432: a refusal or no result of `archkeel validate` never passes a self-check gate."""
    uv = tmp_path / "uv"
    uv.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f"  *archkeel\\ validate*) printf '%s' '{printed}'; exit 2;;\n"
        f'  *) shift 3; exec "{sys.executable}" "$@";;\n'
        "esac\n"
    )
    uv.chmod(0o755)
    for name in (
        "native/expected-gaps.json",
        "docs/architecture/target/studio-ui-expected.json",
        "tools/native_expected.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "-o", "core", "-o", "browser-runtime-install"]
        + [target, f"UV={uv}"],
        cwd=tmp_path,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert shown in result.stdout + result.stderr
    assert "as pinned in" not in result.stdout
