# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432, AD-478, AD-492, AD-1380: the self-check fails without a usable result of the core."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from timeout_support import run_bounded

ROOT = Path(__file__).parents[1]

REFUSED = '{"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_error", "message": "x"}}'


def test_the_self_check_requests_timings_only_when_given_a_path(tmp_path: Path) -> None:
    timings = tmp_path / "phase timings.json"
    for value in ("", str(timings)):
        result = subprocess.run(
            [
                "make",
                "-n",
                "-o",
                "core",
                "self-validate-system",
                f"NATIVE_SELFCHECK_TIMINGS={value}",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert ("--timings" in result.stdout) == bool(value)
        if value:
            assert f'--timings "{timings}"' in result.stdout


@pytest.mark.parametrize(
    ("written", "shown"),
    [
        (REFUSED, "the result is a refusal: core_error: x"),
        ("", "is empty or corrupt"),
        (None, "is missing or unreadable"),
    ],
)
def test_a_self_check_without_a_usable_core_result_fails(
    tmp_path: Path, written: str | None, shown: str
) -> None:
    """AD-432: a refusal or no result of the system run never passes the self-check gate."""
    uv = tmp_path / "uv"
    write = "" if written is None else f"printf '%s' '{written}' > \"$out\"; "
    uv.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '  *archkeel\\ report*) for a in "$@"; do '
        '[ "$prev" = --output ] && out=$a; prev=$a; done; '
        f"{write}exit 2;;\n"
        f'  *) shift 3; exec "{sys.executable}" "$@";;\n'
        "esac\n"
    )
    uv.chmod(0o755)
    name = "tools/self_check_gate.py"
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
        + ["self-validate-system", f"UV={uv}"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert shown in result.stdout + result.stderr
    assert "as pinned in" not in result.stdout and "GREEN" not in result.stdout
