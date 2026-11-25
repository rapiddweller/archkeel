# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432, AD-478, AD-492: a self-check target fails without a usable result of the core."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from timeout_support import run_bounded

ROOT = Path(__file__).parents[1]

REFUSED = '{"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_error", "message": "x"}}'


@pytest.mark.parametrize(
    ("target", "printed", "shown"),
    [
        ("self-validate-native", REFUSED, "the PR result is a refusal: core_error: x"),
        ("self-validate-native", "", "the self-check result is unusable"),
        ("self-validate-shell", REFUSED, "the PR result is a refusal: core_error: x"),
        ("self-validate-shell", "", "is empty or corrupt"),
    ],
)
def test_a_self_check_without_a_usable_core_result_fails(
    tmp_path: Path, target: str, printed: str, shown: str
) -> None:
    """AD-432: a refusal or no result of `archkeel validate` never passes a self-check gate."""
    uv = tmp_path / "uv"
    uv.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f"  *archkeel\\ validate*) printf '%s' '{printed}'; exit 2;;\n"
        f'  *) shift 3; exec "{sys.executable}" "$@";;\n'
        "esac\n"
    )
    uv.chmod(0o755)
    for name in (
        "tools/self_check_gate.py",
        "tools/self_check_diff.py",
        "tools/self_check_shell.py",
        "docs/architecture/target/shell-contract.json",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    (tmp_path / "native").mkdir()
    (tmp_path / "native/lib.rs").write_text("// one\n")
    env = {
        **os.environ,
        "MAKEFLAGS": "",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for git in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", *git], cwd=tmp_path, env=env, check=True, capture_output=True)
    result = run_bounded(
        ["make", "-f", str(ROOT / "Makefile"), "-o", "core", "-o", "browser-runtime-install"]
        + [target, f"UV={uv}"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert shown in result.stdout + result.stderr
    assert "as pinned in" not in result.stdout and "GREEN" not in result.stdout
