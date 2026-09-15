# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import FrozenInstanceError
from typing import cast, get_args

import pytest

from archkeel.ir.codec import result_bytes
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticKind,
    ObservationResult,
    RatchetObservations,
    RecordData,
    RunResult,
)


def test_measurements_exist_exactly_when_regression_checks_are_supported() -> None:
    measured = Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 1, "measured")
    with pytest.raises(ValueError, match="exactly when"):
        RatchetObservations("SUPPORTED", measured)
    with pytest.raises(ValueError, match="exactly when"):
        RatchetObservations("UNKNOWN", measured, measured, reason="unavailable")
    assert RatchetObservations("SUPPORTED", measured, measured).head == measured
    assert RatchetObservations("UNKNOWN", reason="unavailable").baseline is None


def test_missing_observation_requires_diagnostic() -> None:
    with pytest.raises(ValueError, match="requires a diagnostic"):
        ObservationResult(None, None, ())
    diagnostic = Diagnostic("missing_tool", "analyzer", "scan completeness", "Install analyzer.")
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


def test_diagnostic_kind_uses_the_declared_literal_values() -> None:
    for kind in get_args(DiagnosticKind):
        code = "rule.violated" if kind == "contract_invalid" else None
        Diagnostic(kind, "subject", "unknown claim", "Retry.", None, code)
    with pytest.raises(ValueError, match="invalid diagnostic kind"):
        Diagnostic(cast(DiagnosticKind, "invalid"), "subject", "unknown claim", "Retry.")


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


def test_json_pointer_is_emitted_only_for_validation_diagnostics() -> None:
    ordinary = Diagnostic("parse_error", "file.py", "unknown", "Retry.")
    validation = Diagnostic(
        "contract_invalid", "rule", "unknown", "Fix it.", "/rules/0", "rule.violated"
    )
    assert b'"pointer"' not in result_bytes(RunResult("report", 2, diagnostics=(ordinary,)))
    assert b'"pointer":"/rules/0"' in result_bytes(
        RunResult("validate", 2, diagnostics=(validation,))
    )
    with pytest.raises(ValueError, match="JSON Pointer"):
        Diagnostic("contract_invalid", "rule", "unknown", "Fix it.", "rules/0", "rule.violated")


def test_contract_invalid_diagnostic_requires_a_code() -> None:
    with pytest.raises(ValueError, match="require a code"):
        Diagnostic("contract_invalid", "rule", "unknown", "Fix it.")


def test_only_contract_invalid_diagnostics_carry_a_code() -> None:
    with pytest.raises(ValueError, match="only contract_invalid"):
        Diagnostic("parse_error", "file.py", "unknown", "Retry.", None, "rule.violated")


def test_diagnostic_code_uses_the_declared_literal_values() -> None:
    for code in get_args(DiagnosticCode):
        Diagnostic("contract_invalid", "subject", "unknown claim", "Retry.", None, code)
    with pytest.raises(ValueError, match="invalid diagnostic code"):
        Diagnostic(
            "contract_invalid",
            "subject",
            "unknown claim",
            "Retry.",
            None,
            cast(DiagnosticCode, "x"),
        )


def test_code_is_emitted_only_when_present() -> None:
    without_code = Diagnostic("parse_error", "file.py", "unknown", "Retry.")
    with_code = Diagnostic(
        "contract_invalid", "rule", "unknown", "Fix it.", "/rules/0", "rule.violated"
    )
    assert b'"code"' not in result_bytes(RunResult("report", 2, diagnostics=(without_code,)))
    assert b'"code":"rule.violated"' in result_bytes(
        RunResult("validate", 2, diagnostics=(with_code,))
    )
