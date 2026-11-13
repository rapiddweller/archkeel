# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-60: `report --only`, `--rule` and `--component` narrow what is shown, never what is judged."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.cli import main
from fixtures.architecture_demo import CATALOG

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)


def _tour_root(tmp_path: Path) -> Path:
    """AD-51's own demo: 28 rule ids, 29 violations, crossing several component pairs."""
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    return _prepare_repo(tmp_path, dict(tour.files))


def test_cli_report_only_rejects_an_unsupported_value(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _tour_root(tmp_path)

    assert main(["report", "--root", str(root), "--only", "everything", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)

    assert result["diagnostics"][0]["subject"] == "command-line arguments"


def test_cli_report_help_documents_the_filters() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--only" in result.stdout
    assert "--rule" in result.stdout
    assert "--component" in result.stdout
