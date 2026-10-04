# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from filelock import FileLock

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation

ROOT = Path(__file__).parents[1]


@dataclass(frozen=True, slots=True)
class SelfRun:
    observation: Observation
    result: str
    artifact: bytes


def _parse_self_run(artifact: bytes, stdout: str) -> SelfRun:
    result = json.loads(stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == "PASS"
    # Complete observation preserves the real undecided boundary evidence.
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "n/a"
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    return SelfRun(observation, stdout, artifact)


def _load_self_run(directory: Path) -> SelfRun:
    directory.mkdir(exist_ok=True)
    output = directory / "architecture.json"
    result = directory / "result.json"
    with FileLock(str(directory) + ".lock"):
        if result.is_file():
            assert output.with_name("architecture.report.html").is_file()
            return _parse_self_run(output.read_bytes(), result.read_text())
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "archkeel.cli",
                "report",
                "--root",
                str(ROOT),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, (run.stdout, run.stderr)
        assert output.with_name("architecture.report.html").is_file()
        observed = _parse_self_run(output.read_bytes(), run.stdout)
        # Workers may reuse only a validated run; interrupted writes leave no completion marker.
        pending = result.with_suffix(".pending")
        pending.write_text(run.stdout)
        pending.replace(result)
        return observed


@pytest.fixture(scope="session")
def self_run(tmp_path_factory: pytest.TempPathFactory, worker_id: str) -> SelfRun:
    base = tmp_path_factory.getbasetemp()
    if worker_id != "master":
        base = base.parent
    return _load_self_run(base / "self-report")


@pytest.fixture(scope="session")
def self_observation(self_run: SelfRun) -> Observation:
    return self_run.observation


@pytest.fixture(scope="session")
def self_artifact_bytes(self_run: SelfRun) -> bytes:
    return self_run.artifact


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(error: object | None) -> None:
    # xdist can return success after a worker crashes during collection.
    if error is not None:
        pytest.exit(f"Test worker crashed: {error}", returncode=1)
