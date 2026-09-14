# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from pathlib import Path

import pytest

from codekeel.cli import main


@pytest.mark.parametrize("entry", ["installed", "module"])
def test_accept_remains_unknown_at_both_entrypoints(entry: str) -> None:
    command = (
        [str(Path(sys.executable).with_name("codekeel"))]
        if entry == "installed"
        else [sys.executable, "-m", "codekeel.cli"]
    )
    result = subprocess.run(
        [*command, "accept"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["diagnostics"]
    assert json.loads(result.stdout)["expectation_fulfilled"] == "UNKNOWN"


def test_check_requires_explicit_inputs(capsys: pytest.CaptureFixture) -> None:
    assert main(["check"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == "command-line arguments"
    )


def test_report_has_no_external_producer_option() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codekeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--producer-root" not in result.stdout


def test_report_missing_config_is_unknown(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["report", "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "UNKNOWN"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "UNKNOWN"
