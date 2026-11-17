# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-732: the core cache is saved only after its own build and carries a tree stamp."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _jobs(workflow: str) -> dict[str, str]:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


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
        "chmod +x target/release/archkeel-core\n"
    )
    cargo.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MAKEFLAGS": ""}


def _make_core(
    tmp_path: Path, env: dict[str, str], tree: str | None
) -> subprocess.CompletedProcess:
    (tmp_path / "native").mkdir(exist_ok=True)
    env = {k: v for k, v in env.items() if k != "ARCHKEEL_NATIVE_TREE"}
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
    # No tree: always `cargo build`, no stamp promise.
    assert _make_core(tmp_path, env, None).returncode == 0
    assert len(calls.read_text().splitlines()) == 3 and not stamp.exists()
    failing = _fake_cargo(tmp_path, succeed=False)
    assert _make_core(tmp_path, failing, "tree-c").returncode != 0
    assert not stamp.exists()


def test_a_core_is_saved_only_after_its_own_build_step_succeeded() -> None:
    """AD-732: `always()` alone would save the old core that a failed run restored."""
    for workflow, job in (("pr-gate.yml", "pr-gate"), ("ci.yml", "lint")):
        body = _jobs(workflow)[job]
        assert "      - name: Build the core\n        id: build\n" in body, workflow
        save = body.split("      - name: Save the core for this native tree\n", 1)[1]
        condition = re.search(r"^        if: (.+)$", save, re.MULTILINE)
        assert condition is not None and "steps.build.outcome == 'success'" in condition[1]
        assert "archkeel-core.tree" in save.split("key:", 1)[0], workflow
        assert body.index("id: build") < body.index("Save the core for this native tree")
