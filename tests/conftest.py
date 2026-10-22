# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import argparse
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


def _shard(value: str) -> tuple[int, int]:
    index, _, total = value.partition("/")
    if not (index.isdigit() and total.isdigit() and int(index) < int(total)):
        raise argparse.ArgumentTypeError(f"expected I/N with 0 <= I < N, got {value!r}")
    return int(index), int(total)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--shard", type=_shard, help="run every N-th collected test from I: I/N")


_SELF_FIXTURES = frozenset({"self_run", "self_observation", "self_artifact_bytes"})
_SELF_GROUP = "self-report"
# ponytail: measured on CI (Oct 2026), the self report is about half of one shard's run time;
# recalibrate from the shard durations when that changes.
_SELF_REPORT_SHARE = 0.5


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "shard_group(name): keep a module's tests in one PR shard (shared setup)"
    )


def _shard_group(item: pytest.Item) -> str | None:
    if isinstance(item, pytest.Function) and not _SELF_FIXTURES.isdisjoint(item.fixturenames):
        return _SELF_GROUP
    marker = item.get_closest_marker("shard_group")
    return str(marker.args[0]) if marker is not None else None


def _shard_assignments(items: list[pytest.Item], total: int) -> list[int]:
    """Build each shared setup in one shard, then balance the remaining tests by count."""
    groups: dict[str, list[int]] = {}
    singles: list[int] = []
    for number, item in enumerate(items):
        name = _shard_group(item)
        if name is None:
            singles.append(number)
        else:
            members: list[int] = groups.setdefault(name, [])
            members.append(number)
    loads = [0.0] * total
    assignments = [0] * len(items)
    # The self report goes first so it lands in shard 0; larger groups are placed before smaller.
    order = sorted(groups, key=lambda name: (name != _SELF_GROUP, -len(groups[name]), name))
    for name in order:
        shard = min(range(total), key=loads.__getitem__)
        loads[shard] += len(groups[name])
        if name == _SELF_GROUP:
            loads[shard] += len(items) / total * _SELF_REPORT_SHARE
        for number in groups[name]:
            assignments[number] = shard
    for number in singles:
        # Round-robin by test, not by file: one slow file must not pin a whole shard.
        shard = min(range(total), key=loads.__getitem__)
        loads[shard] += 1
        assignments[number] = shard
    return assignments


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    shard = config.getoption("shard")
    if shard is None:
        return
    index, total = shard
    assignments = _shard_assignments(items, total)
    kept = [item for item, assigned in zip(items, assignments, strict=True) if assigned == index]
    if not kept:
        raise pytest.UsageError(f"--shard={index}/{total} selects no tests")
    config.hook.pytest_deselected(
        items=[item for item, assigned in zip(items, assignments, strict=True) if assigned != index]
    )
    items[:] = kept
