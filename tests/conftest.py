# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
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
    parser.addoption("--area", help="run only the test files of this area (tests/areas.py)")
    parser.addoption("--selection", help="run only the tests of this selection (tests/areas.py)")


# These files are each longer than a quarter of their job; they have no module-scoped fixtures.
_SPREAD_PER_TEST = frozenset(
    {
        "test_architecture_demo.py",
        "test_typescript_control_target.py",
        "test_boundary_type_bound_aliases.py",
    }
)


def _select(name: str, items: list[pytest.Item]) -> list[pytest.Item]:
    from areas import PYTHON_COMPAT, SELECTIONS, selects

    if name not in SELECTIONS:
        raise pytest.UsageError(f"--selection={name} is not a selection in tests/areas.py")
    entries = SELECTIONS[name]
    ids = [f"{item.path.name}::{item.nodeid.partition('::')[2]}" for item in items]
    files = {item.path.name for item in items}
    # A stale entry must fail: an explicit path on the command line failed as "not found".
    stale = [
        entry
        for entry in entries
        if not (ROOT / "tests" / entry.partition("::")[0]).is_file()
        or (entry.partition("::")[0] in files and not any(selects(entry, i) for i in ids))
    ]
    if stale:
        raise pytest.UsageError(f"--selection={name} names no test: {stale}")
    return [
        item
        for item, test_id in zip(items, ids, strict=True)
        if any(selects(entry, test_id) for entry in entries)
        or (name == PYTHON_COMPAT and item.get_closest_marker("requires_python") is not None)
    ]


def by_python(minor: int) -> list[object]:
    """Split a version-dependent test: False runs below Python 3.<minor>, True from 3.<minor>."""
    return [
        pytest.param(False, marks=pytest.mark.requires_python(below=minor), id=f"below-3.{minor}"),
        pytest.param(True, marks=pytest.mark.requires_python(minor), id=f"3.{minor}"),
    ]


def _gated_minors() -> set[int]:
    # The classifiers name the versions that Full tests; a gate at the oldest one gates nothing.
    classifiers = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["classifiers"]
    minors = {
        int(found[1])
        for classifier in classifiers
        if (found := re.fullmatch(r"Programming Language :: Python :: 3\.(\d+)", classifier))
    }
    return minors - {min(minors)}


def _python_gate(mark: pytest.Mark, minors: set[int]) -> str | None:
    minimum = mark.args[0] if mark.args else None
    below = mark.kwargs.get("below")
    for minor in (minimum, below):
        if minor is not None and minor not in minors:
            raise pytest.UsageError(f"requires_python: Full verification tests no Python 3.{minor}")
    if minimum is not None and sys.version_info < (3, minimum):
        return f"needs Python 3.{minimum}"
    if below is not None and sys.version_info >= (3, below):
        return f"needs Python below 3.{below}"
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marked = [(item, mark) for item in items for mark in item.iter_markers("requires_python")]
    minors = _gated_minors() if marked else set()
    # The area jobs run the oldest Python; make python-compat runs these tests (tests/areas.py).
    for item, mark in marked:
        if (reason := _python_gate(mark, minors)) is not None:
            item.add_marker(pytest.mark.skip(reason=reason))
    selection = config.getoption("selection")
    if selection is not None:
        kept = _select(selection, items)
        chosen = set(kept)
        config.hook.pytest_deselected(items=[item for item in items if item not in chosen])
        items[:] = kept
    area = config.getoption("area")
    if area is not None:
        # Imported here: some tests copy this file alone into a temporary project.
        from areas import AREAS, area_of

        if area not in AREAS:
            raise pytest.UsageError(f"--area={area} is not an area in tests/areas.py")
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
