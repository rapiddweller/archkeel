# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest
from test_architecture_demo import CONFIG, _prepare_repo
from test_delta import _model
from test_expectation import _delta_payload
from test_interfaces import _declaration, _import_record, _symbol_record

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_delta, parse_observation
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import Diagnostic, RatchetObservations, RunResult
from archkeel.render.html import render_architecture_html, render_check_html, render_html
from archkeel.render.summary import check_decision_sentence, report_summary
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import contract_rule_field

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


def test_html_report_shows_fail_headline_when_declared_rules_fail() -> None:
    """AD-14: report's exit code stays 0, but the headline must follow declared_rules."""
    raw = _model(git_head="a" * 40)
    observation = parse_observation(raw)
    measurements = Measurements(RatchetScalars(3, 0, 0, 0, 0, 0), 0, "n/a")
    result = RunResult(
        "report",
        0,
        observation_complete="PASS",
        declared_rules="FAIL",
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        measurements=measurements,
        python_version=observation.python_version,
    )

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert result.exit_code == 0
    body = page.split("</style>", 1)[1]
    assert 'data-decision="fail"' in body
    assert 'data-decision="pass"' not in body
    assert "3 declared-rule violation(s) found" in page
    assert "report records violations without gating (exit code stays 0)" in page
    assert "Run archkeel check to gate on rule violations" in page
    failures_section = page.split("<h3>Failures</h3>", 1)[1].split("<h3>Diagnostics</h3>", 1)[0]
    assert "None." not in failures_section
    assert "see declared-rule violations below" in failures_section


def test_html_report_clean_report_still_reports_no_failures() -> None:
    raw = _model(git_head="a" * 40)
    observation = parse_observation(raw)
    result = RunResult("report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage)

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert 'data-decision="pass"' in page.split("</style>", 1)[1]
    failures_section = page.split("<h3>Failures</h3>", 1)[1].split("<h3>Diagnostics</h3>", 1)[0]
    assert "<li>None.</li>" in failures_section


def test_html_report_names_agent_decisions_awaiting_the_architect() -> None:
    """AD-16: the HTML summary shows the same agent-decision count as the terminal."""
    raw = _model(git_head="a" * 40)
    observation = parse_observation(raw)
    result = RunResult(
        "report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage, agent_decisions=(2, 5)
    )

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert "2 of 5 rules decided by the agent, awaiting the architect." in page


def test_html_report_renders_component_communication_table() -> None:
    raw = _model(
        git_head="a" * 40,
        imports=[
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="typed",
                origin_definition="pkg.b.typed",
            ),
            _import_record(
                "IMP-2",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="untyped",
                origin_definition="pkg.b.untyped",
            ),
        ],
    )
    raw["declarations"] = [_declaration("a", ["pkg.a"]), _declaration("b", ["pkg.b"])]
    raw["symbols"] = [
        _symbol_record(
            "SYM-1",
            kind="function",
            qualified_name="pkg.b.typed",
            module="pkg.b",
            name="typed",
            parameters=[{"name": "value", "annotation": "int"}],
            returns="str",
        ),
        _symbol_record(
            "SYM-2",
            kind="function",
            qualified_name="pkg.b.untyped",
            module="pkg.b",
            name="untyped",
            parameters=[{"name": "value", "annotation": None}],
            returns=None,
        ),
    ]
    observation = parse_observation(raw)
    result = RunResult("report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage)

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert "Component communication" in page
    assert "pkg.b:typed" in page and "pkg.b:untyped" in page
    assert "value: int" in page and ") → str" in page
    assert "value: UNKNOWN" in page and ") → UNKNOWN" in page
    assert "a → b" in page


def test_html_report_reports_no_cross_component_imports() -> None:
    raw = _model(git_head="a" * 40)
    raw["declarations"] = [_declaration("a", ["pkg.a"])]
    observation = parse_observation(raw)
    result = RunResult("report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage)

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert "Component communication" in page
    assert "No cross-component imports were observed." in page


def test_html_report_rendered_from_architecture_json_alone_shows_agent_decisions(
    tmp_path: Path,
) -> None:
    """AD-16: the count comes from architecture.json bytes, never a `RunResult` field, and
    the terminal summary agrees because both derive it from the same observation."""
    root = _prepare_repo(
        tmp_path,
        {
            "architecture-contract.json": contract_rule_field(
                "DEP-MODEL-NO-STORE", decided_by="agent"
            )
        },
    )
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    assert result.agent_decisions == (1, 29)
    assert "1 of 29 rules decided by the agent" in report_summary(result).sentence

    stripped = replace(result, agent_decisions=None)
    page = render_architecture_html(
        stripped, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    assert "1 of 29 rules decided by the agent, awaiting the architect." in page


def _shop_sample_report(tmp_path: Path, variant_id: str) -> str:
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    return render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()


# Every rule id AD-10's flow view must attach to an edge in the "tour" sample (see
# tests/test_flow.py, which derives this set from the same fixture's violations directly).
_TOUR_FLOW_RULE_IDS = (
    "COMPONENT-NO-CYCLES",
    "DEP-APP-NO-STORE-SQLITE",
    "DEP-MODEL-NO-RENDER",
    "DEP-RENDER-NO-STORE",
    "DEP-STORE-NO-MONEY",
    "INTERFACE-BOUNDARY",
)


def test_html_report_flow_view_marks_every_violated_edge_with_its_rule_id(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "tour")

    assert 'id="flow"' in page
    assert 'id="flow-data"' in page
    data_start = page.index('id="flow-data"')
    payload = json.loads(
        page[page.index(">", data_start) + 1 : page.index("</script>", data_start)]
    )

    violated = {
        tuple(edge["rule_ids"]) for edge in payload["edges"] if edge["state"] == "violation"
    }
    assert set().union(*violated) == set(_TOUR_FLOW_RULE_IDS)
    # A single-subject or unowned-target rule never names a component pair (see test_flow.py).
    assert "ASSIGNMENT-COMPLETE" not in set().union(*violated)
    assert "EXTERNAL-JSON-STORE" not in set().union(*violated)
    assert all(edge["state"] in ("conforms", "violation") for edge in payload["edges"])


def test_html_report_flow_view_clean_sample_has_no_violated_edges(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "clean")

    data_start = page.index('id="flow-data"')
    payload = json.loads(
        page[page.index(">", data_start) + 1 : page.index("</script>", data_start)]
    )

    assert payload["edges"]
    assert all(edge["state"] == "conforms" for edge in payload["edges"])
    assert all(edge["rule_ids"] == [] for edge in payload["edges"])


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
