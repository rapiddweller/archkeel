# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import FrozenInstanceError

import pytest

from archkeel.ir.model import Diagnostic, ObservationResult, RecordData, RunResult


def test_missing_observation_requires_diagnostic() -> None:
    with pytest.raises(ValueError, match="requires a diagnostic"):
        ObservationResult(None, None, ())
    diagnostic = Diagnostic("missing_tool", "producer", "scan completeness", "Install producer.")
    result = ObservationResult(None, None, (diagnostic,))
    assert result.exit_code == 2
    assert result.diagnostics == (diagnostic,)
    with pytest.raises(FrozenInstanceError):
        diagnostic.subject = "changed"


def test_diagnostic_has_actionable_single_line_remedy() -> None:
    with pytest.raises(ValueError, match="one line"):
        Diagnostic("parse_error", "file.py", "AST coverage", "Fix syntax.\nRetry.")
    with pytest.raises(ValueError, match="must not be empty"):
        Diagnostic("parse_error", "", "AST coverage", "Fix syntax.")


def test_record_data_cannot_have_ambiguous_keys() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        RecordData((("key", 1), ("key", 2)))


@pytest.mark.parametrize("command", ["report", "check", "accept"])
def test_exit_two_cannot_exist_without_diagnostic(command: str) -> None:
    with pytest.raises(ValueError, match="exit 2 requires"):
        RunResult(command, 2)
    diagnostic = Diagnostic("parse_error", command, "result is unknown", "Repair the input.")
    assert RunResult(command, 2, diagnostics=(diagnostic,)).exit_code == 2
    with pytest.raises(ValueError, match="diagnostics require"):
        RunResult(command, 0, diagnostics=(diagnostic,))
