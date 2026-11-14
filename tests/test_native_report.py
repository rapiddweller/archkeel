# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-371: the frames of `archkeel-report` are valid report v2 payloads.

The Rust test `write_built_samples_for_the_schema_test` builds frames from the inputs of the
oracle payloads, with and without the graph and the Target. Each frame and each oracle payload
of `native/report/testdata` must validate against `schema/report-2.0.schema.json`, and a frame
built from the inputs of an oracle payload must equal its bytes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest
from core_support import ensure_target_dir
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
TESTDATA = NATIVE / "report" / "testdata"
VALIDATOR = jsonschema.Draft202012Validator(
    json.loads((ROOT / "schema" / "report-2.0.schema.json").read_text(encoding="utf-8"))
)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native report tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    out = tmp_path_factory.mktemp("report-samples")
    command = [cargo, "test", "--locked", "-q", "-p", "archkeel-report", "--lib"]
    command += ["write_built_samples_for_the_schema_test"]
    ensure_target_dir(NATIVE)
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command,
            cwd=NATIVE,
            env={**os.environ, "ARCHKEEL_REPORT_SAMPLES": str(out)},
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stdout + done.stderr
    return out


def _errors(path: Path) -> list[str]:
    payload = json.loads(path.read_bytes())
    return [error.message for error in VALIDATOR.iter_errors(payload)]


def test_each_oracle_payload_of_the_testdata_is_valid() -> None:
    paths = sorted(TESTDATA.glob("*.report-v2.json"))
    assert len(paths) >= 12
    assert {path.name: _errors(path) for path in paths} == {path.name: [] for path in paths}


def test_each_built_frame_is_valid_and_equals_its_oracle(built: Path) -> None:
    paths = sorted(built.glob("*.json"))
    assert len(paths) == 8
    assert {path.name: _errors(path) for path in paths} == {path.name: [] for path in paths}
    for path in built.glob("*.built.json"):
        oracle = TESTDATA / path.name.replace(".built.json", ".report-v2.json")
        assert path.read_bytes() == oracle.read_bytes(), path.name


def test_the_frame_without_graph_carries_no_edge_and_names_imports(built: Path) -> None:
    for path in built.glob("*.no-graph-no-target.json"):
        payload = json.loads(path.read_bytes())
        assert payload["edges"]["level"] == []
        assert payload["run"]["not_carried"][:2] == [0, 1]
        assert payload["run"]["target"] is False
        assert payload["summary"]["status"] == "UNKNOWN"
        assert 2 in payload["unknowns"]["source"]


# The attempts of AD-381: the run proof in the barrier crate, the report and the evaluator in
# their own document tests (the barrier crate is below them in the crate order, AD-382).
# AD-385 adds the attempts of the models of a tree to the barrier crate.
BARRIER = NATIVE / "model-barrier/src/lib.rs"
ATTEMPTS = {
    "archkeel-model-barrier": [
        (BARRIER, "# The run proof (AD-381)", 4),
        (BARRIER, "# The models of a tree (AD-385)", 4),
    ],
    "archkeel-report": [(NATIVE / "report/src/lib.rs", "# The barrier of the report (AD-381)", 4)],
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
