# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import replace

import pytest
from test_delta import _model
from test_expectation import _delta_payload, _expectation_payload

from pledge.check.delta import build_architecture_delta
from pledge.check.expectation import evaluate_expectation, parse_expectation
from pledge.check.report import unknown_result
from pledge.ir.codec import parse_delta, parse_observation
from pledge.ir.model import DiagnosticError


@pytest.mark.parametrize("version", [None, "3.12.10", "3.11.13"])
def test_different_or_missing_runtime_is_exit_two(version: str | None) -> None:
    raw = _model(git_head="a" * 40)
    raw["python_version"] = "3.11.12"
    baseline = parse_observation(raw)
    head = replace(baseline, python_version=version)
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            baseline,
            head,
            baseline_digest="a" * 64,
            head_digest="b" * 64,
            checker_digest="c" * 64,
        )
    result = unknown_result("check", "delta", error.value)
    assert result.exit_code == 2
    assert result.diagnostics[0].kind == "incomparable_runtime"


def test_supplied_delta_cannot_bypass_runtime_comparison() -> None:
    raw = _delta_payload()
    raw["baseline"]["python_version"] = "3.11.12"
    raw["head"]["python_version"] = "3.12.10"
    with pytest.raises(DiagnosticError) as error:
        evaluate_expectation(parse_delta(raw), parse_expectation(_expectation_payload()))
    assert error.value.diagnostic.kind == "incomparable_runtime"


def test_equal_runtime_is_retained_in_delta() -> None:
    raw = _model(git_head="a" * 40)
    raw["python_version"] = "3.11.12"
    observation = parse_observation(raw)
    delta = build_architecture_delta(
        observation,
        observation,
        baseline_digest="a" * 64,
        head_digest="a" * 64,
        checker_digest="c" * 64,
    )
    assert delta.baseline.python_version == delta.head.python_version == "3.11.12"
    assert delta.coverage.status == "PASS"


@pytest.mark.parametrize("version", ["", "3.12", "invalid", None, True])
def test_explicit_invalid_runtime_provenance_is_rejected(version: object) -> None:
    raw = _model(git_head="a" * 40)
    raw["python_version"] = version
    with pytest.raises(ValueError, match="python_version"):
        parse_observation(raw)


def test_legacy_report_is_readable_but_not_comparable() -> None:
    raw = _model(git_head="a" * 40)
    del raw["python_version"]
    observation = parse_observation(raw)
    assert observation.python_version is None
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            observation,
            observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"
