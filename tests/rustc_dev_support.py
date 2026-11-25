# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1047: a test that needs the compiler type-reach facts needs the components of the driver.

The native self-check holds many more gaps without the facts, so a test of its exact result cannot
pass on a machine without `rustc-dev` and `llvm-tools`. Locally such a test skips. The reason
names `rustc`, so the oracle guard (`oracle_support.py`) turns the skip into a failure in CI.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

DRIVER_TOOLCHAIN = Path(__file__).parents[1] / "tools/rustc-facts/rust-toolchain.toml"


def has_driver_components() -> bool:
    """True when the pinned channel has each component that the driver toolchain file names."""
    pinned = tomllib.loads(DRIVER_TOOLCHAIN.read_text())["toolchain"]
    try:
        listed = subprocess.run(
            ["rustup", "component", "list", "--installed", "--toolchain", pinned["channel"]],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    lines = listed.splitlines()
    return all(any(line.startswith(f"{name}-") for line in lines) for name in pinned["components"])


needs_rustc_dev = pytest.mark.skipif(
    not has_driver_components(),
    reason="rustc-dev and llvm-tools are missing: make type-reach-setup",
)
