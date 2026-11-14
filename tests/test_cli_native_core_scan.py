# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The release build of the core links each collector without a test-only feature."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

NATIVE = Path(__file__).resolve().parents[1] / "native"


@pytest.mark.parametrize("collector", ["typescript", "rust"])
def test_the_release_build_links_the_collector_without_its_test_feature(collector: str) -> None:
    """#1099 (a): the wheel builds the whole workspace without a feature (`hatch_build.py`). In
    that resolution the core links the TypeScript collector without `dump`, whose planted faults
    read the environment. A build with `dump` gives no accepted reply: `archkeel-collect` refuses
    it by name (`built`, its unit test)."""
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
    assert "archkeel-core" in tree
    assert 'feature "dump"' not in tree
    hook = (NATIVE / "hatch_build.py").read_text()
    assert '"auditable", "build", "--release", "--locked", "--target-dir"' in hook
    assert "--features" not in hook
