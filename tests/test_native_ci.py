# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-316 and AD-317: CI checks the native collector, and a release gates its platform wheels."""

from __future__ import annotations

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


@pytest.mark.parametrize("gate,published", [("false", False), ("true", True), ("", False)])
def test_a_release_adds_the_platform_wheels_only_when_the_gate_is_open(
    tmp_path: Path, gate: str, published: bool
) -> None:
    build = _jobs("release.yml")["build"]
    assert "pattern: native-wheel-*\n" in build and "path: native-wheels/\n" in build
    step = build.split("- name: Add the platform wheels only when PUBLISH_NATIVE_WHEELS is true\n")
    script = dedent(step[1].split("        run: |\n", 1)[1].split("\n\n", 1)[0])
    (tmp_path / "dist").mkdir()
    (tmp_path / "native-wheels").mkdir()
    (tmp_path / "dist/archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    (tmp_path / "dist/archkeel-5.0.0-py3-none-any.whl").write_bytes(b"pure")
    for tag in PLATFORM_TAGS:
        (tmp_path / "native-wheels" / f"archkeel-5.0.0-{tag}.whl").write_bytes(b"wheel")
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PUBLISH_NATIVE_WHEELS": gate},
        check=False,
        capture_output=True,
    )
    assert (result.returncode == 0) is published
    assert len(list((tmp_path / "dist").glob("*.whl"))) == (len(PLATFORM_TAGS) if published else 1)
    assert len(list((tmp_path / "dist").glob("*.tar.gz"))) == 1


@pytest.mark.parametrize("wheels,sdists", [(n, 1) for n in range(8)] + [(6, 0), (6, 2)])
def test_release_requires_exactly_six_platform_wheels_and_one_sdist(tmp_path, wheels, sdists):
    build = _jobs("release.yml")["build"]
    step = build.split("- name: Add the platform wheels only when PUBLISH_NATIVE_WHEELS is true\n")
    script = dedent(step[1].split("        run: |\n", 1)[1].split("\n\n", 1)[0])
    (tmp_path / "dist").mkdir()
    (tmp_path / "native-wheels").mkdir()
    (tmp_path / "dist/archkeel-5.0.0-py3-none-any.whl").write_bytes(b"pure")
    for index in range(wheels):
        (tmp_path / "native-wheels" / f"archkeel-5.0.0-py3-none-platform{index}.whl").write_bytes(
            b"wheel"
        )
    for index in range(sdists):
        (tmp_path / "dist" / f"archkeel-5.0.{index}.tar.gz").write_bytes(b"sdist")
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PUBLISH_NATIVE_WHEELS": "true"},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (wheels == 6 and sdists == 1)
    if result.returncode == 0:
        assert len(list((tmp_path / "dist").glob("*.whl"))) == 6
        assert not (tmp_path / "dist/archkeel-5.0.0-py3-none-any.whl").exists()


@pytest.mark.parametrize("gate,opened", [("false", False), ("", False), ("true", True)])
def test_a_release_stops_before_full_verification_while_it_is_closed(
    gate: str, opened: bool
) -> None:
    """AD-432: no wheel carries the core, so the first job of a release refuses the release."""
    workflow = (WORKFLOWS / "release.yml").read_text()
    flag = re.findall(r'^  PUBLISH_NATIVE_WHEELS: "(\w+)"$', workflow, re.MULTILINE)
    # Only a wheel hook that bundles the core can open the release.
    hook = (ROOT / "native/hatch_build.py").read_text()
    assert flag == ["true" if '"archkeel-core"' in hook else "false"]
    jobs = _jobs("release.yml")
    first = jobs["core-in-wheel"]
    assert "    needs: core-in-wheel\n" in jobs["verify"]
    assert "needs:" not in first and "uses:" not in first and "if:" not in first
    assert "    permissions: {}\n" in first
    script = dedent(first.split("        run: |\n", 1)[1])
    result = subprocess.run(
        ["bash", "-c", script],
        env={**os.environ, "PUBLISH_NATIVE_WHEELS": gate},
        capture_output=True,
        text=True,
    )
    assert result.returncode == (0 if opened else 2)
    assert ("no wheel carries archkeel-core" in result.stdout) is not opened


def test_the_release_build_checks_the_core_of_the_wheels_before_it_uploads_them() -> None:
    build = _jobs("release.yml")["build"]
    check = "run: python3 -m tools.release_core dist dist/archkeel-*-py3-none-manylinux_2_17_x86_64"
    added = build.index("- name: Add the platform wheels only when PUBLISH_NATIVE_WHEELS is true")
    assert added < build.index(check) < build.index("- name: Upload distributions")
    assert "if:" not in build and "continue-on-error" not in build


def _wheel(directory: Path, tag: str, *members: str) -> Path:
    wheel = directory / f"archkeel-5.0.0-{tag}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for member in ("archkeel/__init__.py", *members):
            archive.writestr(member, "x")
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
    (tmp_path / "no-archive.whl").write_bytes(b"wheel")
    assert not release_core.carries_core(tmp_path / "no-archive.whl")


def test_the_release_check_refuses_each_wheel_without_the_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    core = release_core.MEMBER
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


def test_native_check_runs_the_clone_and_api_tools_only_through_their_tests() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    check = makefile.split("\nnative-check:\n")[1].split("\n# AD-432")[0]
    assert "tests/test_rust_clones.py tests/test_rust_api.py" in check
    assert "tools/rust_clones.py\n" not in check and "tools/rust_api.py --check" not in check
    assert "cargo build --locked\n" not in check
