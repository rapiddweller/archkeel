# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from test_delta import _model

from codekeel.check.html import render_html
from codekeel.ir.codec import parse_observation
from codekeel.ir.measurements import Measurements, RatchetScalars
from codekeel.ir.model import Diagnostic, RunResult


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
    body = page.split("</style>", 1)[1]
    assert 'data-decision="pass"' not in body
