# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest
from test_delta import _model
from test_expectation import _delta_payload

from archkeel.ir.codec import parse_delta, parse_observation
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import Diagnostic, RatchetObservations, RunResult
from archkeel.render.html import render_check_html, render_html
from archkeel.render.summary import check_decision_sentence

FAILED_CHECK = RunResult(
    "check", 1, "PASS", "PASS", "FAIL", git_predicate="PASS", host_order="PASS"
)


def test_html_report_preserves_verdicts_evidence_and_visual_contract() -> None:
    raw = _model(git_head="a" * 40)
    raw["coverage"].update(
        calls_analyzed=3,
        calls_resolved=2,
        calls_unresolved=1,
        call_resolution_percent=66.67,
    )
    observation = parse_observation(raw)
    measurements = Measurements(RatchetScalars(0, 0, 0, 0, 1, 0), 3, "measured")
    result = RunResult(
        "report",
        0,
        observation_complete="PASS",
        declared_rules="PASS",
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        measurements=measurements,
        python_version=observation.python_version,
    )

    page = render_html(
        result,
        observation,
        repository="sample <repo>",
        architecture_href="architecture.json",
    ).decode()

    assert page.index("observation_complete") < page.index("declared_rules")
    assert page.index("declared_rules") < page.index("expectation_fulfilled")
    assert "sample &lt;repo&gt;" in page
    assert "✓</span>PASS" in page
    assert "i</span>NOT APPLICABLE" in page
    assert "1/3" in page and "2/3 (66.67%)" in page
    assert "--ck-lime: #c5f82a" in page and "--ck-unknown: #f4c95d" in page
    assert page.count("data:image/svg+xml;base64,") == 3
    assert "architecture score" not in page.lower()
    assert 'src="http' not in page and 'href="http' not in page


def test_html_report_never_styles_missing_evidence_as_pass() -> None:
    diagnostic = Diagnostic(
        "missing_tool",
        "git",
        "The source revision cannot be established.",
        "Install Git and retry.",
    )
    result = RunResult("report", 2, diagnostics=(diagnostic,))

    page = render_html(
        result,
        None,
        repository="sample",
        architecture_href=None,
    ).decode()

    assert 'data-decision="unknown"' in page
    assert "UNVERIFIABLE" in page
    assert "unknown_claim" in page and "Install Git and retry." in page
    assert 'data-decision="pass"' not in page.split("</style>", 1)[1]


def test_check_html_renders_structured_regression_values() -> None:
    baseline = Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 2, "measured")
    candidate = Measurements(RatchetScalars(0, 0, 0, 0, 1, 0), 1, "measured")
    delta = replace(
        parse_delta(_delta_payload()),
        ratchets=RatchetObservations("SUPPORTED", baseline, candidate),
    )
    coverage = replace(
        parse_observation(_model(git_head="a" * 40)).coverage,
        files_discovered=3,
        files_parsed=3,
    )
    result = replace(FAILED_CHECK, delta=delta, coverage=coverage)
    page = render_check_html(result, repository="sample", result_href="result.json").decode()
    assert check_decision_sentence(result) == (
        "Do not merge: calls_unresolved rose 0 → 1 and unresolved_ratio 0/2 → 1/1."
    )
    assert check_decision_sentence(result) in page
    assert "All 3 files parsed." in page
    assert "2 of 7 regression checks failed." in page
    assert "calls_unresolved" in page and "0 → 1" in page
    assert "unresolved_ratio" in page and "0/2 → 1/1" in page
    regression_table = page.split("<h2>Regression checks</h2>", 1)[1].split("</table>", 1)[0]
    assert regression_table.index("calls_unresolved") < regression_table.index("violations")
    assert regression_table.index("unresolved_ratio") < regression_table.index("violations")
    assert page.split("</style>", 1)[1].count('data-status="fail"') == 2


def test_check_decision_limits_regression_details() -> None:
    baseline = Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 2, "measured")
    candidate = Measurements(RatchetScalars(1, 1, 1, 1, 1, 0), 1, "measured")
    delta = replace(
        parse_delta(_delta_payload()),
        ratchets=RatchetObservations("SUPPORTED", baseline, candidate),
    )
    sentence = check_decision_sentence(replace(FAILED_CHECK, delta=delta))
    assert sentence.endswith("private_crossings rose 0 → 1 and +3 more.")
    assert "typing_positions" not in sentence


def test_check_html_renders_publication_order_failure() -> None:
    failure = "expectation was not published before the first candidate submission"
    result = replace(FAILED_CHECK, host_order="FAIL", failures=(failure,))
    page = render_check_html(result, repository="sample", result_href="result.json").decode()
    assert check_decision_sentence(result) == (
        "Do not merge: the expectation was not published before the first candidate submission."
    )
    assert check_decision_sentence(result) in page
    assert "Publication order" in page and "host_order" in page
    assert "Expectation published after first submission." in page
    assert failure in page


def test_check_html_explains_a_passing_candidate() -> None:
    measurements = Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 2, "measured")
    result = replace(
        FAILED_CHECK,
        exit_code=0,
        expectation_fulfilled="PASS",
        delta=replace(
            parse_delta(_delta_payload()),
            ratchets=RatchetObservations("SUPPORTED", measurements, measurements),
        ),
    )
    sentence = "Merge: all five verdicts passed and no regression check failed."
    page = render_check_html(result, repository="sample", result_href="result.json").decode()
    assert check_decision_sentence(result) == sentence
    assert sentence in page


def test_check_html_never_styles_unverifiable_as_pass() -> None:
    diagnostic = Diagnostic(
        "missing_tool", "git", "Commit order cannot be established.", "Install Git and retry."
    )
    result = RunResult("check", 2, diagnostics=(diagnostic,))
    page = render_check_html(result, repository="sample", result_href="result.json").decode()
    assert check_decision_sentence(result) == (
        "Do not merge: missing_tool — Commit order cannot be established."
    )
    assert check_decision_sentence(result) in page
    assert 'data-decision="unknown"' in page
    assert "UNVERIFIABLE" in page
    assert "Scan completeness is unverifiable." in page
    assert "unknown_claim" in page and "Install Git and retry." in page
    assert 'data-decision="pass"' not in page.split("</style>", 1)[1]


# Wordmarks may split the name across tspans; compare the rendered text, not the source.
@pytest.mark.parametrize("name", ["archkeel-logo-dark.svg", "archkeel-logo-light.svg"])
def test_logo_wordmark_reads_archkeel(name: str) -> None:
    svg = Path(__file__).parents[1] / "src/archkeel/render/assets" / name
    text = ElementTree.parse(svg).find("{http://www.w3.org/2000/svg}text")
    assert text is not None
    assert "".join(text.itertext()).strip() == "archkeel"
