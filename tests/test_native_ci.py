# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-316 and AD-317: CI checks the native collector, and a release gates its platform wheels."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

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
    assert rust == ["native", "native-corpus"]
    assert "runs-on: ubuntu-24.04\n" in jobs["native-corpus"]


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


def _corpus_tests() -> list[str]:
    printed = _dry_run("-p", "native-corpus", "LEG=1")
    found = re.search(r"^NATIVE_CORPUS_TESTS := (.+)$", printed, re.MULTILINE)
    assert found is not None
    return found[1].split()


def test_ci_runs_each_native_check_test_once_in_the_native_job_or_a_corpus_leg() -> None:
    """Issue #880: the corpus tests run in parallel legs; the jobs run all of native-check."""
    jobs = _jobs("ci.yml")
    corpus = _corpus_tests()
    assert len(corpus) == 2
    assert "run: make native-check NATIVE_SPLIT=1\n" in jobs["native"]
    legs = re.search(r"\n        leg: \[(.+)\]\n", jobs["native-corpus"])
    assert legs is not None
    assert legs[1].split(", ") == [str(n) for n in range(1, len(corpus) + 1)]
    assert "run: make native-corpus LEG=${{ matrix.leg }}\n" in jobs["native-corpus"]
    for leg, test in enumerate(corpus, start=1):
        assert _dry_run("native-corpus", f"LEG={leg}").split()[-1] == test
        # A corpus test must come from the test list of native-check, so that the split drops it.
        assert test.split("::")[0] in _dry_run("native-check").split()
    printed = _dry_run("-p", "native-check", "NATIVE_SPLIT=1")
    options = re.findall(r"^PYTEST_ADDOPTS = (.+)$", printed, re.MULTILINE)
    assert options == [f"-n 4 --max-worker-restart=0 --deselect {' --deselect '.join(corpus)}"]


def test_each_corpus_test_names_one_collected_test() -> None:
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *_corpus_tests()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert re.search(r"^2 tests collected", collected.stdout, re.MULTILINE), collected.stdout


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
    workflow = (WORKFLOWS / "release.yml").read_text()
    # PR 4.4 of issue #880 opens the gate in a reviewed change.
    assert '\n  PUBLISH_NATIVE_WHEELS: "false"\n' in workflow
    build = _jobs("release.yml")["build"]
    assert "pattern: native-wheel-*\n" in build and "path: native-wheels/\n" in build
    step = build.split("- name: Add the platform wheels only when PUBLISH_NATIVE_WHEELS is true\n")
    script = dedent(step[1].split("        run: |\n", 1)[1].split("\n\n", 1)[0])
    (tmp_path / "dist").mkdir()
    (tmp_path / "native-wheels").mkdir()
    for tag in PLATFORM_TAGS:
        (tmp_path / "native-wheels" / f"archkeel-5.0.0-{tag}.whl").write_bytes(b"wheel")
    subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PUBLISH_NATIVE_WHEELS": gate},
        check=True,
        capture_output=True,
    )
    assert len(list((tmp_path / "dist").iterdir())) == (len(PLATFORM_TAGS) if published else 0)


def _make(tmp_path: Path, target: str, cargo_deny: str) -> subprocess.CompletedProcess[str]:
    # `self-validate-native` copies the collector that `cargo build` makes, so the stub makes an
    # empty one. A real build output stays as it is, and the test removes only its own file.
    built = ROOT / "native/target/self/debug/archkeel-rust-collector"
    cargo = tmp_path / "cargo"
    cargo.write_text(
        f'#!/bin/sh\necho "cargo $*" >> "{tmp_path}/calls"\necho "{cargo_deny}"\n'
        f'case "$*" in *"build "*) [ -e "{built}" ] || '
        f'{{ mkdir -p "{built.parent}" && : > "{built}"; }};; esac\n'
    )
    cargo.chmod(0o755)
    existed = built.exists()
    try:
        return subprocess.run(
            ["make", target, "UV=true"],
            cwd=ROOT,
            env={**_MAKE_ENV, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
            capture_output=True,
            text=True,
            timeout=15,
        )
    finally:
        if not existed:
            built.unlink(missing_ok=True)


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
    assert """addopts = "-p no:cacheprovider -m 'not browser and not native_wheel'\"""" in pyproject
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
    check = makefile.split("\nnative-check:\n")[1].split("\n# AD-335")[0]
    assert "tests/test_rust_clones.py tests/test_rust_api.py" in check
    assert "tools/rust_clones.py\n" not in check and "tools/rust_api.py --check" not in check
    assert "cargo build --locked\n" not in check
