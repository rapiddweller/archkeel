# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from areas import AREAS, area_of
from filelock import FileLock

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation

ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def no_step_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test must never append to the CI job summary; CI test jobs showed such rows."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@dataclass(frozen=True, slots=True)
class SelfRun:
    observation: Observation
    result: str
    artifact: bytes


def _parse_self_run(artifact: bytes, stdout: str) -> SelfRun:
    result = json.loads(stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == "PASS", [
        (rule["id"], rule["status"], rule["undecided"])
        for rule in result["rule_assessments"]
        if rule["status"] != "PASS"
    ]
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
        # A string message is shown whole; a tuple is cut before the diagnostics.
        assert run.returncode == 0, f"{run.stdout}\n{run.stderr}"
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


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--area", choices=AREAS, help="run only the test files of this area")


# These files are each longer than a quarter of their job; they have no module-scoped fixtures.
_SPREAD_PER_TEST = frozenset(
    {
        "test_architecture_demo.py",
        "test_typescript_control_target.py",
        "test_boundary_type_bound_aliases.py",
    }
)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    area = config.getoption("area")
    if area is not None:
        kept = [item for item in items if area_of(item.path.name) == area]
        if not kept:
            raise pytest.UsageError(f"--area={area} selects no tests")
        config.hook.pytest_deselected(
            items=[item for item in items if area_of(item.path.name) != area]
        )
        items[:] = kept
    # With --dist=loadgroup, a file stays on one worker so its module fixtures run once.
    for item in items:
        if item.path.name not in _SPREAD_PER_TEST:
            item.add_marker(pytest.mark.xdist_group(item.path.name))
