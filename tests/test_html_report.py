# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pytest
from test_architecture_demo import CONFIG, _prepare_repo
from test_delta import _model
from test_expectation import _delta_payload
from test_interfaces import _declaration, _import_record, _symbol_record

from archkeel.check.declarations import _requires_entries
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_delta, parse_observation
from archkeel.ir.decisions import agent_decisions
from archkeel.ir.facts import EvidenceClass
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import (
    ComponentRole,
    ContractComponent,
    Diagnostic,
    Observation,
    RatchetObservations,
    RequiredComponent,
    RuleAssessment,
    RunResult,
)
from archkeel.render.html import (
    _module_tree_html,
    render_architecture_html,
    render_check_html,
    render_html,
)
from archkeel.render.summary import badge, check_decision_sentence, check_summary, report_summary
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import contract_rule_field, contract_without_rule

FAILED_CHECK = RunResult(
    "check", 1, "PASS", "PASS", "FAIL", git_predicate="PASS", host_order="PASS"
)


class _StartTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _start_tags(page: str, tag: str) -> list[dict[str, str | None]]:
    parser = _StartTags()
    parser.feed(page)
    return [attrs for name, attrs in parser.tags if name == tag]


def _native_audit(page: str, observation: Observation, architecture_href: str):
    start = page.index(">", page.index('id="flow-data"')) + 1
    atlas = json.loads(page[start : page.index("</script>", start)])["atlas"]
    assert atlas["source"] == {
        "git_head": observation.source.git_head,
        "source_digest": observation.source.source_digest,
    }
    assert not {"coverage", "contract_digest", "analyzer_digest"} & atlas.keys()
    assert atlas["architecture_href"] == architecture_href
    assert "Snapshot and audit" in page
    assert observation.source.source_digest in page
    assert observation.contract.digest in page
    assert f'href="{architecture_href}"' in page
    return atlas


def _native_details(output: Path, observation: Observation):
    atlas = _native_audit(output.with_suffix(".report.html").read_text(), observation, output.name)
    routes = [f"?component={item['id']}" for item in atlas["components"]]
    routes.append(atlas["unassigned_detail_href"])
    assert all(route.startswith("?component=") for route in routes)
    reports = (_standard_report((output.parent / atlas["detail_page"]).read_text()),)
    evidence = {item.id: item for item in observation.evidence}
    records = {
        item.id: item
        for section in ("violations", "unknowns")
        for item in observation.records(section) or ()
    }
    for report in reports:
        assert report.observed is not None
        assert all(item == evidence[item.id] for item in report.observed.evidence)
        for finding in report.findings:
            record = records[finding.id]
            assert (
                finding.kind,
                finding.title,
                finding.rule_ids,
                finding.subjects,
                finding.evidence_ids,
                finding.provenance,
            ) == (
                record.kind,
                record.title,
                record.rule_ids,
                record.subjects,
                record.evidence_ids,
                record.provenance,
            )
            assert finding.status == (
                "FAIL" if record.evidence_class == EvidenceClass.VIOLATION else "UNKNOWN"
            )
            assert set(finding.evidence_ids) <= {item.id for item in report.observed.evidence}
    return reports


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
    assert "One repository snapshot." in page
    assert "not change against an earlier revision or runtime behavior" in page


def test_html_report_skips_allowance_panel_when_typing_signals_are_unavailable() -> None:
    observation = parse_observation(_model(git_head="a" * 40))
    observation = replace(
        observation,
        sections=tuple(
            section for section in observation.sections if section.name != "typing_signals"
        ),
    )
    result = RunResult(
        "report",
        0,
        observation_complete="PASS",
        declared_rules="PASS",
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        python_version=observation.python_version,
    )

    page = render_html(
        result,
        observation,
        repository="sample",
        architecture_href="architecture.json",
    ).decode()

    assert "Applied boundary type allowances" not in page


def test_html_report_wraps_long_text_in_the_allowance_table() -> None:
    raw = _model(git_head="a" * 40)
    raw["typing_signals"] = [
        {
            "id": "TYPE-" + "a" * 64,
            "evidence_class": "FACT",
            "area": "type_architecture",
            "kind": "boundary_type_allowance",
            "title": (
                "sample.app.impl.read_csv_having_weight_column has an exact unique contained "
                "mapping allowance for dict[str, str] at container depth 2"
            ),
            "subjects": ["sample.app.impl.read_csv_having_weight_column", "sample.app.facade"],
            "evidence_ids": [],
            "rule_ids": ["APP-TYPES-NOT-DICT"],
            "fact_ids": [],
            "provenance": [],
            "data": {},
        }
    ]
    observation = parse_observation(raw)
    result = RunResult("report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage)

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert '<table class="boundary-type-allowances-table">' in page
    assert ".boundary-type-allowances-table td" in page
    assert "overflow-wrap: anywhere;" in page


def test_html_report_lists_compatibility_migration_work() -> None:
    raw = _model(git_head="a" * 40)
    raw["declarations"] = [
        {
            "id": "COMPAT-MIGRATION-WORK",
            "evidence_class": "DECLARED_RULE",
            "area": "compatibility",
            "kind": "compatibility_migration_work",
            "title": "Migration compatibility shims remain",
            "subjects": ["pkg.old"],
            "evidence_ids": [],
            "rule_ids": [],
            "fact_ids": [],
            "provenance": [],
            "data": {"count": 1, "modules": ["pkg.old"]},
        }
    ]
    observation = parse_observation(raw)
    result = RunResult("report", 0, "PASS", "PASS", "n/a", coverage=observation.coverage)

    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert "Compatibility migration work" in page
    assert "1 migration shim(s) remain." in page
    assert "<summary><code>pkg</code>" in page
    assert "<li><code>old</code></li>" in page


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
    assert "archkeel validate --baseline architecture-baseline.json" in page
    failures_section = page.split("<h3>Failures</h3>", 1)[1].split("<h3>Diagnostics</h3>", 1)[0]
    assert "<li>None.</li>" in failures_section
    assert "Report mode does not evaluate an expectation" not in failures_section
    assert "see declared-rule violations below" in page


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

    assert "2 of 5 decisions made by the agent, awaiting the architect." in page


def test_html_report_collapses_cross_component_import_evidence() -> None:
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
            _import_record(
                "IMP-3",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="Missing",
                origin_definition="pkg.b.Missing",
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

    assert "Cross-component imports" in page
    assert "All 1 component pairs · 3 imported names" in page
    assert '<details class="connection-row">' in page
    assert "pkg.b:typed" in page and "pkg.b:untyped" in page
    assert "pkg.b:Missing</code> unknown" in page
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

    assert "Cross-component imports" in page
    assert "No cross-component imports were observed." in page


def test_native_html_audit_keeps_agent_decisions_in_the_recorded_packet(
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
    # 40 rules (AD-11, issue #47), 8 declared public lists and the inside's 3 requires entries
    # (AD-50).
    assert result.agent_decisions == (1, 51)
    assert "1 of 51 decisions made by the agent" in report_summary(result).sentence

    stripped = replace(result, agent_decisions=None)
    page = render_architecture_html(
        stripped, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    assert agent_decisions(observation) == (1, 51)
    decision = next(
        item
        for item in observation.records("declarations") or ()
        if item.id == "DEP-MODEL-NO-STORE"
    )
    assert decision.data.get("decided_by") == "agent"
    _native_audit(page, observation, "architecture.json")


def _shop_sample_report(tmp_path: Path, variant_id: str) -> str:
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    return render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()


def _standard_report(page: str):
    start = page.index(">", page.index('id="flow-data"')) + 1
    data = json.loads(page[start : page.index("</script>", start)])
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation"}
        }
    )


# Every rule id AD-10's flow view must attach to an edge in the "tour" sample (see
# tests/test_flow.py, which derives this set from the same fixture's violations directly).
_TOUR_FLOW_RULE_IDS = (
    "COMPONENT-NO-CYCLES",
    "DEP-APP-NO-STORE-BACKEND",
    "DEP-APP-NO-STORE-SQLITE",
    "DEP-MODEL-NO-RENDER",
    "DEP-RENDER-NO-STORE",
    "DEP-STORE-NO-MONEY",
    "INTERFACE-BOUNDARY",
    "EXTERNAL-JSON-STORE",
)


def test_html_report_flow_view_marks_every_violated_edge_with_its_rule_id(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "tour")
    report = _standard_report(page)
    assert report.observed is not None
    finding_rules = {
        rule for item in report.findings if item.status == "FAIL" for rule in item.rule_ids
    }
    assert set(_TOUR_FLOW_RULE_IDS) <= finding_rules
    sites = {item.id for item in report.observed.relationships}
    marked_rules = {
        rule
        for item in report.findings
        if sites.intersection(item.graph_subject_ids)
        for rule in item.rule_ids
    }
    assert set(_TOUR_FLOW_RULE_IDS) <= marked_rules
    control = next(
        attrs for attrs in _start_tags(page, "label") if attrs.get("for") == "flow-violations-only"
    )
    assert "flow-graph-filter" in page
    assert "hidden" in control


def test_html_report_explorer_uses_one_observation_for_three_views(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "tour")
    assert page.count('id="flow-data"') == 1
    assert '<nav class="flow-views" aria-label="Architecture views" hidden>' in page
    for view in ("diagram", "target", "diff", "structure", "review"):
        assert f'data-flow-view="{view}"' in page
    report = _standard_report(page)
    assert report.observed is not None and report.target is not None
    assert "Recorded findings" in page
    assert "Observed modules" in page
    assert "Cross-component imports" in page


def test_html_report_can_focus_an_open_report_on_violations(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "tour")
    assert "data-violation-focus hidden" in page
    assert "data-report-violations-only" in page
    assert 'id="component-communication-detail" data-secondary-detail' in page
    assert 'id="report-secondary-detail" data-secondary-detail' in page
    assert 'classList.toggle("violations-only", control.checked)' in page
    assert "flowControl.checked = control.checked" in page
    assert 'flowControl.dispatchEvent(new Event("change"))' in page
    assert "DEP-STORE-NO-MONEY" in page
    assert "Cross-component imports" in page
    assert "Known unknowns" in page
    assert "Complete scan inventory" in page
    assert "violationsOnly.checked" in page
    assert "Recorded findings" in page


def test_html_report_locates_a_cited_file_without_a_line(tmp_path: Path) -> None:
    """AD-107: an empty initializer is cited as its file, never as a line 0 that does not exist."""
    page = _shop_sample_report(tmp_path, "class-a-root-layout-empty-package")

    assert "<td><code>shop/extra/__init__.py</code>" in page
    assert "shop/extra/__init__.py:0" not in page


def test_html_report_flow_view_marks_an_undecided_edge(tmp_path: Path) -> None:
    variant = next(item for item in CATALOG if item.id == "tour")
    root = _prepare_repo(
        tmp_path,
        {
            **dict(variant.files),
            "architecture-contract.json": contract_without_rule("DEP-APP-ALLOWS-MODEL"),
        },
    )
    result, encoded = run_report(root, config=CONFIG, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    page = render_html(
        result, model, repository="shop", architecture_href="architecture.json"
    ).decode()
    report = _standard_report(page)
    labels = {item.component_id: item.label for item in report.target.component_intents}
    gap = next(
        item
        for item in report.decision_gaps
        if labels[item.source_id] == "app" and labels[item.target_id] == "model"
    )
    assert gap.relationship_ids
    assert "Open dependency decisions" in page
    assert "This is not a Core UNKNOWN verdict" in page


def test_html_report_flow_view_clean_sample_has_no_violated_edges(tmp_path: Path) -> None:
    report = _standard_report(_shop_sample_report(tmp_path, "clean"))
    assert report.observed.relationships
    assert not any(item.status == "FAIL" for item in report.findings)
    assert report.comparison is None


def test_flow_report_keeps_interface_decisions_and_import_sites(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "class-a-complete-requires")
    report = _standard_report(page)
    assert "How to read this report" in page
    breadcrumb = next(
        attrs
        for attrs in _start_tags(page, "nav")
        if attrs.get("aria-label") == "Diagram breadcrumb"
    )
    assert {"flow-breadcrumb", "flow-navigation-control"} <= set(
        (breadcrumb.get("class") or "").split()
    )
    permissions = [item for item in report.target.relationships if item.kind == "requires"]
    assert permissions and all(item.reason and item.decided_by for item in permissions)
    imports = [item for item in report.observed.relationships if item.kind == "imports"]
    assert imports and all(item.evidence_ids for item in imports)
    proof = {item.id: item for item in report.observed.evidence}
    assert all(
        proof[id].file and proof[id].line > 0 for item in imports for id in item.evidence_ids
    )


def test_static_module_inventory_is_nested_without_duplicate_package_card() -> None:
    tree = _module_tree_html(["pkg", "pkg.api", "pkg.api.users", "pkg.util"])
    assert "<summary><code>pkg</code>" in tree
    assert "<summary><code>api</code>" in tree
    assert "<li><code>users</code></li>" in tree
    assert "<li><code>pkg.api.users</code></li>" not in tree


def test_interactive_flow_controls_start_hidden_without_javascript(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "class-a-complete-requires")

    assert '<div class="flow-toolbar" hidden>' in page
    assert '<nav class="flow-views" aria-label="Architecture views" hidden>' in page
    assert "Observed module tree" in page
    assert 'id="flow-threshold-input"' not in page
    assert 'id="flow-responsibility-search"' not in page
    assert (
        'role="region"\n               aria-label="Pannable component dependencies diagram"' in page
    )


def test_required_interface_projection_keeps_narrowing_and_decider() -> None:
    component = ContractComponent(
        "COMP",
        "app",
        ComponentRole.COMPONENT,
        ("pkg.app",),
        (),
        (),
        (),
        requires=(
            RequiredComponent("domain", "Only use the facade", ("pkg.domain.api",), "agent"),
        ),
        decided_by="architect",
    )
    entry = _requires_entries(component)[0]
    assert entry == {
        "component": "domain",
        "through": ["pkg.domain.api"],
        "rationale": "Only use the facade",
        "decided_by": "agent",
    }


def test_external_scope_keeps_independent_permission_and_recorded_failure(tmp_path: Path) -> None:
    page = _shop_sample_report(tmp_path, "class-a-external-dependency-scope")
    report = _standard_report(page)
    scope = next(item for item in report.target.external_scopes if item.dependency == "json")
    assert scope.id == "EXTERNAL-JSON-STORE"
    assert scope.allowed_sources == ("shop.store",)
    assert scope.rationale and scope.provenance and scope.decided_by
    failures = [
        item for item in report.findings if scope.id in item.rule_ids and item.status == "FAIL"
    ]
    assert failures and all(item.graph_subject_ids for item in failures)
    assert "External dependency permissions" in page


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
    assert "NOT CHECKED" in page
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
    assert "2 of 9 regression checks failed." in page
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
    assert "NOT CHECKED" in page
    assert "The scan could not be completed." in page
    assert "unknown_claim" in page and "Install Git and retry." in page
    assert 'data-decision="pass"' not in page.split("</style>", 1)[1]


# Wordmarks may split the name across tspans; compare the rendered text, not the source.
@pytest.mark.parametrize("name", ["archkeel-logo-dark.svg", "archkeel-logo-light.svg"])
def test_logo_wordmark_reads_archkeel(name: str) -> None:
    svg = Path(__file__).parents[1] / "src/archkeel/render/assets" / name
    text = ElementTree.parse(svg).find("{http://www.w3.org/2000/svg}text")
    assert text is not None
    assert "".join(text.itertext()).strip() == "archkeel"


def test_a_check_that_could_not_decide_a_rule_does_not_claim_every_verdict_passed() -> None:
    """UNKNOWN stays distinct from NOT CHECKED and PASS in the independent verdicts.

    The page then said both things at once: a green PASS over "all five verdicts passed", and a
    card reading "Rules followed: NOT CHECKED". A human approves a merge from the banner.
    """
    result = RunResult(
        "check", 0, "PASS", "UNKNOWN", "PASS", git_predicate="PASS", host_order="PASS"
    )
    assert check_summary(result).decision.label == "UNKNOWN"
    assert "all five verdicts passed" not in check_decision_sentence(result)
    page = render_check_html(result, repository="sample", result_href="result.json").decode()
    assert "all five verdicts passed" not in page


def test_verdict_badges_keep_unknown_and_not_checked_distinct() -> None:
    assert badge("UNKNOWN").label == "UNKNOWN"
    assert badge("n/a").label == "NOT APPLICABLE"
    assert badge("unavailable").label == "NOT CHECKED"


def test_partial_report_does_not_disown_recorded_rule_assessments() -> None:
    result = RunResult(
        "report",
        2,
        "UNKNOWN",
        "UNKNOWN",
        "n/a",
        diagnostics=(Diagnostic("parse_error", "src/main.ts", "Computed import", "Use a literal"),),
        rule_assessments=(),
    )
    summary = report_summary(result)
    assert summary.decision.label == "UNKNOWN"
    assert "Nothing was checked" not in summary.sentence
    assert "Read diagnostics and recorded findings" in summary.sentence


@pytest.mark.parametrize("command", ["report", "validate"])
def test_a_completed_run_with_undecided_rules_does_not_claim_pass(command: str) -> None:
    result = RunResult(command, 0, "PASS", "UNKNOWN", "n/a")
    summary = report_summary(result)
    assert summary.decision.label == "UNKNOWN"
    assert "declared rules could not be evaluated completely" in summary.sentence


def test_rule_rows_show_fail_then_unknown_without_reordering_the_result() -> None:
    observation = parse_observation(_model(git_head="a" * 40))
    assessments = tuple(
        RuleAssessment(
            name, "complete_requires", status, False, 0, 1, "architect", "", (), "", "pkg", ()
        )
        for name, status in (
            ("PASS-ONE", "PASS"),
            ("UNKNOWN-ONE", "UNKNOWN"),
            ("FAIL<ONE>", "FAIL"),
            ("PASS-TWO", "PASS"),
        )
    )
    result = RunResult("report", 0, "PASS", "FAIL", "n/a", rule_assessments=assessments)
    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()
    table = page.split('id="rule-assessments-heading"', 1)[1].split("</section>", 1)[0]
    assert (
        table.index("FAIL&lt;ONE&gt;")
        < table.index("UNKNOWN-ONE")
        < table.index("PASS-ONE")
        < table.index("PASS-TWO")
    )
    assert result.rule_assessments == assessments
    assert "FAIL&lt;ONE&gt;" in page.split('id="rule-assessments-heading"', 1)[0]


def test_report_uses_plain_evidence_labels_and_singular_module() -> None:
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[
                {
                    "id": "module:sample",
                    "evidence_class": "FACT",
                    "area": "source",
                    "kind": "module",
                    "title": "sample",
                    "subjects": ["sample"],
                    "evidence_ids": [],
                    "rule_ids": [],
                    "fact_ids": [],
                    "provenance": [],
                    "data": {"qualified_name": "sample"},
                }
            ],
        )
    )
    report = render_html(
        RunResult("report", 0, "PASS", "PASS", "n/a"),
        observation,
        repository="sample",
        architecture_href="architecture.json",
    ).decode()
    check = render_check_html(FAILED_CHECK, repository="sample", result_href="check.json").decode()
    assert "Observed module tree · 1 module</summary>" in report
    assert "<h2>Source snapshot</h2>" in report
    assert "<th>Area checked</th>" in report
    assert "<h2>Publication timing</h2>" in check
    assert "<h2>Result JSON</h2>" in check
