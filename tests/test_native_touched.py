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


def test_a_change_in_a_crate_names_that_crate_and_a_data_file_checks_only_the_format() -> None:
    assert selection(["native/core/src/main.rs"], CRATES) == "-p archkeel-core"
    paths = ["native/python/src/a.rs", "native/report/src/b.rs", "native/core/src/c.rs"]
    assert (
        selection(paths, CRATES)
        == "-p archkeel-core -p archkeel-python-collector -p archkeel-report"
    )
    assert selection(["native/api_baseline.json"], CRATES) == "-"


def test_a_workspace_file_checks_the_whole_workspace() -> None:
    for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "clippy.toml"):
        assert selection([f"native/{name}", "native/core/src/a.rs"], CRATES) == "--workspace"


def test_crate_dirs_maps_a_manifest_directory_to_its_package() -> None:
    metadata = {
        "workspace_root": "/r/native",
        "packages": [{"name": "archkeel-core", "manifest_path": "/r/native/core/Cargo.toml"}],
    }
    assert crate_dirs(metadata) == {"native/core/": "archkeel-core"}


GATES = (
    "run --locked python -m pytest -q -p no:cacheprovider -n 0 "
    "tests/test_rust_clones.py tests/test_rust_api.py"
)
AREA_JOB = "run --locked python tools/select_areas.py --job self-check and CI"


def _make(
    tmp_path: Path, selected: str, fmt_fails: bool = False, hosted: str | None = None
) -> tuple[int, list[str], list[str]]:
    """Run the Make recipe with a `uv` that prints `selected` and a `cargo` that logs its calls.

    The result is the exit code, the calls of `cargo` and the calls of `uv`. `hosted` is the answer
    of `select_areas.py --job` and turns `PR_HOSTED=1` on.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp_path / "native").mkdir(exist_ok=True)
    log = tmp_path / "cargo.log"
    log.write_text("")
    uv = bin_dir / "uv"
    uv_log = tmp_path / "uv.log"
    uv_log.write_text("")
    answer = f"case \"$*\" in *select_areas.py*) echo '{hosted}';; *) echo '{selected}';; esac\n"
    uv.write_text(f'#!/bin/sh\necho "$@" >> "{uv_log}"\n{answer}')
    cargo = bin_dir / "cargo"
    cargo.write_text(
        f'#!/bin/sh\necho "$@" >> "{log}"\n'
        + ('case "$1" in fmt) exit 1;; esac\n' if fmt_fails else "")
    )
    # AD-1047: the recipe also formats the driver, which the fake tree does not hold.
    rustfmt = bin_dir / "rustfmt"
    rustfmt.write_text("#!/bin/sh\nexit 0\n")
    for script in (uv, cargo, rustfmt):
        script.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MAKEFLAGS": ""}
    flags = [] if hosted is None else ["PR_HOSTED=1"]
    done = subprocess.run(
        ["make", "-s", "-f", str(ROOT / "Makefile"), "pr-native-lint", f"UV={uv}", *flags],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, log.read_text().splitlines(), uv_log.read_text().splitlines()


def test_the_recipe_runs_nothing_when_native_is_unchanged(tmp_path: Path) -> None:
    code, calls, uv_calls = _make(tmp_path, "")
    assert (code, calls) == (0, []) and GATES not in uv_calls


def test_the_recipe_checks_the_format_and_lints_the_touched_crates(tmp_path: Path) -> None:
    code, calls, _ = _make(tmp_path, "-p archkeel-core -p archkeel-report")
    assert code == 0
    assert calls == [
        "fmt --all -- --check",
        "clippy --locked --all-targets -p archkeel-core -p archkeel-report -- -D warnings",
    ]


def test_a_pin_only_change_checks_the_format_alone_and_then_the_gates(tmp_path: Path) -> None:
    code, calls, uv_calls = _make(tmp_path, "-")
    assert (code, calls) == (0, ["fmt --all -- --check"]) and uv_calls[-1] == GATES


def test_an_unformatted_file_fails_the_gate_before_clippy_and_the_gates_run(
    tmp_path: Path,
) -> None:
    code, calls, uv_calls = _make(tmp_path, "-p archkeel-core", fmt_fails=True)
    assert code != 0 and calls == ["fmt --all -- --check"] and GATES not in uv_calls


def test_the_pr_gate_workflow_runs_the_native_lint_after_the_core_build() -> None:
    text = (ROOT / ".github/workflows/pr-gate.yml").read_text()
    assert "make pr-native-lint PR_BASE=" in text


def test_a_native_change_also_runs_the_clone_and_the_api_gate_after_fmt_and_clippy(
    tmp_path: Path,
) -> None:
    """A clone or a public name that nobody checked was merged: they run in the PR gate now."""
    code, _calls, uv_calls = _make(tmp_path, "-p archkeel-core")
    assert code == 0
    assert uv_calls[-1] == GATES


def test_the_hosted_gate_leaves_out_what_the_native_job_and_the_area_job_run(
    tmp_path: Path,
) -> None:
    """PR_HOSTED=1: `native-check` runs the fmt, the driver rustfmt and the workspace clippy.

    The area `self-check and CI` runs the clone and API tests. A crate clippy and a skipped
    area stay.
    """
    code, calls, uv_calls = _make(tmp_path, "--workspace", hosted="run")
    assert (code, calls) == (0, []) and GATES not in uv_calls
    assert AREA_JOB in uv_calls[-1]
    code, calls, uv_calls = _make(tmp_path, "-p archkeel-core", hosted="run")
    assert code == 0 and GATES not in uv_calls
    assert calls == ["clippy --locked --all-targets -p archkeel-core -- -D warnings"]
    code, calls, uv_calls = _make(tmp_path, "-", hosted="no matching paths")
    assert (code, calls) == (0, []) and uv_calls[-1] == GATES
