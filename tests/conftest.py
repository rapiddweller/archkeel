# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import built as built
from core_support import core_binary as core_binary
from core_support import ensure_target_dir
from core_support import release_core as release_core
from filelock import FileLock

ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def no_step_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test must never append to the CI job summary; CI test jobs showed such rows."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def install_rust_toolchain(cargo: str) -> None:
    """Install the toolchain that native/rust-toolchain.toml pins, under the build lock.

    rustup installs a missing toolchain at the first `cargo` call. Two such calls at the same time
    fail to rename the same download, so a test that runs `cargo` without the lock calls this first.
    """
    native = ROOT / "native"
    ensure_target_dir(native)
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
    ensure_target_dir(native)
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


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(error: object | None) -> None:
    # xdist can return success after a worker crashes during collection.
    if error is not None:
        pytest.exit(f"Test worker crashed: {error}", returncode=1)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--area", help="run only the test files of this area (tests/areas.py)")


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


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
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
