# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-316, AD-317, AD-436, AD-476: CI checks the native code; a release has six platform wheels."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import zipfile
from pathlib import Path
from textwrap import dedent

import pytest

from tools import release_core
from tools.publish_release import PLATFORM_TAGS

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _jobs(workflow: str) -> dict[str, str]:
    text = (WORKFLOWS / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_every_action_is_pinned_to_a_commit() -> None:
    # A tag can move to other code; a commit SHA cannot.
    for path in WORKFLOWS.glob("*.yml"):
        for action in re.findall(r"^\s+(?:- )?uses: (\S+)", path.read_text(), re.MULTILINE):
            if not action.startswith("./"):
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), (path.name, action)


def test_the_pr_gate_runs_only_the_linux_rust_checks() -> None:
    jobs = _jobs("ci.yml")
    native = jobs["native"]
    assert "runs-on: ubuntu-24.04\n" in native
    assert native.index("run: make cargo-deny-install") < native.index("run: make native-check")
    rust = [job for job, body in jobs.items() if re.search(r"make native-|cargo|macos", body)]
    assert rust == ["native"]
    assert "run: make native-check\n" in native


_TOOLCHAIN_STEP = "run: rustup toolchain install\n"


@pytest.mark.parametrize(
    ("workflow", "job", "first_make"),
    [
        ("ci.yml", "lint", "run: make ci-pr-static"),
        ("ci.yml", "tests", "run: make pr-test"),
        ("ci.yml", "native", "run: make cargo-deny-install"),
        ("full-verification.yml", "full-suite-and-reports", "run: make ci-core-check"),
        ("full-verification.yml", "tests", "run: make full-test"),
        ("full-verification.yml", "shell-compat", "run: make shell-compat"),
    ],
)
def test_the_pinned_toolchain_installs_once_before_any_parallel_step(
    workflow: str, job: str, first_make: str
) -> None:
    # Parallel pytest workers that find no toolchain each start to install it and break each other.
    body = _jobs(workflow)[job]
    assert body.count(_TOOLCHAIN_STEP) == 1
    assert "working-directory: native\n        run: rustup toolchain install" in body
    assert body.index(_TOOLCHAIN_STEP) < body.index(first_make)


# A parent make (`make pr-test`) passes MAKELEVEL on, and GNU make 4 then prints "Leaving directory"
# after the commands of the child. The child must not know that it runs inside a make.
_MAKE_ENV = {k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS", "MAKELEVEL"}}


def _dry_run(*arguments: str) -> str:
    return subprocess.run(
        ["make", "--no-print-directory", "-n", *arguments, "UV=uv"],
        cwd=ROOT,
        env=_MAKE_ENV,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_full_builds_each_platform_wheel_on_its_own_target() -> None:
    jobs = _jobs("full-verification.yml")
    wheel_jobs = {job: body for job, body in jobs.items() if job.startswith("native-wheel-")}
    assert set(wheel_jobs) == {"native-wheel-linux", "native-wheel-macos", "native-wheel-windows"}
    text = "".join(wheel_jobs.values())
    tags = re.findall(r"tag: (py3-none-\w+)|NATIVE_TAG=(py3-none-\w+)", text)
    assert sorted(a or b for a, b in tags) == sorted(PLATFORM_TAGS)
    for body in wheel_jobs.values():
        assert "make native-wheel NATIVE_TAG=" in body
        assert re.search(r"name: native-wheel-.+\n\s+path: dist/native/\*\.whl\n", body)
        assert "if-no-files-found: error" in body
    # The image sets the oldest glibc or musl; a moving image tag changes the wheel.
    images = re.findall(r"image: (\S+)", wheel_jobs["native-wheel-linux"])
    assert len(images) == 3
    assert all(re.fullmatch(r"quay\.io/pypa/\w+:[\w.-]+@sha256:[0-9a-f]{64}", i) for i in images)
    assert "runs-on: ${{ matrix.runner }}" in wheel_jobs["native-wheel-linux"]
    assert "runner: ubuntu-24.04-arm\n" in wheel_jobs["native-wheel-linux"]


def _add_script() -> str:
    build = _jobs("release.yml")["build"]
    assert "pattern: native-wheel-*\n" in build and "path: native-wheels/\n" in build
    step = build.split("- name: Add the platform wheels that full verification built and ran\n")
    return dedent(step[1].split("        run: |\n", 1)[1].split("\n\n", 1)[0])


def test_a_release_adds_every_platform_wheel_of_full(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "native-wheels").mkdir()
    (tmp_path / "dist/archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    for tag in PLATFORM_TAGS:
        (tmp_path / "native-wheels" / f"archkeel-5.0.0-{tag}.whl").write_bytes(b"wheel")
    result = subprocess.run(
        ["bash", "-c", _add_script()], cwd=tmp_path, check=False, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "dist").glob("*.whl"))) == len(PLATFORM_TAGS)
    assert len(list((tmp_path / "dist").glob("*.tar.gz"))) == 1


@pytest.mark.parametrize("wheels,sdists", [(n, 1) for n in range(8)] + [(6, 0), (6, 2)])
@pytest.mark.parametrize("pure", ["", "dist", "native-wheels"])
def test_release_requires_exactly_six_platform_wheels_and_one_sdist(
    tmp_path: Path, wheels: int, sdists: int, pure: str
) -> None:
    """A wheel without a platform carries no core (AD-436): it stops the step where it is."""
    script = _add_script()
    (tmp_path / "dist").mkdir()
    (tmp_path / "native-wheels").mkdir()
    if pure:
        (tmp_path / pure / "archkeel-5.0.0-py3-none-any.whl").write_bytes(b"pure")
    for index in range(wheels - (pure == "native-wheels")):
        (tmp_path / "native-wheels" / f"archkeel-5.0.0-py3-none-platform{index}.whl").write_bytes(
            b"wheel"
        )
    for index in range(sdists):
        (tmp_path / "dist" / f"archkeel-5.0.{index}.tar.gz").write_bytes(b"sdist")
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (wheels == 6 and sdists == 1 and not pure)
    if result.returncode == 0:
        assert len(list((tmp_path / "dist").glob("*.whl"))) == 6


def _unbuilt(tags: tuple[str, ...]) -> set[str]:
    """The platforms of a release that no job of Full builds, installs and runs."""
    jobs = _jobs("full-verification.yml")
    wheel_jobs = {job: body for job, body in jobs.items() if job.startswith("native-wheel-")}
    assert all("make native-wheel NATIVE_TAG=" in body for body in wheel_jobs.values())
    assert all(f"      - {job}\n" in jobs["verified"] for job in wheel_jobs)
    text = "".join(wheel_jobs.values())
    built = {a or b for a, b in re.findall(r"tag: (py3-none-\w+)|NATIVE_TAG=(py3-none-\w+)", text)}
    return set(tags) - built


def test_a_release_is_open_and_publishes_only_platforms_that_full_builds_and_runs() -> None:
    """AD-476: no flag and no first job close the release; Full is the gate for each wheel."""
    workflow = (WORKFLOWS / "release.yml").read_text()
    assert "PUBLISH_NATIVE_WHEELS" not in workflow and "core-in-wheel" not in workflow
    jobs = _jobs("release.yml")
    assert "needs:" not in jobs["verify"] and "    needs: verify\n" in jobs["build"]
    assert not hasattr(release_core, "NO_VERDICT")
    assert _unbuilt(PLATFORM_TAGS) == set()
    # A listed platform that Full does not build and run is found.
    assert _unbuilt((*PLATFORM_TAGS, "py3-none-win_arm64")) == {"py3-none-win_arm64"}


def test_the_release_build_checks_the_core_of_the_wheels_before_it_uploads_them() -> None:
    build = _jobs("release.yml")["build"]
    check = "run: python3 -m tools.release_core dist dist/archkeel-*-py3-none-manylinux_2_17_x86_64"
    added = build.index("- name: Add the platform wheels that full verification built and ran")
    assert added < build.index(check) < build.index("- name: Upload distributions")
    assert "if:" not in build and "continue-on-error" not in build


def _wheel(directory: Path, tag: str, *members: str, digest: str = "") -> Path:
    """A wheel with the members; a `.sha256` member holds the digest of the other members."""
    wheel = directory / f"archkeel-5.0.0-{tag}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for member in ("archkeel/__init__.py", *members):
            recorded = digest or hashlib.sha256(b"x").hexdigest()
            archive.writestr(member, recorded if member.endswith(".sha256") else "x")
    return wheel


def test_a_wheel_carries_the_core_only_with_the_binary_and_its_digest(tmp_path: Path) -> None:
    core = release_core.MEMBER
    assert core == "archkeel/_native/archkeel-core"
    assert not release_core.carries_core(_wheel(tmp_path, "a", "archkeel/_native/collector"))
    assert not release_core.carries_core(_wheel(tmp_path, "b", core))
    assert not release_core.carries_core(_wheel(tmp_path, "c", core + ".sha256"))
    assert not release_core.carries_core(_wheel(tmp_path, "d", core, core + ".exe.sha256"))
    assert release_core.carries_core(_wheel(tmp_path, "e", core, core + ".sha256"))
    assert release_core.carries_core(_wheel(tmp_path, "f", core + ".exe", core + ".exe.sha256"))
    # A digest of other bytes makes the shell refuse the binary, so the wheel carries no core.
    other = hashlib.sha256(b"other").hexdigest()
    assert not release_core.carries_core(
        _wheel(tmp_path, "g", core, core + ".sha256", digest=other)
    )
    assert not release_core.carries_core(_wheel(tmp_path, "h", core, core + ".sha256", digest="x"))
    (tmp_path / "no-archive.whl").write_bytes(b"wheel")
    assert not release_core.carries_core(tmp_path / "no-archive.whl")


def test_the_release_check_refuses_each_wheel_without_the_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    core = release_core.MEMBER
    monkeypatch.setattr(release_core, "platform_tags", lambda: ("py3-none-host",))
    assert release_core.main([str(tmp_path), "x.whl"]) == 2
    host = _wheel(tmp_path, "py3-none-host", core, core + ".sha256")
    bare = _wheel(tmp_path, "py3-none-other")
    ran: list[Path] = []
    monkeypatch.setattr(release_core, "smoke", lambda wheel: ran.append(wheel) or "")
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert f"release refused: {bare.name} does not carry {core}" in capsys.readouterr().err
    # No installed run stands in for a wheel without the core.
    assert ran == []
    bare.unlink()
    assert release_core.main([str(tmp_path), str(tmp_path / "absent.whl")]) == 2 and ran == []
    assert release_core.main([str(tmp_path), str(host)]) == 0 and ran == [host]
    monkeypatch.setattr(release_core, "smoke", lambda wheel: "refusal core_binary_not_found")
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "gives no verdict of its core: refusal core_binary_not_found" in capsys.readouterr().err
    assert release_core.main([str(tmp_path)]) == 2


def test_the_release_check_wants_exactly_the_platforms_of_the_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-476: a missing or an unlisted platform stops the release; each listed one passes."""
    core = release_core.MEMBER
    host = _wheel(tmp_path, "py3-none-host", core, core + ".sha256")
    windows = _wheel(tmp_path, "py3-none-win_amd64", core + ".exe", core + ".exe.sha256")
    ran: list[Path] = []
    monkeypatch.setattr(release_core, "smoke", lambda wheel: ran.append(wheel) or "")
    monkeypatch.setattr(
        release_core, "platform_tags", lambda: ("py3-none-host", "py3-none-win_amd64")
    )
    assert release_core.main([str(tmp_path), str(host)]) == 0 and ran == [host]
    windows.unlink()
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "are not exactly the platforms" in capsys.readouterr().err
    windows = _wheel(tmp_path, "py3-none-win_amd64", core + ".exe", core + ".exe.sha256")
    monkeypatch.setattr(release_core, "platform_tags", lambda: ("py3-none-host",))
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "are not exactly the platforms" in capsys.readouterr().err


def test_only_a_verdict_of_the_bundled_core_passes_the_installed_run() -> None:
    frame = {"engine": "archkeel-core 0a", "rules": {"R": ["root_layout", "PASS"]}}
    core = {"path": "/venv/site-packages/archkeel/_native/archkeel-core"}
    good = {"status": "UNKNOWN", "exit_code": 2, "frame": frame, "core": core}
    assert release_core.undecided(good, 2) == ""
    refusal = {"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_binary_not_found"}}
    assert release_core.undecided(refusal, 2) == "refusal core_binary_not_found"
    assert release_core.undecided([], 2) == "no result object: []"
    assert "no frame" in release_core.undecided({**good, "frame": {**frame, "engine": "x"}}, 2)
    checkout = {"path": "/checkout/native/target/release/archkeel-core"}
    assert "not the binary of the package" in release_core.undecided({**good, "core": checkout}, 2)
    unknown = {**frame, "rules": {"R": ["root_layout", "UNKNOWN"]}}
    assert "no rule has PASS" in release_core.undecided({**good, "frame": unknown}, 2)
    assert "exit code 0 differs" in release_core.undecided(good, 0)


def _make(tmp_path: Path, target: str, cargo_deny: str) -> subprocess.CompletedProcess[str]:
    # The stub of cargo builds nothing, and UV=true runs no Python: the test reads only the calls.
    cargo = tmp_path / "cargo"
    cargo.write_text(f'#!/bin/sh\necho "cargo $*" >> "{tmp_path}/calls"\necho "{cargo_deny}"\n')
    cargo.chmod(0o755)
    return subprocess.run(
        ["make", target, "UV=true"],
        cwd=ROOT,
        env={**_MAKE_ENV, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_native_check_runs_the_dependency_policy_with_the_pinned_cargo_deny(
    tmp_path: Path,
) -> None:
    wrong = _make(tmp_path, "native-check", "cargo-deny 0.19.0")
    assert wrong.returncode == 2
    assert "native-check needs cargo-deny 0.20.2: run make native-tools" in wrong.stdout
    assert (tmp_path / "calls").read_text() == "cargo deny --version\n"
    pinned = _make(tmp_path, "native-check", "cargo-deny 0.20.2")
    assert pinned.returncode == 0, pinned.stderr
    calls = (tmp_path / "calls").read_text().splitlines()
    assert "cargo deny --locked check" in calls
    assert calls.index("cargo clippy --locked --all-targets -- -D warnings") < calls.index(
        "cargo deny --locked check"
    )
    # AD-432: the self-check of native-check runs the release core of this checkout.
    assert calls[-1] == "cargo build --locked --release -p archkeel-core"


def test_the_ci_install_of_cargo_deny_checks_the_hash_and_creates_the_target_directory() -> None:
    dry_run = subprocess.run(
        ["make", "--no-print-directory", "-n", "cargo-deny-install"],
        cwd=ROOT,
        env=_MAKE_ENV,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "sha256sum --check --strict" in dry_run
    # A fresh runner can lack ~/.cargo/bin; install does not create the directory itself.
    assert 'mkdir -p "${CARGO_HOME:-$HOME/.cargo}/bin"' in dry_run


def test_a_test_that_needs_a_rust_toolchain_runs_only_in_the_wheel_matrix() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert (
        """addopts = "-rs -p no:cacheprovider -m 'not browser and not native_wheel'\""""
        in pyproject
    )
    dry_run = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-n",
            "native-wheel",
            "NATIVE_TAG=py3-none-win_amd64",
            "UV=uv",
        ],
        cwd=ROOT,
        env=_MAKE_ENV,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "cargo install --locked cargo-auditable@0.7.7" in dry_run
    assert "ARCHKEEL_BUNDLE_NATIVE=1 uv build --wheel --no-sources --out-dir dist/native" in dry_run
    assert "-m native_wheel tests/test_collector_native_wheel.py" in dry_run
    # AD-436: the same wheel, installed alone, gives the verdicts of its core.
    assert dry_run.count('ARCHKEEL_NATIVE_WHEEL="$(ls dist/native/*.whl)" uv run --locked') == 2
    assert dry_run.rstrip().endswith("tests/test_cli_installed_wheel.py")


def test_native_check_runs_the_clone_and_api_tools_only_through_their_tests() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    check = makefile.split("\nnative-check:\n")[1].split("\n# AD-432")[0]
    assert "tests/test_rust_clones.py tests/test_rust_api.py" in check
    assert "tools/rust_clones.py\n" not in check and "tools/rust_api.py --check" not in check
    assert "cargo build --locked\n" not in check
