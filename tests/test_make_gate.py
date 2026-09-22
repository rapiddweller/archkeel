# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The repository Make gate must fail closed when a project check fails."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_gate_does_not_mask_a_failed_project_check(tmp_path: Path) -> None:
    """A failed check stops the gate before a later release step can look successful."""
    marker = tmp_path / "later-step-ran"
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        f"include {ROOT / 'Makefile'}\n\n"
        ".PHONY: lint typecheck test check build smoke\n"
        "lint typecheck test build:\n\t@:\n"
        "check:\n\t@false\n"
        f"smoke:\n\t@touch {marker}\n"
    )
    environment = {**os.environ, "UV": "false"}

    result = subprocess.run(
        ["make", "-f", str(makefile), "gate"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not marker.exists()
