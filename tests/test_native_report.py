# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The model, evaluator and engine-frame barriers (AD-381, AD-388)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import ensure_target_dir
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
# The attempts of AD-381: the run proof in the barrier crate, the report and the evaluator in
# their own document tests (the barrier crate is below them in the crate order, AD-382).
# AD-385 adds the attempts of the models of a tree to the barrier crate.
BARRIER = NATIVE / "model-barrier/src/lib.rs"
ATTEMPTS = {
    "archkeel-model-barrier": [
        (BARRIER, "# The run proof (AD-381)", 4),
        (BARRIER, "# The models of a tree (AD-385)", 4),
    ],
    "archkeel-report": [
        (NATIVE / "report/src/lib.rs", "# The barrier of the engine frame (AD-388)", 8)
    ],
    "archkeel-eval": [(NATIVE / "eval/src/lib.rs", "# The barrier of the evaluator (AD-381)", 1)],
}


def test_each_barrier_attempt_of_ad_381_fails_with_its_error_code() -> None:
    """S2 of the review of #1080: a stable rustdoc does not check the error code of a
    `compile_fail` test. `RUSTC_BOOTSTRAP=1` makes it check: rustdoc compiles each attempt on
    its own and fails when the named code is not the error. Each attempt of AD-381 names one."""
    for path, heading, count in [section for sections in ATTEMPTS.values() for section in sections]:
        section = path.read_text(encoding="utf-8").split(heading, 1)[1].split("\n//! # ", 1)[0]
        fences = re.findall(r"^//! ```(compile_fail\S*)$", section, re.M)
        assert len(fences) == count, path
        assert all(re.fullmatch(r"compile_fail,E\d{4}", fence) for fence in fences), fences
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native report tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    command = [cargo, "test", "--locked", "-q", "--doc"]
    for crate in ATTEMPTS:
        command += ["-p", crate]
    ensure_target_dir(NATIVE)
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command,
            cwd=NATIVE,
            env={**os.environ, "RUSTC_BOOTSTRAP": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stdout + done.stderr
