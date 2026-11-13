# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from filelock import FileLock

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation
from archkeel.ir.store_seam import active_store, close_store

ROOT = Path(__file__).parents[1]
SELF_RULE_UNKNOWN = frozenset(
    {
        "COMPONENT-NO-CYCLES",
        "INTERFACE-BOUNDARY",
        "MODULE-NO-CYCLES",
        "REQUIRES-COMPLETE",
    }
)


@pytest.fixture(autouse=True)
def no_step_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test must never append to the CI job summary; CI test jobs showed such rows."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture(autouse=True)
def no_store_left() -> Iterator[None]:
    """A test that ends with an open Rust store fails (AD-346).

    The store stays active until the next observation or `close_store`. A test that leaves it
    open makes the Python writer refuse each later observation in the same worker, so a test far
    away fails. The guard closes the store and fails the test that left it open.
    """
    yield
    if active_store() is not None:
        close_store()
        pytest.fail("the test left the Rust store open (AD-346): call close_store in teardown")


@dataclass(frozen=True, slots=True)
class SelfRun:
    observation: Observation
    result: str
    artifact: bytes


def _parse_self_run(artifact: bytes, stdout: str) -> SelfRun:
    result = json.loads(stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == "UNKNOWN"
    assessments = result["rule_assessments"]
    assert {rule["id"] for rule in assessments if rule["status"] == "UNKNOWN"} == set(
        SELF_RULE_UNKNOWN
    )
    assert all(
        rule["status"] == "UNKNOWN"
        and not rule["evaluation_proven"]
        and rule["count"] == rule["undecided"] == 0
        and rule["reason"] == "No complete evaluator receipt exists for this rule and scope."
        if rule["id"] in SELF_RULE_UNKNOWN
        else rule["status"] == "PASS"
        and rule["evaluation_proven"]
        and rule["count"] == rule["undecided"] == 0
        for rule in assessments
    )
    assert result["measurements"]["scalars"]["unknown_positions"] == 0
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
def _self_report_directory(tmp_path_factory: pytest.TempPathFactory, worker_id: str) -> Path:
    base = tmp_path_factory.getbasetemp()
    if worker_id != "master":
        base = base.parent
    return base / "self-report"


def _warm_self_run(directory: Path) -> None:
    # A failure is shown by the first consumer test, which runs the report again.
    with contextlib.suppress(Exception):
        _load_self_run(directory)


@pytest.fixture(scope="session", autouse=True)
def _start_self_run(request: pytest.FixtureRequest) -> Iterator[None]:
    """Start the self-run before the first test, so no worker idles in its first consumer."""
    consumers = any(
        isinstance(item, pytest.Function) and "self_run" in item.fixturenames
        for item in request.session.items
    )
    if not consumers:
        yield
        return
    # Looked up here, not as a parameter: a run without xdist has no `worker_id` fixture.
    directory: Path = request.getfixturevalue("_self_report_directory")
    warm = threading.Thread(target=_warm_self_run, args=(directory,), daemon=True)
    warm.start()
    yield
    # A worker must not exit while its run still writes the shared output.
    warm.join()


@pytest.fixture(scope="session")
def self_run(_self_report_directory: Path) -> SelfRun:
    return _load_self_run(_self_report_directory)


@pytest.fixture(scope="session")
def self_observation(self_run: SelfRun) -> Observation:
    return self_run.observation


@pytest.fixture(scope="session")
def self_artifact_bytes(self_run: SelfRun) -> bytes:
    return self_run.artifact


def install_rust_toolchain(cargo: str) -> None:
    """Install the toolchain that native/rust-toolchain.toml pins, under the build lock.

    rustup installs a missing toolchain at the first `cargo` call. Two such calls at the same time
    fail to rename the same download, so a test that runs `cargo` without the lock calls this first.
    """
    native = ROOT / "native"
    (native / "target").mkdir(exist_ok=True)
    with FileLock(str(native / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            [cargo, "--version"], cwd=native, capture_output=True, text=True, check=False
        )
    assert done.returncode == 0, done.stderr


def build_native_copy(
    factory: pytest.TempPathFactory,
    label: str,
    features: tuple[str, ...] = (),
    binary: str = "archkeel-typescript-collector",
) -> Path:
    """Build the debug collector and copy it for this worker (AD-316).

    All workers of all test sessions on this checkout share one build lock. The lock covers the
    build and the copy: a worker never copies the file while another worker builds. The `dump`
    feature has a target directory of its own, because it changes the binary. A copy that fails
    after a good build is tried once more, and the second error is the one that shows.
    """
    cargo = shutil.which("cargo")
    # A Rust toolchain is required only for changes in native/; CI always has one.
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native TypeScript collector tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    native = ROOT / "native"
    target = native / "target"
    command = [cargo, "build", "--manifest-path", str(native / "Cargo.toml"), "--locked"]
    if features:
        target = target / "dump"
        command += ["--features", ",".join(features), "--target-dir", str(target)]
    name = binary + (".exe" if os.name == "nt" else "")
    copy = factory.mktemp(label) / name
    (native / "target").mkdir(exist_ok=True)
    with FileLock(str(native / "target" / ".pytest-native-build.lock")):
        for attempt in (1, 2):
            built = subprocess.run(
                command,
                # The working directory selects the toolchain that native/rust-toolchain.toml pins.
                cwd=native,
                capture_output=True,
                text=True,
                check=False,
            )
            assert built.returncode == 0, built.stderr
            try:
                shutil.copy2(target / "debug" / name, copy)
            except FileNotFoundError:
                if attempt == 2:
                    raise
            else:
                break
    return copy


@pytest.fixture(scope="session")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The debug build of the native TypeScript collector (AD-316), copied for its own tests."""
    return build_native_copy(tmp_path_factory, "native")


@pytest.fixture(scope="session")
def dump_binary(native_binary: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The native TypeScript collector with its test-only syntax dump."""
    assert native_binary.is_file()
    return build_native_copy(tmp_path_factory, "native-dump", ("dump",))


@pytest.fixture(scope="session")
def python_dump_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The native Python collector with the test-only `dump` feature (AD-334)."""
    return build_native_copy(
        tmp_path_factory, "native-dump-python", ("dump",), binary="archkeel-python-collector"
    )


@pytest.fixture(scope="session")
def rust_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The debug build of the native Rust collector (AD-335), copied for its own tests."""
    return build_native_copy(tmp_path_factory, "native-rust", binary="archkeel-rust-collector")


@pytest.fixture(scope="session")
def store_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The debug build of the Rust store (AD-346), copied for its own tests."""
    return build_native_copy(tmp_path_factory, "store", binary="archkeel-store")


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(error: object | None) -> None:
    # xdist can return success after a worker crashes during collection.
    if error is not None:
        pytest.exit(f"Test worker crashed: {error}", returncode=1)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--area", help="run only the test files of this area (tests/areas.py)")
    parser.addoption("--selection", help="run only the tests of this selection (tests/areas.py)")


_SHARED_SCOPES = frozenset({"class", "module", "package"})


def _shares_a_fixture(item: pytest.Item) -> bool:
    """True if the test uses a fixture that other tests of its file reuse in the same process.

    A session fixture runs once in each worker in all cases, so it does not count. An item without
    fixture data, for example a doctest, stays with its file.
    """
    info = getattr(item, "_fixtureinfo", None)
    if info is None:
        return True
    return any(
        definition.scope in _SHARED_SCOPES
        for definitions in info.name2fixturedefs.values()
        for definition in definitions
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
    # With --dist=loadgroup, a test without a group can run on any free worker. The tests of a file
    # that use a module, class or package fixture stay on one worker, so that the fixture runs once.
    # A whole file on one worker sets the least time of its job: one file took 17 minutes in Full.
    for item in items:
        if _shares_a_fixture(item):
            item.add_marker(pytest.mark.xdist_group(item.path.name))
    # The self-run takes minutes on a runner. Its consumers come last, so that the other workers run
    # other tests while one worker builds it, and do not wait for its lock. The sort is stable.
    items.sort(key=lambda item: "self_run" in getattr(item, "fixturenames", ()))
