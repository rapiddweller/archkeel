# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The repository Make gate must fail closed when a project check fails."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("check_exit", "expected_exit", "expected_steps"),
    [(1, 2, ["check"]), (0, 0, ["check", "build", "smoke", "self-validate"])],
)
def test_gate_does_not_mask_a_failed_project_check(
    tmp_path: Path, check_exit: int, expected_exit: int, expected_steps: list[str]
) -> None:
    """A failed check stops release steps; a successful check reaches them in order."""
    steps = tmp_path / "steps"
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        f"include {ROOT / 'Makefile'}\n\n"
        ".PHONY: lint typecheck test typescript-adapter check build smoke self-validate\n"
        "lint typecheck test typescript-adapter:\n\t@:\n"
        f'check:\n\t@echo check >> "{steps.as_posix()}"\n\t@exit {check_exit}\n'
        f'build:\n\t@echo build >> "{steps.as_posix()}"\n'
        f'smoke:\n\t@echo smoke >> "{steps.as_posix()}"\n'
        f'self-validate:\n\t@echo self-validate >> "{steps.as_posix()}"\n'
    )
    environment = {**os.environ, "UV": "false", "NPM": "false"}

    result = subprocess.run(
        ["make", "-f", str(makefile), "gate"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert steps.exists(), result.stderr
    assert steps.read_text().splitlines() == expected_steps
    assert result.returncode == expected_exit, result.stderr


def test_against_uses_pinned_base_and_stops_before_gate(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    runner = tmp_path / "uv"
    runner.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{steps}"\nexit 1\n')
    runner.chmod(0o755)
    result = subprocess.run(
        ["sh", "-c", "make against && make gate"],
        cwd=ROOT,
        env={**os.environ, "UV": str(runner), "BASE": "a" * 40},
        capture_output=True,
    )
    assert result.returncode != 0
    assert steps.read_text().splitlines() == [
        f"run --locked python -m tools.against --base {'a' * 40}"
    ]
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "BASE: ${{ github.event.pull_request.base.sha }}" in workflow
    assert workflow.index("run: make against") < workflow.index("run: make gate")
