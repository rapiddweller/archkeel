# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The release uses both workers without test features."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

NATIVE = Path(__file__).resolve().parents[1] / "native"


@pytest.mark.parametrize("collector", ["typescript", "rust"])
def test_the_release_uses_the_collector_without_its_test_feature(collector: str) -> None:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("cargo is not installed")
    tree = subprocess.run(
        [cargo, "tree", "--locked", "--workspace", "-e", "features", "-i"]
        + [f"archkeel-{collector}-collector"],
        cwd=NATIVE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "archkeel-core" not in tree
    assert 'feature "dump"' not in tree
    hook = (NATIVE / "hatch_build.py").read_text()
    assert '"auditable", "build", "--release", "--locked", "--target-dir"' in hook
    assert "--features" not in hook
