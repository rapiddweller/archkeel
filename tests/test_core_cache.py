# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-732: the core cache is saved only after its own build and carries a tree stamp."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _fake_cargo(tmp_path: Path, succeed: bool = True) -> dict[str, str]:
    """A `cargo` that writes the release core and logs each call; the PATH that finds it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    cargo = bin_dir / "cargo"
    cargo.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{tmp_path}/cargo.log"\n'
        f"{'' if succeed else 'exit 1'}\n"
        "mkdir -p target/release\n"
        "echo built > target/release/archkeel-core\n"
        "echo built > target/release/archkeel-rust-collector\n"
        "echo built > target/release/archkeel-typescript-collector\n"
        "chmod +x target/release/archkeel-*\n"
    )
    cargo.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MAKEFLAGS": ""}


def _make_core(
    tmp_path: Path, env: dict[str, str], tree: str | None, source: str = "cache"
) -> subprocess.CompletedProcess:
    (tmp_path / "native").mkdir(exist_ok=True)
    env = {
        k: v for k, v in env.items() if k not in ("ARCHKEEL_NATIVE_TREE", "ARCHKEEL_CORE_SOURCE")
    }
    env["ARCHKEEL_CORE_SOURCE"] = source
    if tree is not None:
        env["ARCHKEEL_NATIVE_TREE"] = tree
    return subprocess.run(
        ["make", "-s", "-f", str(ROOT / "Makefile"), "core"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_make_core_reuses_a_core_only_with_the_stamp_of_its_tree(tmp_path: Path) -> None:
    """AD-732: a binary of another tree is rebuilt; a failed build leaves no stamp."""
    env = _fake_cargo(tmp_path)
    calls = tmp_path / "cargo.log"
    stamp = tmp_path / "native/target/release/archkeel-core.tree"
    assert _make_core(tmp_path, env, "tree-a").returncode == 0
    assert stamp.read_text().strip() == "tree-a" and len(calls.read_text().splitlines()) == 1
    done = _make_core(tmp_path, env, "tree-a")
    assert "is used" in done.stdout and len(calls.read_text().splitlines()) == 1
    assert _make_core(tmp_path, env, "tree-b").returncode == 0
    assert stamp.read_text().strip() == "tree-b" and len(calls.read_text().splitlines()) == 2
    # AD-736: a core that did not come from the cache is never reused, even with a matching stamp.
    before = len(calls.read_text().splitlines())
    assert _make_core(tmp_path, env, "tree-b", source="build").returncode == 0
    assert len(calls.read_text().splitlines()) == before + 1
    assert _make_core(tmp_path, env, "tree-b").returncode == 0
    assert len(calls.read_text().splitlines()) == before + 1
    # No tree: always `cargo build`, no stamp promise.
    assert _make_core(tmp_path, env, None).returncode == 0
    assert len(calls.read_text().splitlines()) == before + 2 and not stamp.exists()
    failing = _fake_cargo(tmp_path, succeed=False)
    assert _make_core(tmp_path, failing, "tree-c").returncode != 0
    assert not stamp.exists()
