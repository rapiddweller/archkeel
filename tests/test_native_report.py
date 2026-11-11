# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-371: the frames of `archkeel-report` are valid report v2 payloads.

The Rust test `write_built_samples_for_the_schema_test` builds frames from the inputs of the
oracle payloads, with and without the graph and the Target. Each frame and each oracle payload
of `native/report/testdata` must validate against `schema/report-2.0.schema.json` and pass the
Python checker, and a frame built from the inputs of an oracle payload must equal its bytes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest
from filelock import FileLock

from archkeel.report.payload.checker import check_payload

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
    (NATIVE / "target").mkdir(exist_ok=True)
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
    errors = [error.message for error in VALIDATOR.iter_errors(payload)]
    try:
        check_payload(payload)
    except ValueError as error:
        errors.append(str(error))
    return errors


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
