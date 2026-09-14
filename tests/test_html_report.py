# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from pathlib import Path
from xml.etree import ElementTree

import pytest
from test_delta import _model

from archkeel.ir.codec import parse_observation
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import Diagnostic, RunResult
from archkeel.render.html import render_html


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


# Wordmarks may split the name across tspans; compare the rendered text, not the source.
@pytest.mark.parametrize("name", ["archkeel-logo-dark.svg", "archkeel-logo-light.svg"])
def test_logo_wordmark_reads_archkeel(name: str) -> None:
    svg = Path(__file__).parents[1] / "src/archkeel/render/assets" / name
    text = ElementTree.parse(svg).find("{http://www.w3.org/2000/svg}text")
    assert text is not None
    assert "".join(text.itertext()).strip() == "archkeel"
