# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-756: the PR gate checks the Rust format and lints the touched crates when native/ changes."""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_touched import crate_dirs, selection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CRATES = {
    "native/core/": "archkeel-core",
    "native/python/": "archkeel-python-collector",
    "native/report/": "archkeel-report",
}


def test_a_change_outside_native_checks_no_rust() -> None:
    assert selection(["src/archkeel/cli/core_text.py", "docs/a.md"], CRATES) == ""


def test_a_change_in_a_crate_names_that_crate_and_a_pin_checks_only_the_format() -> None:
    assert selection(["native/core/src/main.rs"], CRATES) == "-p archkeel-core"
    paths = ["native/python/src/a.rs", "native/report/src/b.rs", "native/core/src/c.rs"]
    assert (
        selection(paths, CRATES)
        == "-p archkeel-core -p archkeel-python-collector -p archkeel-report"
    )
    assert selection(["native/expected-gaps.json"], CRATES) == "-"


def test_a_workspace_file_checks_the_whole_workspace() -> None:
    for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "clippy.toml"):
        assert selection([f"native/{name}", "native/core/src/a.rs"], CRATES) == "--workspace"


def test_crate_dirs_maps_a_manifest_directory_to_its_package() -> None:
    metadata = {
        "workspace_root": "/r/native",
        "packages": [{"name": "archkeel-core", "manifest_path": "/r/native/core/Cargo.toml"}],
    }
    assert crate_dirs(metadata) == {"native/core/": "archkeel-core"}


def _make(tmp_path: Path, selected: str, fmt_fails: bool = False) -> tuple[int, list[str]]:
    """Run the Make recipe with a `uv` that prints `selected` and a `cargo` that logs its calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp_path / "native").mkdir(exist_ok=True)
    log = tmp_path / "cargo.log"
    log.write_text("")
    uv = bin_dir / "uv"
    uv_log = tmp_path / "uv.log"
    uv_log.write_text("")
    uv.write_text(f'#!/bin/sh\necho "$@" >> "{uv_log}"\necho \'{selected}\'\n')
    cargo = bin_dir / "cargo"
    cargo.write_text(
        f'#!/bin/sh\necho "$@" >> "{log}"\n'
        + ('case "$1" in fmt) exit 1;; esac\n' if fmt_fails else "")
    )
    for script in (uv, cargo):
        script.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MAKEFLAGS": ""}
    done = subprocess.run(
        ["make", "-s", "-f", str(ROOT / "Makefile"), "pr-native-lint", f"UV={uv}"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, log.read_text().splitlines()


def _uv_calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "uv.log").read_text().splitlines()


def test_the_recipe_runs_nothing_when_native_is_unchanged(tmp_path: Path) -> None:
    assert _make(tmp_path, "") == (0, [])


def test_the_recipe_checks_the_format_and_lints_the_touched_crates(tmp_path: Path) -> None:
    code, calls = _make(tmp_path, "-p archkeel-core -p archkeel-report")
    assert code == 0
    assert calls == [
        "fmt --all -- --check",
        "clippy --locked --all-targets -p archkeel-core -p archkeel-report -- -D warnings",
    ]


def test_a_pin_only_change_checks_the_format_alone(tmp_path: Path) -> None:
    assert _make(tmp_path, "-") == (0, ["fmt --all -- --check"])


def test_an_unformatted_file_fails_the_gate_before_clippy_runs(tmp_path: Path) -> None:
    code, calls = _make(tmp_path, "-p archkeel-core", fmt_fails=True)
    assert code != 0 and calls == ["fmt --all -- --check"]


def test_the_pr_gate_workflow_runs_the_native_lint_after_the_core_build() -> None:
    text = (ROOT / ".github/workflows/pr-gate.yml").read_text()
    assert text.index("name: Build the core") < text.index("make pr-native-lint")
    assert "make pr-native-lint PR_BASE=" in text


GATES = (
    "run --locked python -m pytest -q -p no:cacheprovider -n 0 "
    "tests/test_rust_clones.py tests/test_rust_api.py"
)


def test_a_native_change_also_runs_the_clone_and_the_api_gate_after_fmt_and_clippy(
    tmp_path: Path,
) -> None:
    """A clone or a public name that nobody checked was merged: they run in the PR gate now."""
    code, _calls = _make(tmp_path, "-p archkeel-core")
    assert code == 0
    assert _uv_calls(tmp_path)[-1] == GATES
    code, _calls = _make(tmp_path, "-")
    assert code == 0 and _uv_calls(tmp_path)[-1] == GATES


def test_the_gates_do_not_run_without_a_native_change_or_after_an_unformatted_file(
    tmp_path: Path,
) -> None:
    assert _make(tmp_path, "")[0] == 0 and GATES not in _uv_calls(tmp_path)
    code, _calls = _make(tmp_path, "-p archkeel-core", fmt_fails=True)
    assert code != 0 and GATES not in _uv_calls(tmp_path)
