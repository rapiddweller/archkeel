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
    assert selection(["native/README.md"], CRATES) == "-"


def test_a_workspace_file_checks_the_whole_workspace() -> None:
    for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "clippy.toml"):
        assert selection([f"native/{name}", "native/core/src/a.rs"], CRATES) == "--workspace"


def test_crate_dirs_maps_a_manifest_directory_to_its_package() -> None:
    metadata = {
        "workspace_root": "/r/native",
        "packages": [{"name": "archkeel-core", "manifest_path": "/r/native/core/Cargo.toml"}],
    }
    assert crate_dirs(metadata) == {"native/core/": "archkeel-core"}


def _make(
    tmp_path: Path, selected: str, fmt_fails: bool = False, hosted: bool = False
) -> tuple[int, list[str]]:
    """Run the Make recipe with a `uv` that prints `selected` and a `cargo` that logs its calls.

    The result is the exit code and the calls of `cargo`. `hosted` turns `PR_HOSTED=1` on.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp_path / "native").mkdir(exist_ok=True)
    log = tmp_path / "cargo.log"
    log.write_text("")
    uv = bin_dir / "uv"
    uv.write_text(f"#!/bin/sh\necho '{selected}'\n")
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
    flags = ["PR_HOSTED=1"] if hosted else []
    done = subprocess.run(
        ["make", "-s", "-f", str(ROOT / "Makefile"), "pr-native-lint", f"UV={uv}", *flags],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, log.read_text().splitlines()


def test_the_recipe_runs_nothing_when_native_is_unchanged(tmp_path: Path) -> None:
    code, calls = _make(tmp_path, "")
    assert (code, calls) == (0, [])
