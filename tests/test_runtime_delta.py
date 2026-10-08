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
    if "calls" in profile.absent_sections:
        for key in (
            "calls_analyzed",
            "calls_resolved",
            "calls_partially_resolved",
            "calls_unresolved",
            "call_resolution_percent",
        ):
            raw["coverage"][key] = None
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
    raw["analyzer"]["name"] = "archkeel-dart-analyzer"
    for section in ("typing_signals", "constructs"):
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
    raw["analyzer"]["name"] = "archkeel-dart-analyzer"
    for section in ("typing_signals", "constructs"):
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


@pytest.mark.parametrize("labels", ["analyzer", "producer", "both"])
def test_producer_distribution_label_does_not_change_identical_parser_bytes(labels: str) -> None:
    raw = _model(git_head="a" * 40)
    raw["analyzer"]["name"] = "archkeel-dart-analyzer"
    for section in ("typing_signals", "constructs"):
        raw[section] = None
    baseline = replace(
        parse_observation(raw),
        runtime=RuntimeInfo("python", "3.11.12"),
        producer=AnalyzerInfo("directive-parser", "1.0.0", "b" * 64),
    )
    head = replace(
        baseline,
        analyzer=replace(baseline.analyzer, version="1.0.1")
        if labels in ("analyzer", "both")
        else baseline.analyzer,
        producer=replace(baseline.producer, version="1.0.1")
        if labels in ("producer", "both")
        else baseline.producer,
    )
    delta = build_architecture_delta(
        baseline,
        head,
        baseline_digest="a" * 64,
        head_digest="b" * 64,
        checker_digest="c" * 64,
    )
    assert delta.coverage.status == "PASS"


@pytest.mark.parametrize(
    "producer",
    [
        None,
        AnalyzerInfo("different-parser", "1.0.0", "b" * 64),
        AnalyzerInfo("directive-parser", "1.0.0", "c" * 64),
    ],
)
def test_changed_or_missing_producer_identity_is_incomparable(
    producer: AnalyzerInfo | None,
) -> None:
    raw = _model(git_head="a" * 40)
    raw["analyzer"]["name"] = "archkeel-dart-analyzer"
    for section in PROFILES["dart"].absent_sections:
        raw[section] = None
    baseline = replace(
        parse_observation(raw),
        runtime=RuntimeInfo("python", "3.11.12"),
        producer=AnalyzerInfo("directive-parser", "1.0.0", "b" * 64),
    )
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            baseline,
            replace(baseline, producer=producer),
            baseline_digest="a" * 64,
            head_digest="b" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"


@pytest.mark.parametrize(
    "runtime", [None, RuntimeInfo("node", "3.11.12"), RuntimeInfo("python", "3.12.10")]
)
def test_changed_or_missing_explicit_runtime_is_incomparable(runtime: RuntimeInfo | None) -> None:
    baseline = replace(
        parse_observation(_model(git_head="a" * 40)),
        runtime=RuntimeInfo("python", "3.11.12"),
        producer=AnalyzerInfo("python-parser", "1.0.0", "b" * 64),
    )
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            baseline,
            replace(baseline, runtime=runtime),
            baseline_digest="a" * 64,
            head_digest="b" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"


def test_requirement_state_does_not_change_runtime_identity_and_old_reports_load() -> None:
    declared = RuntimeInfo("python", "3.11.12", ">=3.11")
    missing = RuntimeInfo("python", "3.11.12", ">=3.11", "metadata_missing")
    assert declared == missing

    raw = _model(git_head="a" * 40)
    raw["runtime"] = {"name": "python", "version": "3.11.12", "required": ">=3.11"}
    assert parse_observation(raw).runtime == declared

    raw["runtime"]["requirement_state"] = "unknown"
    with pytest.raises(ValueError, match="requirement_state"):
        parse_observation(raw)


def test_different_analyzer_bytes_never_grant_coverage() -> None:
    baseline = parse_observation(_model(git_head="a" * 40))
    delta = build_architecture_delta(
        baseline,
        replace(baseline, analyzer=replace(baseline.analyzer, code_digest="d" * 64)),
        baseline_digest="a" * 64,
        head_digest="b" * 64,
        checker_digest="c" * 64,
    )
    assert delta.coverage.status == "FAIL"
    assert delta.ratchets.status == "UNKNOWN"


def test_different_analyzer_profile_is_incomparable() -> None:
    baseline = parse_observation(_model(git_head="a" * 40))
    with pytest.raises(DiagnosticError) as error:
        build_architecture_delta(
            baseline,
            replace(
                baseline,
                analyzer=replace(baseline.analyzer, name="archkeel-dart-analyzer"),
            ),
            baseline_digest="a" * 64,
            head_digest="b" * 64,
            checker_digest="c" * 64,
        )
    assert error.value.diagnostic.kind == "incomparable_runtime"


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


@pytest.mark.parametrize("version", ["1.3.0", "1.4.0", "2.0.0"])
def test_runtime_metadata_requires_delta_2_and_preserves_legacy_read(version):
    from archkeel.ir.codec import delta_payload

    raw = _delta_payload()
    raw["schema_version"] = version
    for side in ("baseline", "head"):
        raw[side]["runtime"] = {"name": "python", "version": "3.11.12"}
    legacy = parse_delta(raw)
    assert delta_payload(legacy)["schema_version"] == version
    assert "requirement_state" not in delta_payload(legacy)["head"]["runtime"]
    for side in ("baseline", "head"):
        raw[side]["runtime"]["requirement_state"] = "metadata_missing"
    if version != "2.0.0":
        with pytest.raises(ValueError, match="requirement_state"):
            parse_delta(raw)
    else:
        parsed = parse_delta(raw)
        assert parsed.head.runtime.requirement_state == "metadata_missing"
        assert parse_delta(delta_payload(parsed)) == parsed
        with pytest.raises(ValueError, match="requires Delta schema 2.0.0"):
            delta_payload(replace(parsed, schema_version="1.4.0"))
