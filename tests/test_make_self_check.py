# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432, AD-474: a self-check target fails without the pinned result of the core."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

REFUSED = '{"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_error", "message": "x"}}'


@pytest.mark.parametrize(
    ("target", "printed", "shown"),
    [
        ("self-validate-native", REFUSED, "refused: core_error: x"),
        ("self-validate-native", "", "JSONDecodeError"),
        ("self-validate-shell", REFUSED, "refused: core_error: x"),
        ("self-validate-shell", "", "JSONDecodeError"),
        ("browser-architecture-check", REFUSED, "core_error"),
    ],
)
def test_a_self_check_without_the_pinned_core_result_fails(
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
        "native/expected-gaps.json",
        "docs/architecture/target/shell-expected.json",
        "docs/architecture/target/studio-ui-expected.json",
        "tools/native_expected.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "-o", "core", "-o", "browser-runtime-install"]
        + [target, f"UV={uv}"],
        cwd=tmp_path,
        env={**os.environ, "MAKEFLAGS": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert shown in result.stdout + result.stderr
    assert "as pinned in" not in result.stdout
