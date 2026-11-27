# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard-global catalog follows the compiler's own lib files for each `lib` and target."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TYPESCRIPT_LIB = ROOT / "tools/browser-runtime/node_modules/typescript/lib"


def test_generated_catalog_is_the_one_the_pinned_compiler_produces():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    result = subprocess.run(
        [sys.executable, "-m", "tools.typescript_libs", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
