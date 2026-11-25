# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1047: only the CI area that runs the type-reach tests installs `rustc-dev` and `llvm-tools`.

The tests skip without them, and the components add about 160 MB. The self-scan of `native/` has the
option off (9 cold `cargo check` runs exceed the job cap), so no other job needs them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_native_ci import _TOOLCHAIN_STEP, _jobs

_TYPE_REACH_STEP = "run: make type-reach-setup\n"
_MATRIX = [("area-checks.yml", "tests"), ("full-verification.yml", "tests")]


@pytest.mark.parametrize(("workflow", "job"), _MATRIX)
def test_only_the_area_that_runs_the_type_reach_tests_installs_type_reach(
    workflow: str, job: str
) -> None:
    body = _jobs(workflow)[job]
    steps = [step for step in body.split("      - name: ") if _TYPE_REACH_STEP in step]
    assert len(steps) == 1
    assert "if: " in steps[0] and "matrix.area == 'CLI and core'" in steps[0]
    assert body.index(_TOOLCHAIN_STEP) < body.index(_TYPE_REACH_STEP)


def test_the_self_scan_of_native_has_the_option_off_until_the_job_cap_allows_it() -> None:
    config = (Path(__file__).resolve().parents[1] / "native/archkeel.toml").read_text()
    assert "rust_type_reach = false" in config
