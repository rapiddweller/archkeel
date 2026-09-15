# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.cli import main

ROOT = Path(__file__).parents[1]


def test_check_requires_explicit_inputs(capsys: pytest.CaptureFixture) -> None:
    assert main(["check"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == "command-line arguments"
    )


def test_report_has_no_external_analyzer_option() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--analyzer-root" not in result.stdout


def test_skill_install_writes_the_packaged_instructions(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["skill", "install", "claude", "--root", str(tmp_path), "--json"]) == 0
    path = Path(json.loads(capsys.readouterr().out)["path"])
    assert path == tmp_path / ".claude/skills/archkeel/SKILL.md"
    assert "archkeel validate --json" in path.read_text()


@pytest.mark.parametrize("command", ["init", "report", "validate", "check", "skill"])
def test_every_command_help_explains_purpose_and_exit_codes(command: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", command, "--help"],
        capture_output=True,
        text=True,
        env={"NO_COLOR": "1", "COLUMNS": "100", "PATH": ""},
    )
    assert result.returncode == 0
    assert "Exit codes:" in result.stdout
    assert "Example" in result.stdout


def test_no_arguments_prints_the_command_overview(capsys: pytest.CaptureFixture) -> None:
    assert main([]) == 0
    overview = capsys.readouterr().out
    assert all(name in overview for name in ("report", "validate", "check", "--version"))


def test_interactive_terminal_gets_a_summary_and_json_stays_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert main(["validate", "--root", str(ROOT)]) == 0
    summary = capsys.readouterr().out
    assert "Independent verdicts" in summary and not summary.startswith("{")
    assert main(["validate", "--root", str(ROOT), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_report_missing_config_is_unknown(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["report", "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "UNKNOWN"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "UNKNOWN"


def test_validate_self_and_json_are_identical(capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "--root", str(ROOT)]) == 0
    default = capsys.readouterr().out
    assert main(["validate", "--root", str(ROOT), "--json"]) == 0
    explicit = capsys.readouterr().out
    assert explicit == default
    result = json.loads(explicit)
    assert result["observation_complete"] == result["declared_rules"] == "PASS"


def test_validate_configuration_error_has_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["validate", "--root", str(tmp_path), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "contract_invalid"
    assert diagnostic["pointer"] == ""
