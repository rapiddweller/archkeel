# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1047: each CI job that runs the self-check of native/ installs `rustc-dev` and `llvm-tools`.

Without them the compiler type-reach facts are unavailable and the self-check holds many more gaps.
The components add about 160 MB, so one make target installs them, in these jobs only.
"""

from __future__ import annotations

import re

import pytest
from test_native_ci import _TOOLCHAIN_STEP, ROOT, WORKFLOWS, _jobs

_TYPE_REACH_STEP = "run: make type-reach-setup\n"
_SELF_CHECK_MAKE = re.compile(
    r"make (?:self-validate|pr-gate|ci-check|full-test|fast-test|report-gallery)\b"
)
# The jobs that run the self-check on every run, and the matrix jobs that run it in one area.
_SINGLE = [
    ("ci.yml", "lint", "run: make ci-pr-static"),
    ("pr-gate.yml", "base", "run: make pr-gate"),
    ("full-verification.yml", "full-suite-and-reports", "run: make ci-core-check"),
    ("pages.yml", "publish-gallery", "run: make core"),
]
_MATRIX = [("area-checks.yml", "tests"), ("full-verification.yml", "tests")]


@pytest.mark.parametrize(("workflow", "job", "first_make"), _SINGLE)
def test_the_toolchain_with_type_reach_installs_once_before_any_parallel_step(
    workflow: str, job: str, first_make: str
) -> None:
    # Parallel pytest workers that find no toolchain each start to install it and break each other.
    body = _jobs(workflow)[job]
    assert body.count(_TYPE_REACH_STEP) == 1
    assert _TOOLCHAIN_STEP not in body
    assert body.index(_TYPE_REACH_STEP) < body.index(first_make)


@pytest.mark.parametrize(("workflow", "job"), _MATRIX)
def test_only_the_area_that_runs_the_native_self_check_tests_installs_type_reach(
    workflow: str, job: str
) -> None:
    body = _jobs(workflow)[job]
    steps = [step for step in body.split("      - name: ") if _TYPE_REACH_STEP in step]
    assert len(steps) == 1
    assert "if: " in steps[0] and "matrix.area == 'CLI and core'" in steps[0]
    assert body.index(_TOOLCHAIN_STEP) < body.index(_TYPE_REACH_STEP)


def test_each_job_that_runs_the_self_check_installs_type_reach() -> None:
    checked = {
        (path.name, job)
        for path in WORKFLOWS.glob("*.yml")
        for job, body in _jobs(path.name).items()
        if _SELF_CHECK_MAKE.search(body)
    }
    assert {(w, j) for w, j, _ in _SINGLE} | set(_MATRIX) <= checked
    for workflow, job in sorted(checked):
        assert _TYPE_REACH_STEP in _jobs(workflow)[job], (workflow, job)


def test_the_operator_permission_to_build_is_set_in_one_place_for_the_self_runs() -> None:
    """AD-1130: only the Makefile targets of the self runs allow compilation."""
    root = ROOT
    makefile = (root / "Makefile").read_text()
    lines = [line for line in makefile.splitlines() if "ARCHKEEL_ALLOW_BUILD" in line]
    assigned = [line for line in lines if not line.startswith("#")]
    assert assigned == ["self-validate-native report-gallery: export ARCHKEEL_ALLOW_BUILD = 1"]
    for path in [*WORKFLOWS.glob("*.yml"), root / "native/archkeel.toml"]:
        assert "ARCHKEEL_ALLOW_BUILD" not in path.read_text(), path
    # `self-check` and the gate run the native self-check through this target.
    assert "self-validate: self-validate-native" in makefile
