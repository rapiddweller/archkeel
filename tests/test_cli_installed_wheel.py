# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-436: a platform wheel, installed alone, gives the verdict of its own core.

Consumer: a user who installs the wheel and has no checkout. `make native-wheel` builds the wheel
of each target of the matrix and gives it in `ARCHKEEL_NATIVE_WHEEL`. Without the variable the
test builds the wheel of this host from the release core of the checkout. Each run starts the
`archkeel` command of a new environment that is not below the checkout.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import rust_repository
from core_support import NATIVE, ROOT, SUFFIX, case_root, run
from filelock import FileLock

from archkeel.cli import core_only
from tools.release_core import NO_VERDICT

NAME = f"archkeel-core{SUFFIX}"
WINDOWS = os.name == "nt"


def _uv(*arguments: str, **environment: str) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "the installed-wheel tests need uv"
    kept = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ARCHKEEL_BUNDLE_NATIVE", "HATCH_BUILD_NO_HOOKS", "VIRTUAL_ENV"}
    }
    done = subprocess.run(
        [uv, *arguments], env={**kept, **environment}, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


@pytest.fixture(scope="module")
def reference(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The release core of the checkout: the binary that the wheel must carry."""
    if os.environ.get("ARCHKEEL_NATIVE_WHEEL"):
        # The wheel hook built it in the target directory of the checkout.
        return NATIVE / "target" / "release" / NAME
    built: Path = request.getfixturevalue("release_core")
    # A copy under the build lock: a build of another test session can replace the file.
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        return Path(shutil.copy2(built, tmp_path_factory.mktemp("core") / NAME))


@pytest.fixture(scope="module")
def wheel(reference: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    given = os.environ.get("ARCHKEEL_NATIVE_WHEEL")
    if given:
        return Path(given).resolve()
    output = tmp_path_factory.mktemp("wheel")
    _uv(
        *("build", "--wheel", "--no-sources", "--out-dir", str(output), str(ROOT)),
        ARCHKEEL_BUNDLE_NATIVE=str(reference),
        SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0",
    )
    (built,) = output.glob("*.whl")
    return built


class Installed:
    """One new environment that holds only the wheel."""

    def __init__(self, wheel: Path, directory: Path) -> None:
        assert not directory.resolve().is_relative_to(ROOT), directory
        venv = directory / "venv"
        _uv("venv", "--python", sys.executable, str(venv))
        # A copy, not a link: a test changes the installed files.
        install = ("pip", "install", "--no-deps", "--link-mode", "copy", "--python", str(venv))
        _uv(*install, str(wheel))
        scripts = venv / ("Scripts" if WINDOWS else "bin")
        self.command = scripts / f"archkeel{SUFFIX}"
        (self.core,) = venv.rglob(f"archkeel/_native/{NAME}")
        self.digest = self.core.with_name(NAME + ".sha256")
        # The environment of a user: no checkout on the import path, and no tool directory.
        self.environment = {
            key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PATH"}
        }
        system = Path(os.environ.get("SystemRoot", "")) / "System32"
        places = (system,) if WINDOWS else (Path("/usr/bin"), Path("/bin"))
        self.environment["PATH"] = os.pathsep.join(str(path) for path in places if path.is_dir())

    def run(
        self, *arguments: str, cwd: Path | None = None, path: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed `archkeel`, in `cwd` and with `path` first on `PATH`."""
        environment = dict(self.environment)
        if path is not None:
            environment["PATH"] = os.pathsep.join([str(path), environment["PATH"]])
        return subprocess.run(
            [str(self.command), *arguments],
            cwd=cwd or self.command.parent,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def validate(
        self, root: Path, form: str = "--json", cwd: Path | None = None, path: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self.run("validate", "--root", str(root), form, cwd=cwd, path=path)

    def refusal(self, root: Path) -> dict[str, Any]:
        """The typed refusal of `validate`: exit 2, UNKNOWN, no frame and no verdict."""
        done = self.validate(root)
        assert done.returncode == 2, (done.stdout, done.stderr)
        assert "Traceback" not in done.stderr, done.stderr
        result = json.loads(done.stdout)
        assert set(result) == {"status", "exit_code", "refusal"}, result
        assert result["status"] == "UNKNOWN" and result["exit_code"] == 2, result
        text = self.validate(root, "--text")
        assert text.returncode == 2, (text.stdout, text.stderr)
        assert text.stdout.startswith(f"REFUSED: {result['refusal']['kind']}: "), text.stdout
        assert "PASS" not in text.stdout
        refusal: dict[str, Any] = result["refusal"]
        return refusal


@pytest.fixture(scope="module")
def decides(wheel: Path) -> bool:
    """False for a platform whose core refuses each root, so its wheel gives no verdict."""
    return wheel.stem.rsplit("-", 1)[1] not in NO_VERDICT


@pytest.fixture(scope="module")
def installed(wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Installed:
    return Installed(wheel, tmp_path_factory.mktemp("installed"))


@pytest.fixture
def changed(wheel: Path, tmp_path: Path) -> Installed:
    """An environment of its own, for a test that changes the installed files."""
    return Installed(wheel, tmp_path / "changed")


@pytest.fixture
def crate(reference: Path, tmp_path: Path) -> Path:
    """A Rust project that the core decides with PASS."""
    return rust_repository.repository((tmp_path / "crate").resolve(), reference)


def _broken_crate(reference: Path, directory: Path) -> Path:
    # The app crate uses the base crate, and the contract does not allow it.
    parts = (
        rust_repository.component("base", "base_crate"),
        rust_repository.component("app", "app"),
    )
    return rust_repository.repository(directory.resolve(), reference, components=parts)


@pytest.fixture(params=["rust PASS", "rust FAIL", "typescript UNKNOWN"])
def project(
    request: pytest.FixtureRequest, reference: Path, tmp_path: Path
) -> Iterator[tuple[Path, str]]:
    """A project in its own Git repository, and the verdict that the core gives for it."""
    language, verdict = request.param.split()
    if language == "typescript":
        # One rule needs a rule kind that the core does not decide, so the run is UNKNOWN.
        with case_root("fixture/H-typescript") as root:
            yield root, verdict
    elif verdict == "PASS":
        yield rust_repository.repository((tmp_path / "crate").resolve(), reference), verdict
    else:
        yield _broken_crate(reference, tmp_path / "crate"), verdict


def _of_the_checkout(reference: Path, root: Path) -> tuple[int, dict[str, Any]]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: reference)
        return run("validate", "--root", str(root))


def test_the_installed_core_has_the_digest_that_the_wheel_records(
    wheel: Path, installed: Installed
) -> None:
    # The bytes of a later build of the checkout can differ, so the test reads only the wheel.
    # The verdict test compares the code digest and the frame with the core of the checkout.
    carried = hashlib.sha256(installed.core.read_bytes()).hexdigest()
    assert installed.digest.read_text(encoding="ascii") == carried
    assert WINDOWS or os.access(installed.core, os.X_OK)
    version = installed.run("--version")
    assert version.stdout.strip() == f"archkeel {wheel.name.split('-')[1]}", version


def test_the_installed_wheel_gives_the_verdict_of_its_core(
    installed: Installed, reference: Path, project: tuple[Path, str], decides: bool
) -> None:
    root, verdict = project
    done = installed.validate(root)
    result = json.loads(done.stdout)
    code, checkout = _of_the_checkout(reference, root)
    statuses = {row[1] for row in result.get("frame", {}).get("rules", {}).values()}

    assert result["exit_code"] == done.returncode == code, (result, done.stderr)
    assert result["status"] == checkout["status"]
    if not decides:
        # The core of this platform refuses each root: no verdict, and never a PASS (AD-436).
        assert done.returncode == 2 and result["status"] == "UNKNOWN", result
        assert result["refusal"] == checkout["refusal"], result
        assert "is not canonical" in result["refusal"]["message"], result
        assert not statuses & {"PASS", "FAIL"}, result
        return
    # The installed shell ran the binary of its own package, never the core of the checkout.
    assert Path(result["core"]["path"]) == installed.core, result["core"]
    assert result["core"]["code_digest"] == checkout["core"]["code_digest"]
    assert result["frame"] == checkout["frame"]
    assert (result["status"], code) == (verdict, {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[verdict])
    assert "refusal" not in result, result
    expected = {"PASS": {"PASS"}, "FAIL": {"PASS", "FAIL"}}.get(verdict)
    assert statuses == expected if expected else "PASS" in statuses, result


def test_a_wheel_without_its_binary_or_digest_refuses(changed: Installed, crate: Path) -> None:
    saved = changed.digest.read_bytes()
    changed.digest.unlink()
    assert changed.refusal(crate)["kind"] == "core_binary_not_found"
    changed.digest.write_bytes(saved)
    changed.core.unlink()
    assert changed.refusal(crate)["kind"] == "core_binary_not_found"
    changed.digest.unlink()
    refusal = changed.refusal(crate)
    assert refusal["kind"] == "core_binary_not_found"
    assert "install a platform wheel of archkeel" in refusal["message"]


def test_a_wheel_with_a_wrong_digest_refuses(changed: Installed, crate: Path) -> None:
    recorded = changed.digest.read_text(encoding="ascii")
    changed.digest.write_text("0" * 64, encoding="ascii")
    refusal = changed.refusal(crate)
    assert refusal["kind"] == "core_error" and "digest does not match" in refusal["message"]
    # A changed binary with the recorded digest of the build.
    changed.digest.write_text(recorded, encoding="ascii")
    with changed.core.open("ab") as stream:
        stream.write(b"\0")
    refusal = changed.refusal(crate)
    assert refusal["kind"] == "core_error" and "digest does not match" in refusal["message"]


@pytest.mark.skipif(WINDOWS, reason="Windows has no executable bit")
def test_a_wheel_with_a_binary_that_cannot_start_refuses(changed: Installed, crate: Path) -> None:
    changed.core.chmod(0o644)
    refusal = changed.refusal(crate)
    assert refusal["kind"] == "core_error" and "could not execute" in refusal["message"]


def _plant(reference: Path, *places: Path) -> None:
    """Put a core that decides, with its digest, at each place that a lookup could read."""
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    for place in places:
        place.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference, place / NAME)
        (place / f"{NAME}.sha256").write_text(digest, encoding="ascii")


def test_the_lookup_never_runs_a_binary_of_the_project_the_directory_or_the_path(
    changed: Installed, reference: Path, crate: Path, tmp_path: Path, decides: bool
) -> None:
    cwd, tools = tmp_path / "cwd", tmp_path / "tools"
    (crate / "native/core").mkdir(parents=True)
    (crate / "native/core/Cargo.toml").write_text('[package]\nname = "archkeel-core"\n')
    places = (crate, crate / "_native", crate / "archkeel/_native", crate / "native/target/release")
    _plant(reference, *places, cwd, cwd / "_native", tools)
    rust_repository.commit_tree(crate)

    if decides:
        done = changed.validate(crate, cwd=cwd, path=tools)
        assert Path(json.loads(done.stdout)["core"]["path"]) == changed.core, done.stdout
    # Without its own core the package refuses: no planted binary answers.
    changed.core.unlink()
    changed.digest.unlink()
    for run_in in (cwd, crate):
        done = changed.validate(crate, cwd=run_in, path=tools)
        result = json.loads(done.stdout)
        assert done.returncode == 2 and "frame" not in result, result
        assert result["refusal"]["kind"] == "core_binary_not_found", result


def test_an_installed_package_never_runs_a_build_output_beside_its_environment(
    changed: Installed, reference: Path, crate: Path
) -> None:
    """The checkout lookup is for a package below `src/` of a checkout, not for an install."""
    beside = changed.core.parents[3]
    (beside / "native/core").mkdir(parents=True)
    (beside / "native/core/Cargo.toml").write_text('[package]\nname = "archkeel-core"\n')
    (beside / "pyproject.toml").write_text('[project]\nname = "archkeel"\n')
    _plant(reference, beside / "native/target/release", beside / "native/target/debug")
    shutil.rmtree(changed.core.parent)

    refusal = changed.refusal(crate)
    assert refusal["kind"] == "core_binary_not_found", refusal
    assert "install a platform wheel of archkeel" in refusal["message"]
