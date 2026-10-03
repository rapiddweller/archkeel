# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import replace

import pytest
from test_delta import _model
from test_expectation import _delta_payload, _expectation_payload

from archkeel.check.delta import build_architecture_delta
from archkeel.check.expectation import evaluate_expectation, parse_expectation
from archkeel.check.report import unknown_result
from archkeel.ir.codec import parse_delta, parse_observation
from archkeel.ir.model import AnalyzerInfo, DiagnosticError, RuntimeInfo
from archkeel.ir.profiles import PROFILES


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("field", ["analyzer", "contract"])
@pytest.mark.parametrize("value", ["", " ", "unknown", "UNKNOWN", " unknown "])
def test_equal_missing_comparison_identity_never_grants_coverage(language, field, value):
    raw = _model(git_head="a" * 40)
    profile = PROFILES[language]
    raw["analyzer"]["name"] = profile.analyzer
    for name in profile.absent_sections:
        raw[name] = None
    observation = parse_observation(raw)
    if language != "python":
        observation = replace(
            observation,
            runtime=RuntimeInfo("cpython", "3.11.12"),
            producer=AnalyzerInfo(profile.analyzer, "1.0.0", "c" * 64),
        )
    if field == "analyzer":
        observation = replace(
            observation, analyzer=replace(observation.analyzer, code_digest=value)
        )
    else:
        observation = replace(observation, contract=replace(observation.contract, digest=value))
    delta = build_architecture_delta(
        observation,
        observation,
        baseline_digest="a" * 64,
        head_digest="a" * 64,
        checker_digest="c" * 64,
    )
    assert delta.coverage.status == "FAIL"
    assert delta.ratchets.status == "UNKNOWN"


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


@pytest.mark.parametrize("field", ["name", "version", "code_digest"])
@pytest.mark.parametrize("missing", ["", " ", "unknown", "UNKNOWN"])
def test_equal_incomplete_producer_cannot_pass_a_language_delta(field: str, missing: str) -> None:
    raw = _model(git_head="a" * 40)
    raw["analyzer"]["name"] = "archkeel-dart-directives"
    for section in ("symbols", "references", "bindings"):
        raw[section] = None
    producer = {"name": "directive-parser", "version": "1.0.0", "code_digest": "b" * 64}
    producer[field] = missing
    observation = replace(
        parse_observation(raw),
        runtime=RuntimeInfo("cpython", "3.11.12"),
        producer=AnalyzerInfo(**producer),
    )
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            observation,
            observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"


@pytest.mark.parametrize("field", ["name", "version"])
@pytest.mark.parametrize("missing", ["", " ", "unknown", "UNKNOWN"])
def test_equal_incomplete_runtime_cannot_pass_a_language_delta(field: str, missing: str) -> None:
    raw = _model(git_head="a" * 40)
    raw["analyzer"]["name"] = "archkeel-dart-directives"
    for section in ("symbols", "references", "bindings"):
        raw[section] = None
    runtime = {"name": "cpython", "version": "3.11.12"}
    runtime[field] = missing
    observation = replace(
        parse_observation(raw),
        runtime=RuntimeInfo(**runtime),
        producer=AnalyzerInfo("directive-parser", "1.0.0", "b" * 64),
    )
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            observation,
            observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"


def test_producer_distribution_label_does_not_change_identical_parser_bytes() -> None:
    raw = _model(git_head="a" * 40)
    raw["analyzer"]["name"] = "archkeel-dart-directives"
    for section in ("symbols", "references", "bindings"):
        raw[section] = None
    baseline = replace(
        parse_observation(raw),
        runtime=RuntimeInfo("python", "3.11.12"),
        producer=AnalyzerInfo("directive-parser", "1.0.0", "b" * 64),
    )
    head = replace(
        baseline,
        analyzer=replace(baseline.analyzer, version="1.0.1"),
        producer=replace(baseline.producer, version="1.0.1"),
    )
    delta = build_architecture_delta(
        baseline,
        head,
        baseline_digest="a" * 64,
        head_digest="b" * 64,
        checker_digest="c" * 64,
    )
    assert delta.coverage.status == "PASS"


def test_python_profile_prefers_explicit_collector_runtime() -> None:
    raw = _model(git_head="a" * 40)
    raw.pop("python_version")
    observation = replace(
        parse_observation(raw),
        runtime=RuntimeInfo("node", "22.23.3"),
        producer=AnalyzerInfo("python-parser", "1.0.0", "b" * 64),
    )
    delta = build_architecture_delta(
        observation,
        observation,
        baseline_digest="a" * 64,
        head_digest="a" * 64,
        checker_digest="c" * 64,
    )
    assert delta.coverage.status == "PASS"


def test_partial_common_provenance_cannot_use_the_legacy_python_fallback() -> None:
    observation = replace(
        parse_observation(_model(git_head="a" * 40)),
        producer=AnalyzerInfo("alternate-parser", "1.0.0", "b" * 64),
    )
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            observation,
            observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"
