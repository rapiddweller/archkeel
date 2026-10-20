# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re
import sys
from cProfile import Profile
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from browser_report_support import _browser_page, _open_details, _open_health_check
from test_architecture_demo import _prepare_repo
from test_module_explore import _sample
from test_report_filter import CONFIG as TOUR_CONFIG
from test_report_filter import _tour_root
from test_uml_rendering import _intercept_elk_publication, _wait_for_layout

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.baseline import select_violations
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
    value_bytes,
)
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import ReportFilter, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.render import html as html_renderer
from archkeel.render.html import render_architecture_html


def _result(model):
    return RunResult(
        "report",
        0,
        "PASS",
        "FAIL",
        "n/a",
        coverage=model.coverage,
        rule_assessments=rule_assessments(model, undecided_by_rule={}),
        architecture_projection=architecture_projection(
            model, architecture_report(model), (), violation_remedy="Review native findings"
        ),
    )


def _page(model):
    return render_architecture_html(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()


def test_report_pages_derive_one_graph_per_page(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    result = _result(model)
    encoded = canonical_report_bytes(model)
    with Profile() as work:
        page = render_architecture_html(
            result, encoded, repository="One target", architecture_href="architecture.json"
        )
        details = render_architecture_details(
            result, encoded, repository="One target", architecture_href="architecture.json"
        )
    assert page and len(details) == 1
    graph_builds = sum(
        entry.callcount for entry in work.getstats() if entry.code is architecture_report.__code__
    )
    assert graph_builds == 2


def test_atlas_structure_overview_retains_canonical_component_route(tmp_path):
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core/helper.py": "def one():\n    return 1\n",
            "sample/core/helper2.py": "def two():\n    return 2\n",
        },
    )
    page = _page(model)
    component_id = next(
        item.id
        for item in _result(model).architecture_projection.components
        if item.scope == "core"
    )

    assert '<details class="report-section report-evidence atlas-structure-overview">' in page
    assert "<summary>Structure overview</summary>" in page
    assert "Top-level context" in page
    assert "Architecture boundaries require authored decisions" in page
    assert (
        f'<a href="?component={component_id}" data-atlas-component-route="{component_id}">core</a>'
    ) in page


def test_html_graph_omits_resolvable_record_id_lists_only(tmp_path):
    from archkeel.ir.graph_codec import report_bytes
    from archkeel.render.html import render_architecture_details, render_html

    model = _sample(tmp_path, uml=True)
    report = architecture_report(model)
    canonical = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(model))))
    canonical_ids = {item.id for section in canonical.sections for item in section.records}
    graph_record_ids = {
        record_id
        for graph in (report.observed, report.target)
        if graph is not None
        for item in (*graph.entities, *graph.relationships)
        for record_id in item.record_ids
    }
    assert graph_record_ids and graph_record_ids <= canonical_ids

    result = _result(model)
    documents = [
        render_html(result, model, repository="One target", architecture_href="architecture.json"),
        *render_architecture_details(
            result,
            canonical_report_bytes(model),
            repository="One target",
            architecture_href="architecture.json",
        ).values(),
    ]
    expected = json.loads(report_bytes(report))
    for document in documents:
        page = document.decode()
        match = re.search(
            r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S
        )
        assert match is not None
        actual = json.loads(match.group(1))
        for side in ("observed", "target"):
            expected_graph = expected[side]
            actual_graph = actual[side]
            for collection in ("entities", "relationships"):
                expected_items = expected_graph[collection]
                actual_items = actual_graph[collection]
                assert len(actual_items) == len(expected_items)
                assert actual_items == [
                    {key: value for key, value in item.items() if key != "record_ids"}
                    for item in expected_items
                ]
                assert all("record_ids" not in item for item in actual_items)


def test_atlas_inlines_pinned_elk_before_flow_script_under_offline_csp(tmp_path):
    model = _sample(tmp_path)
    page = _page(model)

    elk_script = '<script data-elkjs-version="0.12.0">'
    assert elk_script in page
    assert page.count(elk_script) == 1
    assert page.index(elk_script) < page.index('<script data-report-asset="explorer">')
    assert "Generated from flow.js; source-sha256=" in page
    assert "default-src 'none'" in page
    assert "script-src 'unsafe-inline'" in page
    assert "worker-src" not in page
    assert not re.search(r"<script\b[^>]*\bsrc=", page)


def _atlas(page):
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))["atlas"]
    data["cells"] = [
        {
            "source_id": data["modules"][row[0]]["id"],
            "target_id": data["modules"][row[1]]["id"],
            "import_sites": row[2],
            "status": row[3],
            "permission": "UNKNOWN",
            "permission_reason": data["reference_ids"][data["cell_permission_reason_ref"]],
            "evidence_ids": row[4],
            "finding_ids": row[5],
            "reasons": [data["reference_ids"][index] for index in row[6]],
        }
        for row in data["cells"]
    ]
    data["rule_assessments"] = [
        {
            **row,
            "id": data["reference_ids"][row["id"]],
            "kind": data["reference_ids"][row["kind"]],
            "reason": data["reference_ids"][row["reason"]],
            "scope": data["reference_ids"][row["scope"]],
            "components": [data["reference_ids"][index] for index in row["components"]],
            "uncertainty_actions": [
                {**action, "next_action": data["reference_ids"][action["next_action"]]}
                for action in row["uncertainty_actions"]
            ],
            "evidence": [
                {**entry, "id": data["reference_ids"][entry["id"]]} for entry in row["evidence"]
            ],
        }
        for row in data["rule_assessments"]
    ]
    data["assignments"] = [
        dict(
            zip(
                ("id", "component_id", "candidate_ids", "ownership_status", "ownership_reason"),
                (
                    data["modules"][row[0]]["id"],
                    data["reference_ids"][row[1]] if row[1] is not None else None,
                    [data["reference_ids"][index] for index in row[2]],
                    row[3],
                    data["reference_ids"][row[4]],
                ),
                strict=True,
            )
        )
        for row in data["assignments"]
    ]
    for module in data["modules"]:
        module["symbol_coverage"] = data["symbol_coverages"][module["symbol_coverage"]]
    for level in data["levels"]:
        level["modules"] = [data["assignments"][index] for index in level["modules"]]
    return data


def test_default_report_is_one_authentic_repository_with_sparse_native_cells(tmp_path):
    model = _sample(tmp_path)
    page = _page(model)
    data = _atlas(page)
    assert data["repository"] == "One target"
    result = _result(model)
    audit = json.loads(canonical_report_bytes(model))
    assert data["declared_rules"] == result.declared_rules
    assert data["observation_complete"] == result.observation_complete
    assert (
        not {
            "coverage",
            "required_relationships",
            "analyzer_digest",
            "contract_digest",
            "finding_count",
        }
        & data.keys()
    )
    assert audit["contract"]["digest"] == model.contract.digest
    assert audit["analyzer"]["code_digest"] == model.analyzer.code_digest
    assert str(model.source.git_head) in page
    assert model.source.source_digest in page
    assert model.contract.digest in page
    assert data["rule_assessments"] == [
        {
            "id": item.id,
            "kind": item.kind,
            "status": item.status,
            "count": item.count,
            "undecided": item.undecided,
            "reason": item.reason,
            "scope": item.scope,
            "scope_id": None,
            "components": list(item.components),
            "component_ids": list(item.components),
            "evaluation_proven": item.evaluation_proven,
            "uncertainty_actions": [],
            "evidence_count": 0,
            "evidence": [],
        }
        for item in result.rule_assessments or ()
    ]
    assert {item["id"] for item in data["components"]} == {"core", "peer"}
    projection = _result(model).architecture_projection
    components = {item.id: item for item in projection.components}
    for item in data["components"]:
        public = components[item["id"]].public
        if public is None:
            assert item["public"] is None
        else:
            assert [data["reference_ids"][index] for index in item["public"]] == list(public)
    assert len(data["cells"]) == 1
    cell = data["cells"][0]
    assert cell["status"] == "FAIL" and cell["permission"] == "UNKNOWN"
    assert cell["import_sites"] == 2
    assert cell["evidence_ids"] and cell["finding_ids"] and cell["reasons"]
    assert "data-ds=" not in page
    assert "Simulate violation" not in page
    assert "EXT-TS" not in page
    assert "Worth a look" in page
    assert 'aria-label="Switch to light theme"' in page
    page_bytes = len(page.encode())
    elk_bytes = (
        (Path(__file__).parents[1] / "src/archkeel/render/assets/elkjs-0.12.0.bundled.js")
        .stat()
        .st_size
    )
    # The Explorer adds inline search, perspectives and export; ELK still dominates the file.
    assert page_bytes < 2_000_000
    assert page_bytes - elk_bytes < 400_000


def test_atlas_header_shows_four_status_cards_with_native_rule_counts(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path)
    result = _result(model)
    page = _page(model)
    details = next(
        iter(
            render_architecture_details(
                result,
                canonical_report_bytes(model),
                repository="One target",
                architecture_href="architecture.json",
            ).values()
        )
    ).decode()
    cards = re.findall(r'<article class="verdict-card".*?</article>', page, re.S)
    assert len(cards) == 4
    for card, status in zip(cards, ("PASS", "FAIL", "UNKNOWN", "NOT CHECKED"), strict=True):
        assert f"</span>{status}</div>" in card
        if status != "NOT CHECKED":
            count = sum(item.status == status for item in result.rule_assessments)
            assert f"<h3>{count} rule{'s' if count != 1 else ''}</h3>" in card
        else:
            assert "Status definition" in card
            assert "which occurred" in card
    assert '<article class="verdict-card"' not in details
    assert f"Whole-run rules: {result.declared_rules}" in details
    assert f"Source observation: {result.observation_complete}" in details
    assert '<a href="architecture.report.html">Architecture overview</a>' in details
    for document in (page, details):
        assert "NOT APPLICABLE" not in document
        assert "atlas-status-key" not in document
        assert "Symbol inventory:" in document


def test_partial_lexical_inventory_keeps_symbols_and_uncertainty(tmp_path):
    model = _sample(tmp_path, extra_files={"sample/inventory.py": "def observed():\n    pass\n"})
    data = _atlas(_page(model))
    module = next(item for item in data["modules"] if item["name"] == "sample.inventory")
    assert module["symbols"] == 1
    assert module["symbol_coverage"]
    assert any(item["status"] != "complete" for item in module["symbol_coverage"])
    assert not any(question["kind"] == "heavy" for question in data["questions"])


def test_ambiguous_and_unowned_assignments_remain_distinct(tmp_path):
    data = _atlas(_page(_sample(tmp_path, ambiguous=True)))
    level = next(item for item in data["levels"] if item["parent_id"] is None)
    names = {item["id"]: item["name"] for item in data["modules"]}
    ambiguous = next(item for item in level["modules"] if names[item["id"]] == "sample.core")
    assert ambiguous["component_id"] is None
    assert ambiguous["candidate_ids"] == ["core", "overlap"]
    assert ambiguous["ownership_status"] == "UNKNOWN"
    unowned = next(item for item in level["modules"] if names[item["id"]] == "sample.unowned")
    assert unowned["candidate_ids"] == [] and unowned["ownership_status"] == "UNKNOWN"


def test_atlas_findings_and_balances_match_core_by_level(tmp_path):
    model = _sample(tmp_path)
    result = _result(model)
    data = _atlas(_page(model))
    records = {item.id: item for item in model.records("violations") or ()}
    finding_id = {index: item["id"] for index, item in enumerate(data["findings"])}
    evidence = {item.id: item for item in model.evidence}
    assert {finding_id[index] for index in data["levels"][0]["finding_ids"]} == set(records)
    for component in result.architecture_projection.components:
        level = next(item for item in data["levels"] if item["parent_id"] == component.id)
        selected = select_violations(
            model, ReportFilter(only_violations=True, component=component.scope)
        )
        assert {finding_id[index] for index in level["finding_ids"]} == {
            item.id for item in selected
        }
    for entry in data["findings"]:
        record = records[entry["id"]]
        assert entry["rule_ids"] == list(record.rule_ids)
        assert entry["kind"] == record.kind
        assert entry["title"] == record.title
        assert (
            data["reference_ids"][entry["remedy_ref"]]
            == result.architecture_projection.violation_remedy
        )
        source = min(
            (evidence[item] for item in record.evidence_ids if item in evidence),
            key=lambda item: (item.file, item.line),
        )
        assert (entry["path"], entry["line"]) == (source.file, source.line)
    for expected in result.architecture_projection.levels:
        actual = next(item for item in data["levels"] if item["parent_id"] == expected.parent_id)
        assert actual["balance"] == {
            "declared": expected.declared,
            "used": expected.used,
            "allowed_unused": expected.unused,
            "undeclared": expected.undeclared,
        }
        assert len(actual["deviation_ids"]) == (expected.unused or 0) + (expected.undeclared or 0)
    projection_level_ids = {item.parent_id for item in result.architecture_projection.levels}
    for component in result.architecture_projection.components:
        if component.id not in projection_level_ids:
            leaf = next(item for item in data["levels"] if item["parent_id"] == component.id)
            assert leaf["balance"] == {
                "declared": 0,
                "used": 0,
                "allowed_unused": 0,
                "undeclared": 0,
            }
    assert data["balance"] == {
        field: sum(getattr(level, attr) or 0 for level in result.architecture_projection.levels)
        for field, attr in (
            ("declared", "declared"),
            ("used", "used"),
            ("allowed_unused", "unused"),
            ("undeclared", "undeclared"),
        )
    }


def test_atlas_keeps_every_rule_of_a_finding_without_inflating_totals(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    model = _sample(
        tmp_path,
        extra_rules=[
            {
                "id": "second",
                "kind": "complete_requires",
                "rationale": "Check the same boundary independently.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    )
    original = model.records("violations")[0]
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(record, rule_ids=("dependencies", "second"))
                    if record.id == original.id
                    else record
                    for record in section.records
                ),
            )
            for section in model.sections
        ),
    )
    model = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(model))))
    html = _page(model)
    atlas = _atlas(html)
    entry = next(item for item in atlas["findings"] if item["id"] == original.id)
    assert entry["rule_ids"] == ["dependencies", "second"]
    records = model.records("violations")
    assert len(atlas["findings"]) == len(records)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_health_check(page)
        panel = page.locator(".atlas-findings")
        assert panel.locator(":scope > summary").inner_text() == f"Findings · {len(records)}"
        for rule in original.rule_ids + ("second",):
            count = sum(rule in record.rule_ids for record in records)
            group = panel.locator(f'[id="atlas-rule-{rule}"]')
            assert not group.evaluate("node => node.open")
            group.locator("summary").click()
            assert group.locator("li").count() == count
            finding = group.locator(f'[id^="atlas-finding-{original.id}-"]')
            assert finding.count() == 1
            assert finding.locator("strong").inner_text() == original.title
        identities = panel.locator("[id]").evaluate_all("nodes => nodes.map(node => node.id)")
        assert len(identities) == len(set(identities))
    finally:
        browser.close()
        playwright.stop()


def test_atlas_unavailable_projection_does_not_report_zero_balances(tmp_path):
    model = _sample(tmp_path)
    assert architecture_report(model).target is not None
    sections = tuple(
        replace(
            section,
            records=tuple(
                record
                for record in section.records
                if record.kind not in {"architecture_target", "uml_target"}
            ),
        )
        if section.name == "declarations" and section.records is not None
        else section
        for section in model.sections
    )
    unavailable = replace(model, sections=sections)
    result = _result(unavailable)
    assert result.architecture_projection is not None
    assert result.architecture_projection.levels == ()

    data = _atlas(_page(unavailable))
    assert data["levels"]
    for level in data["levels"]:
        assert level["balance"] == {
            "declared": None,
            "used": None,
            "allowed_unused": None,
            "undeclared": None,
        }
    assert data["balance"] == {
        "declared": None,
        "used": None,
        "allowed_unused": None,
        "undeclared": None,
    }


def test_allowed_dependency_without_import_is_a_core_sourced_unused_deviation(tmp_path):
    from test_target_graph import _repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation

    root, config = _repository(tmp_path)
    contract = json.loads((root / config.contract).read_bytes())
    contract["components"][0]["public"] = ["sample.core:Service"]
    peer = dict(contract["components"][0])
    peer.update(id="peer", label="peer", packages=["sample.peer"], namespace="sample.peer")
    contract["components"].append(peer)
    contract["rules"] = [
        {
            "id": "peer-core-permission",
            "kind": "allowed_dependency",
            "source": "sample.peer",
            "target": "sample.core",
            "rationale": "Allow the peer to use the core interface.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    (root / config.contract).write_text(json.dumps(contract))
    (root / "sample/peer.py").write_text("value = 1\n")
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    data = _atlas(_page(model))
    balance = next(level["balance"] for level in data["levels"] if level["parent_id"] is None)
    assert balance == {"declared": 1, "used": 0, "allowed_unused": 1, "undeclared": 0}
    deviation = next(item for item in data["deviations"] if item["kind"] == "allowed_unused")
    assert (deviation["source_id"], deviation["target_id"]) == ("peer", "core")
    core = next(item for item in data["components"] if item["id"] == "core")
    assert [data["reference_ids"][index] for index in core["public"]] == ["sample.core:Service"]


@pytest.mark.parametrize("only", [None, "architecture"])
def test_rerun_cleans_only_obsolete_generated_detail_pages(tmp_path, capsys, monkeypatch, only):
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "published" / "architecture.json"
    output.parent.mkdir()
    obsolete = (
        output.parent / "architecture.detail-component-0123456789abcdef.html",
        output.parent / "architecture.detail-unknown.html",
    )
    preserved = (
        output.parent / "architecture.detail-custom.html",
        output.parent / "other.detail-component-0123456789abcdef.html",
    )
    for path in (*obsolete, *preserved):
        path.write_text("old artifact")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    arguments = ["report", "--root", str(root), "--output", str(output)]
    if only is not None:
        arguments.extend(("--only", only))
    assert main(arguments) == 0
    capsys.readouterr()
    if only is None:
        assert not any(path.exists() for path in obsolete)
        assert (output.parent / "architecture.detail.html").exists()
    else:
        assert all(path.exists() for path in obsolete)
        assert not (output.parent / "architecture.detail.html").exists()
    assert all(path.read_text() == "old artifact" for path in preserved)


def test_component_detail_links_are_relative_and_keep_shared_uml(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    encoded = canonical_report_bytes(model)
    result = _result(model)
    details = render_architecture_details(
        result, encoded, repository="One target", architecture_href="architecture.json"
    )
    data = _atlas(_page(model))
    assert set(details) == {"architecture.detail.html"}
    for component in data["components"]:
        assert component["id"]
        assert data["detail_page"] in details
        page = details["architecture.detail.html"].decode()
        assert 'id="flow-data"' in page
        assert "architecture.json" in page
        assert "fetch(" not in page
        assert "default-src 'none'" in page


@pytest.mark.parametrize("width", [1440, 390])
def test_atlas_closed_details_releases_diagram_space(tmp_path, width):
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(
        api, _page(_sample(tmp_path)), width=width, height=900, errors=errors
    )
    try:
        _open_details(page)
        opened = page.locator(".flow-canvas").bounding_box()
        page.locator(".flow-details-toggle").click()
        api.expect(page.locator(".flow-inspector")).to_be_hidden()
        layout = page.locator(".flow-layout").bounding_box()
        closed = page.locator(".flow-canvas").bounding_box()
        assert closed["width"] >= layout["width"] - (62 if width == 1440 else 2)
        if width == 1440:
            assert closed["width"] > opened["width"] + 200
        else:
            assert closed["height"] > opened["height"] + 100
        page.locator(".flow-details-toggle").click()
        api.expect(page.locator(".flow-inspector")).to_be_visible()
        reopened = page.locator(".flow-canvas").bounding_box()
        assert reopened["width"] == pytest.approx(opened["width"], abs=2)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width", [1440, 400])
def test_atlas_browser_keeps_positions_and_unknown_cells_across_lenses(tmp_path, width):
    api = pytest.importorskip("playwright.sync_api")
    page_html = _page(_sample(tmp_path))
    errors = []
    playwright, browser, page = _browser_page(api, page_html, width=width, errors=errors)
    try:
        assert page.evaluate(
            "[typeof window.module, typeof window.exports, typeof window.define, typeof window.ELK]"
        ) == ["undefined", "undefined", "undefined", "function"]
        _open_health_check(page)
        card = page.locator('.flow-nodes [data-label="core"]')
        assert card.count() == 1
        if width == 1440:
            canvas = page.locator(".flow-canvas").bounding_box()
            cards = page.locator(".flow-nodes .card").evaluate_all("""nodes => nodes.map(node => {
              const box = node.getBoundingClientRect();
              return {left: box.left, right: box.right, top: box.top, bottom: box.bottom};
            })""")
            assert all(
                card["left"] >= canvas["x"]
                and card["right"] <= canvas["x"] + canvas["width"]
                and card["top"] >= canvas["y"]
                and card["bottom"] <= canvas["y"] + canvas["height"]
                for card in cards
            )
        position = card.get_attribute("transform")
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert card.get_attribute("transform") == position
        page.locator('.flow-matrix [data-cell="0"]').click()
        assert "Permission: UNKNOWN" in page.locator(".flow-inspector-content").inner_text()
        assert "FAIL" in page.locator(".flow-inspector-content").inner_text()
        page.get_by_role("button", name="Target", exact=True).click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "observed import cell" not in details.lower()
        assert "evidence ids" not in details.lower()
        page.get_by_role("button", name="As-Is", exact=True).click()
        _open_health_check(page)
        page.locator(".matrix-label[data-module]").first.click()
        assert "observed module" in page.locator(".flow-inspector-content").inner_text().lower()
        page.get_by_role("button", name="Target", exact=True).click()
        assert "observed module" not in page.locator(".flow-inspector-content").inner_text().lower()
        dark = page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
        page.get_by_role(
            "button", name="Switch to light theme" if dark else "Switch to dark theme"
        ).click()
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == (
            "rgb(255, 255, 255)" if dark else "rgb(0, 0, 0)"
        )
        page.get_by_role(
            "button", name="Switch to dark theme" if dark else "Switch to light theme"
        ).click()
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == (
            "rgb(0, 0, 0)" if dark else "rgb(255, 255, 255)"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_ignores_stale_layout_and_retries_rejected_layout(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html = _page(_sample(tmp_path, uml=True))
    atlas = _atlas(html)
    declared_ids = sorted(module["id"] for module in atlas["declared_modules"])
    level = next(level for level in atlas["levels"] if level["parent_id"] is None)
    observed_ids = sorted(module["id"] for module in level["modules"])
    hook = """window.__originalAtlasLayout = ELK.prototype.layout;
window.__atlasLayoutCalls = 0;
ELK.prototype.layout = function(graph) {
  const call = ++window.__atlasLayoutCalls;
  if (call === 2) return new Promise(resolve => {
    window.__oldAtlasSettled = false;
    window.__resolveOldAtlasLayout = async () => {
      resolve(await window.__originalAtlasLayout.call(this, graph));
      window.__oldAtlasSettled = true;
    };
  });
  if (call === 4) return new Promise((resolve, reject) => {
    window.__rejectAtlasLayout = () => reject(new Error("deliberate Atlas layout failure"));
  });
  return window.__originalAtlasLayout.call(this, graph);
};"""
    html = _intercept_elk_publication(html, hook)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        assert page.evaluate("window.__elkHookInstalled === true")
        _wait_for_layout(page)
        page.locator('.atlas-content-choice [data-content="modules"]').click()
        page.wait_for_function("() => typeof window.__resolveOldAtlasLayout === 'function'")
        page.get_by_role("button", name="Target", exact=True).click()
        _wait_for_layout(page)
        assert (
            page.locator('.flow-nodes [data-uml-kind="module"]').evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId).sort()"
            )
            == declared_ids
        )

        def scene():
            return page.evaluate("""() => ({
              nodes: [...document.querySelectorAll('.flow-nodes [data-uml-id]')]
                .map(node => [node.dataset.umlId, node.getAttribute('transform')]),
              edges: [...document.querySelectorAll('.flow-edges > g[data-uml-source]')]
                .map(edge => [edge.dataset.umlId, edge.querySelector('.line').getAttribute('d')])
            })""")

        target = scene()
        page.evaluate("window.__resolveOldAtlasLayout()")
        page.wait_for_function("() => window.__oldAtlasSettled === true")
        assert page.locator('[data-flow-view="target"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#flow").get_attribute("data-content") == "modules"
        assert scene() == target

        page.get_by_role("button", name="Diff", exact=True).click()
        page.wait_for_function("() => typeof window.__rejectAtlasLayout === 'function'")
        page.evaluate("window.__rejectAtlasLayout()")
        page.get_by_text("Architecture layout unavailable", exact=True).wait_for()
        assert page.locator("#flow").get_attribute("data-layout-state") == "error"
        assert not page.locator(".flow-canvas").is_visible()
        page.get_by_role("button", name="Diff", exact=True).click()
        _wait_for_layout(page)
        assert page.locator('[data-flow-view="diff"]').get_attribute("aria-pressed") == "true"
        assert page.locator(".flow-canvas").is_visible()
        assert sorted(identity for identity, _ in scene()["nodes"]) == observed_ids
        assert sorted(identity for identity, _ in scene()["edges"]) == [
            f"module-cell:{index}" for index in sorted(level["cells"])
        ]
        assert page.evaluate("window.__atlasLayoutCalls") == 5
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_component_layout_keeps_union_geometry_and_active_edges(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        other_component=True,
        extra_files={"sample/other.py": "import sample.core\n"},
    )
    html = _page(model)
    match = re.search(
        r'(<script id="flow-data" type="application/json">)(.*?)(</script>)', html, re.S
    )
    assert match is not None
    data = json.loads(match.group(2))
    atlas = data["atlas"]
    components = atlas["components"]
    by_id = {component["id"]: component for component in components}
    peer_index = next(
        index for index, component in enumerate(components) if component["id"] == "peer"
    )

    peer_edge_id = by_id["peer"]["requires"][0]["id"]
    parallel = dict(by_id["peer"]["requires"][0], id="parallel-peer-core")
    by_id["peer"]["requires"].append(parallel)
    cycle = dict(by_id["peer"]["requires"][0], id="cycle-core-peer", target_id=peer_index)
    by_id["core"]["requires"].append(cycle)
    html = (
        html[: match.start()]
        + match.group(1)
        + json.dumps(data, separators=(",", ":"))
        + match.group(3)
        + html[match.end() :]
    )

    api = pytest.importorskip("playwright.sync_api")
    errors = []
    path = tmp_path / "architecture.report.html"
    path.write_text(html)
    playwright, browser, page = _browser_page(api, html, width=390, errors=errors)
    try:
        page.goto(path.as_uri())
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=component]').length === 3"
        )
        assert page.evaluate("""() => {
          const canvas = document.querySelector('.flow-canvas').getBoundingClientRect();
          return [...document.querySelectorAll('.flow-nodes [data-uml-kind=component] .card')]
            .some(card => {
              const box = card.getBoundingClientRect();
              return box.left >= canvas.left && box.right <= canvas.right
                && box.top >= canvas.top && box.bottom <= canvas.bottom;
            });
        }"""), "the initial mobile component view must show a complete card"
        page.locator('[data-flow-view="diagram"]').click()
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=component]').length === 3"
        )

        def scene() -> dict:
            return page.evaluate("""() => ({
            nodes: [...document.querySelectorAll('.flow-nodes [data-uml-kind="component"]')]
                .map(node => {
                  const box = node.getBoundingClientRect();
                  const card = node.querySelector('.card');
                  return {id: node.dataset.umlId, transform: node.getAttribute('transform'),
                    x: box.x, y: box.y, right: box.right, bottom: box.bottom,
                    width: card.getAttribute('width'), height: card.getAttribute('height')};
                }),
              edges: [...document.querySelectorAll('.flow-edges > g[data-uml-source]')]
                .map(edge => ({id: edge.dataset.umlId, source: edge.dataset.umlSource,
                  target: edge.dataset.umlTarget, classes: [...edge.classList],
                  tooltip: edge.querySelector('.line title')?.textContent,
                  labels: [...edge.querySelectorAll('.atlas-edge-label')]
                    .map(label => label.textContent),
                  path: edge.querySelector('.line').getAttribute('d')})),
              labels: [...document.querySelectorAll('.atlas-edge-label')].map(label => {
                const box = label.getBoundingClientRect();
                return {text: label.textContent, x: box.x, y: box.y,
                  right: box.right, bottom: box.bottom};
              })
            })""")

        target_edge_ids = {"cycle-core-peer", "parallel-peer-core", peer_edge_id}
        views = {}
        for lens in ("As-Is", "Target", "Diff"):
            page.get_by_role("button", name=lens, exact=True).click()
            expected_count = 3 if lens == "Target" else 2
            page.wait_for_function(
                "count => document.querySelectorAll('.flow-edges > g[data-uml-source]').length "
                "=== count",
                arg=expected_count,
            )
            views[lens] = scene()

        positions = {
            lens: {node["id"]: node["transform"] for node in view["nodes"]}
            for lens, view in views.items()
        }
        dimensions = {
            lens: {node["id"]: (node["width"], node["height"]) for node in view["nodes"]}
            for lens, view in views.items()
        }
        assert positions["As-Is"] == positions["Target"] == positions["Diff"]
        assert dimensions["As-Is"] == dimensions["Target"] == dimensions["Diff"]
        assert len({positions["Target"]["core"], positions["Target"]["peer"]}) == 2

        root_level = next(level for level in atlas["levels"] if level["parent_id"] is None)
        expected_observed = {
            f"observed:{edge['source_id']}>{edge['target_id']}": edge
            for edge in root_level["edges"]
        }
        deviations = {
            (item["source_id"], item["target_id"]): item["kind"] for item in atlas["deviations"]
        }
        state_for_status = {"FAIL": "violation", "UNKNOWN": "undecided"}
        expected_observed_labels = {
            edge_id: f"{edge['import_sites']} import" + ("s" if edge["import_sites"] != 1 else "")
            for edge_id, edge in expected_observed.items()
        }
        for lens in ("As-Is", "Diff"):
            edges = {edge["id"]: edge for edge in views[lens]["edges"]}
            assert set(edges) == set(expected_observed)
            for edge_id, source_edge in expected_observed.items():
                pair = (source_edge["source_id"], source_edge["target_id"])
                state = (
                    "violation"
                    if lens == "Diff" and deviations.get(pair) == "undeclared"
                    else state_for_status.get(source_edge["status"], "observed")
                )
                assert state in edges[edge_id]["classes"]
                assert edges[edge_id]["labels"] == [expected_observed_labels[edge_id]]
        observed = {(edge["source"], edge["target"]) for edge in views["As-Is"]["edges"]}
        declared = {(edge["source"], edge["target"]) for edge in views["Target"]["edges"]}
        assert ("other", "core") in observed
        assert ("other", "core") not in declared
        assert ("core", "peer") in declared
        assert {edge["id"] for edge in views["Target"]["edges"]} == target_edge_ids
        target_declarations = {
            edge["id"]: edge for component in components for edge in component["requires"]
        }
        target_edges = {edge["id"]: edge for edge in views["Target"]["edges"]}
        for edge_id in target_edge_ids:
            declaration = target_declarations[edge_id]
            rationale = atlas["reference_ids"][declaration["rationale_ref"]]
            assert "declared" in target_edges[edge_id]["classes"]
            assert target_edges[edge_id]["labels"] == ["requires"]
            assert rationale in target_edges[edge_id]["tooltip"]
        assert (
            sum(
                edge["source"] == "peer" and edge["target"] == "core"
                for edge in views["Target"]["edges"]
            )
            == 2
        )
        assert len(views["Target"]["labels"]) == len(views["Target"]["edges"])
        assert len({edge["path"] for edge in views["Target"]["edges"]}) == len(
            views["Target"]["edges"]
        )
        assert "violation" in next(
            edge["classes"]
            for edge in views["Diff"]["edges"]
            if edge["id"] == "observed:other>core"
        )
        for view in views.values():
            for label in view["labels"]:
                for node in view["nodes"]:
                    assert (
                        label["right"] <= node["x"] + 1
                        or node["right"] <= label["x"] + 1
                        or label["bottom"] <= node["y"] + 1
                        or node["bottom"] <= label["y"] + 1
                    ), (label, node)
            for left_index, left in enumerate(view["labels"]):
                for right in view["labels"][left_index + 1 :]:
                    assert (
                        left["right"] <= right["x"] + 1
                        or right["right"] <= left["x"] + 1
                        or left["bottom"] <= right["y"] + 1
                        or right["bottom"] <= left["y"] + 1
                    ), (left, right)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_diff_balance_links_select_the_deviation_source(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html = _page(_sample(tmp_path))
    path = tmp_path / "architecture.report.html"
    path.write_text(html)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_health_check(page)
        page.goto(path.as_uri())
        _open_health_check(page)
        page.get_by_role("button", name="Diff", exact=True).click()
        balance = page.locator(".atlas-balance")
        assert (
            "Whole system: 0 declared · 1 used · 0 allowed but unused · 1 undeclared"
            in balance.inner_text()
        )
        link = balance.get_by_role("link", name="Undeclared · peer → core")
        assert "selected=peer" in link.get_attribute("href")
        link.click()
        assert (
            page.locator('.flow-nodes [data-uml-id="peer"]').get_attribute("aria-pressed") == "true"
        )
        assert page.locator(".flow-edges .atlas-undeclared").count() == 1
        assert "red: undeclared" in page.locator(".flow-legend").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "theme, fill", [("dark", "rgb(255, 107, 107)"), ("light", "rgb(185, 28, 28)")]
)
def test_recorded_findings_are_visible_in_each_atlas_lens(tmp_path, theme, fill):
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, _page(_sample(tmp_path)), errors=errors)
    try:
        _open_health_check(page)
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
        atlas = json.loads(page.locator("#flow-data").text_content())["atlas"]
        _open_details(page)
        for lens in ("As-Is", "Target", "Diff"):
            page.get_by_role("button", name=lens, exact=True).click()
            component = atlas["components"][0]
            page.locator(f'.flow-nodes [data-uml-id="{component["id"]}"]').press("Space")
            panel = page.locator(".atlas-findings")
            assert panel.is_visible()
            assert "Findings · 2" in panel.inner_text()
            assert "dependencies" in panel.inner_text()
            groups = panel.locator(".atlas-finding-group")
            assert groups.count() == 1 and not groups.first.evaluate("node => node.open")
            groups.first.locator("summary").click()
            assert page.locator(".atlas-findings li strong").count() == 2
            root_level = next(item for item in atlas["levels"] if item["parent_id"] is None)
            grouped_findings = {}
            for index in root_level["finding_ids"]:
                finding = atlas["findings"][index]
                for rule in finding["rule_ids"]:
                    grouped_findings.setdefault((rule, finding["kind"]), []).append(finding)
            shared_remedies = []
            individual_remedies = []
            for entries in grouped_findings.values():
                remedies = [
                    atlas["reference_ids"][finding["remedy_ref"]]
                    if finding.get("remedy_ref") is not None
                    else None
                    for finding in entries
                ]
                shared = (
                    remedies[0]
                    if len(remedies) > 1 and remedies[0] and all(r == remedies[0] for r in remedies)
                    else None
                )
                if shared:
                    shared_remedies.append(shared)
                individual_remedies.extend(
                    remedy for remedy in remedies if remedy and remedy != shared
                )
            assert sorted(page.locator(".atlas-shared-remedy").all_text_contents()) == sorted(
                shared_remedies
            )
            assert sorted(page.locator(".atlas-finding-remedy").all_text_contents()) == sorted(
                individual_remedies
            )
            rules = page.locator(".flow-inspector-content .atlas-rule-assessments")
            if lens == "Target":
                assert not rules.count()
                assert not page.locator(".flow-inspector-content .atlas-evidence").count()
                assert not page.locator(".flow-inspector-content .atlas-scoped-findings").count()
            else:
                assert (
                    f"Rules · whole run {atlas['declared_rules']}"
                    in rules.locator("summary").inner_text()
                )
                rules.locator("summary").click()
                assert "Whole-run rule assessments" in rules.inner_text()
                assert page.locator(".flow-inspector-content .atlas-evidence").is_visible()
                component_level = next(
                    item for item in atlas["levels"] if item["parent_id"] == component["id"]
                )
                expected_findings = len(component_level["finding_ids"])
                assert (
                    f"{expected_findings} recorded failing finding"
                    in page.locator(".flow-inspector-content .atlas-scoped-findings").inner_text()
                )
            for component in atlas["components"]:
                level = next(
                    item for item in atlas["levels"] if item["parent_id"] == component["id"]
                )
                finding_count = len(level["finding_ids"])
                card = page.locator(f'.flow-nodes [data-uml-id="{component["id"]}"]')
                chip = card.locator(".atlas-finding-chip")
                assert chip.count() == (1 if finding_count and lens != "Target" else 0)
                if finding_count and lens != "Target":
                    assert chip.evaluate("node => getComputedStyle(node).fill") == fill
                    assert (
                        chip.text_content()
                        == f"{finding_count} finding{'s' if finding_count != 1 else ''} inside"
                    )
            assert page.get_by_role("link", name="sample/peer.py:1").count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_finding_links_open_collapsed_groups_without_trapping_navigation(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html = _page(_sample(tmp_path))
    report = tmp_path / "report.html"
    report.write_text(html)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.goto(report.as_uri() + "#atlas-rule-dependencies")
        group = page.locator("#atlas-rule-dependencies")
        group.locator("li").first.wait_for(state="visible")
        page.get_by_role("button", name="Target", exact=True).click()
        assert not page.locator("#atlas-rule-dependencies").evaluate("node => node.open")
        page.evaluate("location.hash = '#%invalid'")
        page.evaluate("location.hash = '#atlas-rule-dependencies'")
        group.locator("li").first.wait_for(state="visible")
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_findings_show_only_distinct_nested_annotation_without_deduplication(tmp_path):
    model = _sample(tmp_path)
    violations = model.records("violations") or ()
    assert len(violations) >= 2
    replacement = {}
    for index, record in enumerate(violations[:2]):
        values = dict(record.data.entries)
        values["annotation"] = "Base"
        values["nested_annotation"] = "dict[str, float]" if index == 0 else "Base"
        replacement[record.id] = replace(
            record, data=replace(record.data, entries=tuple(values.items()))
        )
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(replacement.get(record.id, record) for record in section.records),
            )
            for section in model.sections
        ),
    )
    findings = _atlas(_page(model))["findings"]
    assert len(findings) == len(violations)
    by_id = {finding["id"]: finding for finding in findings}
    assert by_id[violations[0].id]["nested_annotation"] == "dict[str, float]"
    assert "nested_annotation" not in by_id[violations[1].id]


def test_target_content_is_independent_of_observed_evidence(tmp_path):
    from archkeel.check.ports import ScanConfig

    api = pytest.importorskip("playwright.sync_api")
    root = tmp_path / "target-purity"
    _sample(
        root,
        permitted=True,
        other_component=True,
        uml=True,
        extra_files={"sample/other.py": "VALUE = 1\n"},
    )
    repository = root / "repo"
    # The unowned helper module prevents a fully decided starting point.
    (repository / "sample/unowned.py").unlink()
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    contract_value = json.loads((repository / config.contract).read_bytes())
    contract_value["declarations"]["uml"]["relationships"] = [
        {
            "id": "peer-imports-core",
            "kind": "imports",
            "source_id": "peer-module",
            "target_id": "core-module",
            "provenance": ["docs/target.md"],
        }
    ]
    (repository / config.contract).write_text(json.dumps(contract_value))
    contract_value["components"][1]["public"] = ["sample.peer:control"]
    peer_source = repository / "sample/peer.py"
    peer_source.write_text(peer_source.read_text() + "\ndef control() -> int: return 1\n")
    contract_value["rules"].append(
        {
            "id": "PURE-BOUNDARY",
            "kind": "boundary_types",
            "source": "sample.peer",
            "rationale": "Native result stays an explicit target decision.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
            "allowed_positions": [
                {
                    "qualified_name": "sample.peer.unused",
                    "position": "return",
                    "annotation": "object",
                }
            ],
        }
    )
    (repository / config.contract).write_text(json.dumps(contract_value))
    contract = (repository / config.contract).read_bytes()

    def report():
        result, encoded = run_report(repository, config=config, analyzer=observe)
        assert encoded is not None
        return result, render_architecture_html(
            result, encoded, repository="One target", architecture_href="architecture.json"
        ).decode()

    observations = [report()]
    long_source = repository / "sample/peer/deep/remove_none_or_empty_element_converter.py"
    long_source.parent.mkdir(parents=True)
    long_source.write_text("import sample.other\n")
    observations.append(report())
    long_source.unlink()
    (repository / "sample/__init__.py").write_text("class core:\n    pass\n")
    observations.append(report())
    assert (repository / config.contract).read_bytes() == contract
    assert [result.declared_rules for result, _ in observations] == ["PASS", "FAIL", "UNKNOWN"]
    permission_rows = [
        json.loads(
            re.search(
                r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S
            ).group(1)
        )["boundary_permissions"]["declared"]
        for _, html in observations
    ]
    assert permission_rows[0] == permission_rows[1] == permission_rows[2]
    assert permission_rows[0]
    assert permission_rows[0][0]["entity_ids"] == ["peer-module"]
    atlases = [_atlas(html) for _, html in observations]
    root_levels = [
        next(level for level in atlas["levels"] if level["parent_id"] is None) for atlas in atlases
    ]
    assert len(atlases[0]["findings"]) < len(atlases[1]["findings"])
    assert len(root_levels[0]["deviation_ids"]) < len(root_levels[1]["deviation_ids"])

    target_views = []
    errors = []
    for _, html in observations:
        playwright, browser, page = _browser_page(api, html, errors=errors)
        try:
            atlas = json.loads(page.locator("#flow-data").text_content())["atlas"]
            peer = next(item for item in atlas["components"] if item["id"] == "peer")
            module = next(
                item for item in atlas["declared_modules"] if item["component_id"] == "peer"
            )
            page.get_by_role("button", name="Target", exact=True).click()
            target_component_ids = set(root_levels[0]["component_ids"])
            target_edge_count = sum(
                1
                for component in atlas["components"]
                if component["id"] in target_component_ids
                for edge in component["requires"]
                if atlas["components"][edge["target_id"]]["id"] in target_component_ids
            )
            page.wait_for_function(
                "count => { const edges = [...document.querySelectorAll("
                "'.flow-edges > g[data-uml-source]')]; return edges.length === count "
                "&& edges.every(edge => edge.classList.contains('declared')); }",
                arg=target_edge_count,
            )
            page.evaluate(
                """async () => {
                  await document.fonts.ready;
                  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                }"""
            )
            root_sheet = page.locator(".flow-inspector-content").inner_text()
            assert "Recorded checks" not in root_sheet
            assert "Rules · whole run" not in root_sheet
            assert "Source observation:" not in root_sheet
            cards = page.locator(".flow-nodes > g").evaluate_all("""nodes => nodes.map(node => ({
              id: node.dataset.umlId,
              label: node.dataset.label,
              width: node.querySelector('.card')?.getAttribute('width'),
              height: node.querySelector('.card')?.getAttribute('height'),
              text: [...node.querySelectorAll('text')].map(item => item.textContent).join(' | '),
              findingChips: node.querySelectorAll('.atlas-finding-chip').length,
              deviationChips: node.querySelectorAll('.atlas-deviation-chip').length
            }))""")
            assert all(item["findingChips"] == item["deviationChips"] == 0 for item in cards)
            target_edges = page.locator(".flow-edges > g[data-uml-source]").evaluate_all(
                """edges => edges.map(edge => ({
                  id: edge.dataset.umlId, source: edge.dataset.umlSource,
                  target: edge.dataset.umlTarget, state: edge.getAttribute('class'),
                  labels: [...edge.querySelectorAll('.atlas-edge-label')]
                    .map(label => label.textContent)
                }))"""
            )
            assert all(edge["state"].split()[1] == "declared" for edge in target_edges)
            legend = page.locator(".flow-legend").inner_text()
            assert "observed import sites" not in legend
            assert "declared" in legend.lower()

            page.locator(f'.flow-nodes [data-uml-id="{peer["id"]}"]').click()
            component_sheet = page.locator(".flow-inspector-content").inner_text()
            assert "Recorded checks" not in component_sheet
            assert "Rules · whole run" not in component_sheet
            assert "Source observation:" not in component_sheet
            page.locator("[data-browse-component]").click()
            page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]').click()
            module_sheet = page.locator(".flow-inspector-content").inner_text()
            target_views.append(
                (root_sheet, cards, target_edges, legend, component_sheet, module_sheet)
            )
        finally:
            browser.close()
            playwright.stop()

    assert target_views[0] == target_views[1] == target_views[2]
    assert not errors


def test_long_atlas_paths_fit_mobile_on_initial_view_and_after_resize(tmp_path):
    from archkeel.check.ports import ScanConfig

    api = pytest.importorskip("playwright.sync_api")
    root = tmp_path / "mobile-long-path"
    _sample(root, permitted=False)
    repository = root / "repo"
    long_path = repository / "sample/peer/deep/remove_none_or_empty_element_converter.py"
    long_path.parent.mkdir(parents=True)
    long_path.write_text("import sample.core\n")
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    result, encoded = run_report(repository, config=config, analyzer=observe)
    assert encoded is not None
    html = render_architecture_html(
        result, encoded, repository="One target", architecture_href="architecture.json"
    ).decode()
    errors = []
    playwright, browser, page = _browser_page(api, html, width=375, height=900, errors=errors)
    try:
        _open_details(page)

        def assert_visible_links_fit():
            page.evaluate(
                """async () => {
                  await document.fonts.ready;
                  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                }"""
            )
            geometry = page.evaluate("""() => ({width: innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              links: [...document.querySelectorAll('a')]
                .filter(node => !node.closest('.flow-matrix') && node.checkVisibility())
                .map(node => ({text: node.textContent.trim(),
                  right: node.getBoundingClientRect().right}))
            })""")
            assert geometry["documentWidth"] <= geometry["width"], geometry
            assert all(item["right"] <= geometry["width"] + 0.5 for item in geometry["links"]), (
                geometry
            )

        for lens in ("As-Is", "Target", "Diff"):
            page.get_by_role("button", name=lens, exact=True).click()
            _open_health_check(page)
            panel = page.locator(".atlas-findings")
            for group in panel.locator(".atlas-finding-group").all():
                group.locator("summary").click()
            if lens != "Target":
                modules = page.locator(".atlas-module-list")
                modules.locator("summary").click()
                api.expect(
                    page.locator(".atlas-module-list").get_by_role(
                        "link", name="remove_none_or_empty_element_converter.py"
                    )
                ).to_have_count(1)
            assert_visible_links_fit()
            page.locator(".flow-details-toggle").click()
            assert_visible_links_fit()
            page.locator(".flow-details-toggle").click()

        page.set_viewport_size({"width": 1440, "height": 900})
        page.get_by_role("button", name="Diff", exact=True).click()
        page.set_viewport_size({"width": 375, "height": 900})
        _open_health_check(page)
        page.locator(".atlas-module-list summary").click()
        api.expect(
            page.locator(".atlas-module-list").get_by_role(
                "link", name="remove_none_or_empty_element_converter.py"
            )
        ).to_have_count(1)
        assert_visible_links_fit()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_tour_nested_scope_chips_balances_and_deviation_links(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    repository = _tour_root(tmp_path)
    contract_path = repository / TOUR_CONFIG.contract
    contract = json.loads(contract_path.read_text())
    cli = next(item for item in contract["components"] if item["id"] == "COMP-CLI")
    cli["requires"] = [{"component": "model", "rationale": "Exercise an unused root permission."}]
    contract_path.write_text(json.dumps(contract))
    result, architecture = run_report(repository, config=TOUR_CONFIG, analyzer=observe)
    assert architecture is not None and result.architecture_projection is not None
    html = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    report = tmp_path / "tour.report.html"
    report.write_text(html)
    data_match = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert data_match is not None
    atlas = json.loads(data_match.group(1))["atlas"]
    root_level = next(item for item in atlas["levels"] if item["parent_id"] is None)
    store = next(item for item in atlas["components"] if item["id"] == "COMP-STORE")
    store_level = next(item for item in atlas["levels"] if item["parent_id"] == store["id"])
    core_balances = {item.parent_id: item for item in result.architecture_projection.levels}
    for level in (root_level, store_level):
        native = core_balances[level["parent_id"]]
        core_fields = {
            "declared": native.declared,
            "used": native.used,
            "allowed_unused": native.unused,
            "undeclared": native.undeclared,
        }
        for field, value in core_fields.items():
            assert level["balance"][field] == value
            assert value > 0
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_health_check(page)

        def assert_matrix_labels_do_not_overlap():
            overlaps = page.locator(".flow-matrix svg").evaluate("""svg => {
              const intersects = (a, b) => a.box[0] < b.box[2] && a.box[2] > b.box[0]
                && a.box[1] < b.box[3] && a.box[3] > b.box[1];
              const describe = node => {
                const b = node.getBoundingClientRect();
                return {text: node.firstChild.textContent,
                  box: [b.left, b.top, b.right, b.bottom]};
              };
              const groups = [...svg.querySelectorAll('.matrix-group-label')].map(describe);
              const columns = [...svg.querySelectorAll('.matrix-label[transform]')].map(describe);
              const rows = [...svg.querySelectorAll(
                '.matrix-label:not([transform])')].map(describe);
              const cells = [...svg.querySelectorAll('.matrix-cell')].map(describe);
              const pairs = (left, right) => left.flatMap((a, i) => right
                .filter((b, j) => (left !== right || j > i) && intersects(a, b))
                .map(b => [a, b]));
              return {
                columnRows: pairs(columns, rows),
                columnCells: pairs(columns, cells),
                columnColumns: pairs(columns, columns),
                groupColumns: pairs(groups, columns),
                groupRows: pairs(groups, rows),
                groupGroups: pairs(groups, groups)
              };
            }""")
            assert all(not pairs for pairs in overlaps.values()), overlaps

        for lens in ("As-Is", "Target", "Diff"):
            page.goto(report.as_uri())
            _open_health_check(page)
            page.get_by_role("button", name=lens, exact=True).click()
            rule_links = page.locator('a[href*="#atlas-rule-"]')
            assert (rule_links.count() > 0) == (lens != "Target")
            assert rule_links.evaluate_all("""links => links.every(link =>
              document.getElementById(decodeURIComponent(new URL(link.href).hash.slice(1))))""")
            spacing = page.evaluate("""() => {
              const box = selector => document.querySelector(selector).getBoundingClientRect();
              const summary = box('.atlas-summary');
              const breadcrumb = box('.flow-breadcrumb');
              const canvas = box('.flow-canvas');
              return {summaryTop: summary.top, summaryBottom: summary.bottom,
                breadcrumbBottom: breadcrumb.bottom, canvasTop: canvas.top};
            }""")
            assert spacing["canvasTop"] >= spacing["breadcrumbBottom"] + 8
            if lens == "As-Is":
                assert_matrix_labels_do_not_overlap()
                for axis in ("column", "row"):
                    labels = page.locator(f'.matrix-group-label[data-axis="{axis}"]').evaluate_all(
                        "nodes => nodes.map(node => node.firstChild.textContent)"
                    )
                    range_label = "columns" if axis == "column" else "rows"
                    assert any(f"Root · {range_label} " in label for label in labels)
                    assert any(
                        f"{store['label']} · inside · {range_label} " in label for label in labels
                    )
            for component_id in root_level["component_ids"]:
                level = next(item for item in atlas["levels"] if item["parent_id"] == component_id)
                card = page.locator(f'.flow-nodes [data-uml-id="{component_id}"]')
                chip = card.locator(".atlas-finding-chip")
                expected = len(level["finding_ids"])
                assert chip.count() == (1 if expected and lens != "Target" else 0)
                if expected and lens != "Target":
                    assert (
                        chip.text_content()
                        == f"{expected} finding{'s' if expected != 1 else ''} inside"
                    )
                descendant_ids = {component_id}
                while True:
                    children = {
                        item["id"]
                        for item in atlas["components"]
                        if item.get("parent_id") in descendant_ids
                    }
                    if children <= descendant_ids:
                        break
                    descendant_ids |= children
                expected_deviations = {
                    deviation_id
                    for scoped in atlas["levels"]
                    if scoped["parent_id"] in descendant_ids
                    for deviation_id in scoped["deviation_ids"]
                }
                deviation_chip = card.locator(".atlas-deviation-chip")
                assert deviation_chip.count() == (
                    1 if expected_deviations and lens != "Target" else 0
                )
                if expected_deviations and lens != "Target":
                    expected_label = (
                        f"{len(expected_deviations)} deviation"
                        f"{'s' if len(expected_deviations) != 1 else ''} inside"
                    )
                    assert deviation_chip.text_content() == expected_label
            store_card = page.locator(f'.flow-nodes [data-uml-id="{store["id"]}"]')
            if lens == "Target":
                assert store_card.locator(".atlas-finding-chip, .atlas-deviation-chip").count() == 0
                assert store_card.locator(".card").get_attribute("height") == "178"
            else:
                assert (
                    store_card.locator(".atlas-finding-chip").text_content() == "7 findings inside"
                )
                assert (
                    store_card.locator(".atlas-deviation-chip").text_content()
                    == "3 deviations inside"
                )
                assert store_card.locator(".card").get_attribute("height") == "178"
            store_card.press("Space")
            if lens != "Target":
                scoped_checks = page.locator(".atlas-scoped-findings").inner_text()
                assert "7 recorded failing findings" in scoped_checks
            if lens == "Diff":
                root_balance = page.locator(".atlas-balance").inner_text()
                for field, value in atlas["levels"][0]["balance"].items():
                    label = {"allowed_unused": "allowed but unused"}.get(field, field)
                    assert f"{value} {label}" in root_balance
                root_link = page.get_by_role("link", name="Undeclared · render → store")
                assert root_link.count() == 1
                root_link.click()
                render_component = next(
                    item for item in atlas["components"] if item["label"] == "render"
                )
                root_deviation = next(
                    item
                    for item in atlas["deviations"]
                    if item["level_id"] is None and item["source_id"] == render_component["id"]
                )
                assert parse_qs(urlsplit(page.url).query)["selected"] == [
                    root_deviation["source_id"]
                ]
                page.goto(report.as_uri())
                _open_health_check(page)
                page.get_by_role("button", name="Diff", exact=True).click()
                store_card = page.locator(f'.flow-nodes [data-uml-id="{store["id"]}"]')
                store_card.press("Space")
            if lens != "Diff":
                continue
            browse = page.locator(".flow-inspector-content").get_by_role(
                "button", name=re.compile("Browse .* modules")
            )
            browse.click()
            assert "scope=COMP-STORE" in page.url
            page.locator('.atlas-content-choice [data-content="components"]').click()
            assert (
                "7 recorded failing findings" in page.locator(".atlas-scoped-findings").inner_text()
            )
            page.wait_for_function(
                "count => [...document.querySelectorAll('.flow-nodes > g')]"
                ".filter(node => node.dataset.umlKind === 'component').length === count",
                arg=len(store_level["component_ids"]),
            )
            for component_id in store_level["component_ids"]:
                child_level = next(
                    item for item in atlas["levels"] if item["parent_id"] == component_id
                )
                card = page.locator(f'.flow-nodes [data-uml-id="{component_id}"]')
                child_chip = card.locator(".atlas-finding-chip")
                count = len(child_level["finding_ids"])
                assert child_chip.count() == (1 if count else 0)
            assert_matrix_labels_do_not_overlap()
            if lens == "Diff":
                balance = page.locator(".atlas-balance").inner_text()
                for field, value in store_level["balance"].items():
                    label = {"allowed_unused": "allowed but unused"}.get(field, field)
                    assert f"{value} {label}" in balance
                nested_deviations = [
                    item for item in atlas["deviations"] if item["level_id"] == store["id"]
                ]
                links = page.locator(".atlas-balance a")
                assert links.count() == len(nested_deviations)
                for index, deviation in enumerate(nested_deviations):
                    page.goto(report.as_uri() + f"?scope={store['id']}&view=diff")
                    _open_health_check(page)
                    link = page.locator(".atlas-balance a").nth(index)
                    link.click()
                    assert parse_qs(urlsplit(page.url).query)["selected"] == [
                        deviation["source_id"]
                    ]
                    assert (
                        page.locator(
                            f'.flow-nodes [data-uml-id="{deviation["source_id"]}"]'
                        ).get_attribute("aria-pressed")
                        == "true"
                    )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_rationale_labels_fit_without_overlapping_cards(tmp_path):
    from test_target_graph import _permission_contract, _repository
    from test_uml_evaluation import _model

    api = pytest.importorskip("playwright.sync_api")
    repository, config = _repository(tmp_path)
    (repository / config.contract).write_text(json.dumps(_permission_contract()))
    errors = []
    playwright, browser, page = _browser_page(
        api, _page(_model(repository, config)), width=1440, errors=errors
    )
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        labels = page.locator(".atlas-edge-label").evaluate_all("""nodes => nodes.map(node => {
          const box = node.getBoundingClientRect();
          return {text: node.textContent, box: {
            left: box.left, right: box.right, top: box.top, bottom: box.bottom
          }};
        })""")
        cards = page.locator(".flow-nodes .card").evaluate_all("""nodes => nodes.map(node => {
          const box = node.getBoundingClientRect();
          return {left: box.left, right: box.right, top: box.top, bottom: box.bottom};
        })""")
        canvas = page.locator(".flow-canvas").bounding_box()
        assert labels
        assert all(len(label["text"]) <= 32 for label in labels)
        for index, label in enumerate(labels):
            assert not any(
                label["box"]["left"] < card["right"]
                and label["box"]["right"] > card["left"]
                and label["box"]["top"] < card["bottom"]
                and label["box"]["bottom"] > card["top"]
                for card in cards
            )
            assert not any(
                label["box"]["left"] < other["box"]["right"]
                and label["box"]["right"] > other["box"]["left"]
                and label["box"]["top"] < other["box"]["bottom"]
                and label["box"]["bottom"] > other["box"]["top"]
                for other in labels[index + 1 :]
            )
        assert all(
            card["left"] >= canvas["x"]
            and card["right"] <= canvas["x"] + canvas["width"]
            and card["top"] >= canvas["y"]
            and card["bottom"] <= canvas["y"] + canvas["height"]
            for card in cards
        )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("extra_count", [0, 68])
def test_matrix_reserves_space_for_long_native_module_names(tmp_path, extra_count):
    api = pytest.importorskip("playwright.sync_api")
    name = "sample.a_module_name_that_needs_more_than_the_default_axis_margin"
    files = {f"sample/group_{index}.py": "VALUE = 1\n" for index in range(extra_count)}
    files[name.replace(".", "/") + ".py"] = "VALUE = 1\n"
    model = _sample(tmp_path, extra_files=files)
    playwright, browser, page = _browser_page(api, _page(model))
    try:
        _open_health_check(page)
        column = page.locator(".matrix-label[transform]").filter(has_text=name).bounding_box()
        assert column is not None
        groups = page.locator(".matrix-group-label").evaluate_all(
            "nodes => nodes.map(node => node.getBoundingClientRect().bottom)"
        )
        assert column["y"] > max(groups)
        row = page.locator(".matrix-label:not([transform])").filter(has_text=name).bounding_box()
        matrix = page.locator(".flow-matrix svg").bounding_box()
        assert row is not None and matrix is not None
        assert row["x"] >= matrix["x"]
        columns = page.locator(".matrix-label[transform]").evaluate_all(
            "nodes => nodes.map(node => node.getBoundingClientRect().toJSON())"
        )
        assert all(
            left["right"] <= right["left"]
            for left, right in zip(columns, columns[1:], strict=False)
        )
    finally:
        browser.close()
        playwright.stop()


def test_matrix_renders_each_core_status_and_axis_groups(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html = _page(_sample(tmp_path))
    match = re.search(
        r'(<script id="flow-data" type="application/json">)(.*?)(</script>)', html, re.S
    )
    assert match is not None
    data = json.loads(match.group(2))
    atlas = data["atlas"]
    source = atlas["cells"][0]
    atlas["cells"].extend([[*source[:3], status, *source[4:]] for status in ("PASS", "UNKNOWN")])
    root_level = next(level for level in atlas["levels"] if level["parent_id"] is None)
    root_level["cells"] = [0, 1, 2]
    html = html[: match.start(2)] + json.dumps(data) + html[match.end(2) :]
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_health_check(page)
        assert page.locator(".matrix-cell.fail").count() == 1
        assert page.locator(".matrix-cell.pass").count() == 1
        assert page.locator(".matrix-cell.unknown").count() == 1
        assert page.locator(".matrix-group-label").all_text_contents()
        assert "Core PASS" in page.locator(".flow-explore").inner_text()
        assert "Core FAIL" in page.locator(".flow-explore").inner_text()
        assert "Core UNKNOWN" in page.locator(".flow-explore").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_offline_module_drilldown_reaches_native_classifiers_and_returns(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    source = (
        "from enum import Enum\nLIMIT = 3\n"
        "def transform(value: int) -> int:\n    return value + LIMIT\n"
        "class Client:\n    def run(self, value: int) -> int:\n        return transform(value)\n"
        "class State(Enum):\n    READY = 'ready'\n    FAILED = 'failed'\n"
    )
    model = _sample(tmp_path, extra_files={"sample/core.py": source})
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    result = _result(model)
    for name, content in render_architecture_details(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.locator('.flow-nodes [data-label="core"]').dblclick()
        page.locator('.flow-nodes [data-label="core.py"]').press("Enter")
        assert page.url.startswith("file:") and "module=" in page.url
        for name, kind in (
            ("Client", "class"),
            ("transform", "function"),
            ("State", "enum"),
            ("LIMIT", "constant"),
        ):
            card = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert card.get_attribute("data-uml-kind") == kind
            card.click()
            assert name in page.locator(".flow-inspector-content").inner_text()
        page.locator('.flow-nodes [data-label="State"]').dblclick()
        assert (
            page.locator('.flow-nodes [data-label="READY"]').get_attribute("data-uml-kind")
            == "enum_literal"
        )
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert page.url.startswith(index.as_uri())
        assert "scope=" in page.url
        assert "Architecture map · core" == page.locator("#flow-heading").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_shared_detail_snapshot_retains_cross_component_method_context(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "from sample.peer import Client\nClient.run()\n",
            "sample/peer.py": (
                "class Client:\n    @staticmethod\n    def run() -> int:\n        return 1\n"
            ),
        },
    )
    details = render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    )
    page = details["architecture.detail.html"].decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    snapshot = json.loads(match.group(1))
    observed = snapshot["observed"]
    entities = {item["id"]: item for item in observed["entities"]}
    method = next(item for item in observed["entities"] if item["kind"] == "method")
    classifier = entities[method["parent_id"]]
    assert classifier["kind"] == "class" and classifier["qualified_name"] == "sample.peer.Client"
    assert any(
        edge["kind"] == "calls" and edge["target_id"] == method["id"]
        for edge in observed["relationships"]
    )


def test_shared_detail_snapshot_retains_nested_component_routes(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.render.html import render_architecture_details

    root, config = _nested_repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert any(intent.parent_id for intent in report.target.component_intents)
    details = render_architecture_details(
        _result(model),
        encoded,
        repository="Nested",
        architecture_href="architecture.json",
    )
    page = details["architecture.detail.html"].decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    navigation = json.loads(match.group(1))["navigation"]
    routes = {item["id"]: item for item in navigation["component_path"]}
    for intent in report.target.component_intents:
        assert intent.component_id in routes
        if intent.parent_id:
            assert intent.parent_id in routes
            assert routes[intent.component_id]["parent_id"] == intent.parent_id


def test_module_and_classifier_defaults_show_only_direct_native_children(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": (
                "from enum import Enum\nfrom sample.peer import Base\nLIMIT = 3\n"
                "def transform(value):\n    if value is State:\n        return State.READY\n"
                "    return value + LIMIT\n"
                "class Client(Base):\n    def run(self):\n        return transform(LIMIT)\n"
                "class State(Enum):\n    READY = 'ready'\n    FAILED = 'failed'\n"
            ),
            "sample/peer.py": "class Base:\n    def outside(self):\n        return 1\n",
        },
    )
    graph = architecture_report(model).observed
    module = next(item for item in graph.entities if item.qualified_name == "sample.core")
    pages = render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    )
    for name, content in pages.items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(
        api, pages["architecture.detail.html"].decode(), errors=errors
    )
    try:
        page.goto(
            (tmp_path / "architecture.detail.html").as_uri() + "?component=core&module=" + module.id
        )

        def direct_ids(parent):
            return {
                item.id
                for item in graph.entities
                if item.parent_id == parent and item.presence != "referenced"
            }

        def scene_ids():
            return set(
                page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.umlId)"
                )
            )

        assert scene_ids() == direct_ids(module.id)
        assert page.locator('.flow-nodes [data-outside="true"]').count() == 0
        direct = direct_ids(module.id)
        sites = [
            (edge, target)
            for edge in graph.relationships
            if edge.kind != "owns" and edge.source_id in direct
            for target in ([edge.target_id] if edge.target_id else edge.candidate_ids)
            if target in direct
        ]
        groups = {(edge.kind, edge.source_id, target, edge.resolution) for edge, target in sites}
        assert groups
        assert page.locator(".flow-edges .hit").count() == len(groups)
        reset = page.locator('.flow-legend [data-relationship-kind=""]')
        assert reset.inner_text() == f"Local relationships · {len(groups)}"
        assert f"local relationships at this level · {len(groups)}" in reset.get_attribute("title")
        for kind, source, target, resolution in groups:
            hit = page.locator(
                f'.flow-edges [data-uml-id="{kind}:{source}>{target}:{resolution}"] .hit'
            )
            expected = sum(
                edge.kind == kind
                and edge.source_id == source
                and endpoint == target
                and edge.resolution == resolution
                for edge, endpoint in sites
            )
            assert f"{expected} source or declaration site" in hit.get_attribute("aria-label")
            hit.press("Enter")
            items = (
                page.locator(".flow-inspector-content h3")
                .filter(has_text="Relationship sites")
                .locator("xpath=following-sibling::ul[1]/li")
            )
            assert items.count() == expected
        page.locator(".flow-filters > summary").click()
        assert (
            page.get_by_label("Element kind", exact=True).locator('[value="class"]').inner_text()
            == "class · 1"
        )
        page.get_by_label("Element kind", exact=True).select_option("class")
        _wait_for_layout(page)
        assert scene_ids() == {
            item.id
            for item in graph.entities
            if item.parent_id == module.id and item.kind == "class"
        }
        page.get_by_label("Element kind", exact=True).select_option("")
        _wait_for_layout(page)
        page.locator(".flow-filters > summary").click()
        page.get_by_role("button", name="Legend", exact=True).click()
        page.locator('.flow-legend [data-relationship-kind="inherits"]').click()
        _wait_for_layout(page)
        assert (
            "in context"
            in page.locator('.flow-legend [data-relationship-kind="inherits"]').inner_text()
        )
        assert page.locator('.flow-nodes [data-label="Base"]').count() == 1
        assert page.locator(".flow-edges .hit").count() > 0
        page.locator('.flow-legend [data-relationship-kind=""]').click()
        _wait_for_layout(page)
        page.keyboard.press("Escape")
        assert scene_ids() == direct_ids(module.id)
        for name in ("Client", "State"):
            classifier = next(
                item
                for item in graph.entities
                if item.parent_id == module.id and item.qualified_name.endswith("." + name)
            )
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').click()
            page.locator(".flow-open-selected").click()
            _wait_for_layout(page)
            assert scene_ids() == direct_ids(classifier.id)
            page.locator(".flow-back").click()
            _wait_for_layout(page)
            assert scene_ids() == direct_ids(module.id)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("component_id", ["ROOT", "unassigned"])
def test_unknown_detail_links_keep_deeper_claimed_modules_and_distinct_names(
    tmp_path, component_id
):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.ir.graph_codec import parse_report
    from archkeel.render.html import render_architecture_details

    root, config = _nested_repository(tmp_path)
    raw = json.loads((root / config.contract).read_bytes())
    raw["components"][0]["id"] = component_id
    (root / config.contract).write_text(json.dumps(raw))
    inner = json.loads((root / "inside.json").read_bytes())
    inner["components"][0].update(packages=["sample.future"], namespace="sample.future")
    (root / "inside.json").write_text(json.dumps(inner))
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    data = _atlas(_page(model))
    level = next(item for item in data["levels"] if item["parent_id"] == component_id)
    module = next(item for item in data["modules"] if item["name"] == "sample.core")
    assignment = next(item for item in level["modules"] if item["id"] == module["id"])
    assert assignment["component_id"] is None and assignment["ownership_status"] == "UNKNOWN"
    assert any(module["id"] in item.module_ids for item in architecture_report(model).memberships)
    pages = render_architecture_details(
        _result(model), encoded, repository="One target", architecture_href="architecture.json"
    )
    assert any(item["id"] == component_id for item in data["components"])
    assert data["unassigned_detail_href"].startswith("?component=")
    assert data["detail_page"] in pages
    text = pages["architecture.detail.html"].decode()
    payload = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', text, re.S
    )
    native = json.loads(payload.group(1))
    native.pop("initial_view")
    native.pop("navigation")
    native.pop("boundary_permissions")
    scoped = parse_report(native)
    scoped.validate()
    original = architecture_report(model).observed
    wanted = {
        replace(item, record_ids=())
        for item in original.entities
        if item.id == module["id"] or item.parent_id == module["id"]
    }
    assert wanted <= set(scoped.observed.entities)
    api = pytest.importorskip("playwright.sync_api")
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in pages.items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        _open_health_check(page)
        page.goto(index.as_uri())
        page.locator(f'.flow-nodes [data-uml-id="{component_id}"]').dblclick()
        _open_health_check(page)
        page.locator(".atlas-module-list > summary").click()
        entry = page.locator(".atlas-module-list").get_by_role("link", name="core.py", exact=True)
        entry_href = entry.get_attribute("href")
        assert entry_href is not None
        entry_query = parse_qs(urlsplit(entry_href).query)
        assert entry_query.get("component") == ["unassigned"]
        assert entry_query.get("module") == [module["id"]]
        assert entry_query.get("return_scope") == [component_id]
        entry.click()
        detail_path = urlsplit(entry_href).path

        def at_module_route(url):
            query = parse_qs(urlsplit(str(url)).query)
            return (
                urlsplit(str(url)).path.endswith(detail_path)
                and query.get("module") == [module["id"]]
                and query.get("return_scope") == [component_id]
            )

        page.wait_for_url(at_module_route)
        assert page.locator('.flow-nodes [data-label="Service"]').count() == 1
        page.get_by_role("link", name="Back to architecture map", exact=True).click()

        def at_return_route(url):
            query = parse_qs(urlsplit(str(url)).query)
            return (
                urlsplit(str(url)).path == urlsplit(index.as_uri()).path
                and query.get("scope") == [component_id]
                and query.get("content") == ["components"]
            )

        page.wait_for_url(at_return_route)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def _route_pages(tmp_path, *, local_imports=False, package_empty=False):
    from archkeel.render.html import render_architecture_details

    model = _sample(
        tmp_path,
        core_exact=("sample" if package_empty else "sample.empty",),
        extra_files={
            "sample/__init__.py" if package_empty else "sample/empty.py": "",
            "sample/core.py": (
                (
                    (
                        "import sample\nimport sample\n"
                        if package_empty
                        else "import sample.empty\nimport sample.empty\n"
                    )
                    if local_imports
                    else ""
                )
                + "from enum import Enum\nLIMIT = 3\n"
                "class Client:\n    def run(self):\n        return LIMIT\n"
                "class State(Enum):\n    READY = 'ready'\n"
            ),
        },
    )
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    return index, architecture_report(model).observed


def _cli_route_pages(tmp_path):
    _sample(
        tmp_path,
        uml=True,
        extra_files={
            "sample/core.py": "class Client:\n    def run(self):\n        return 1\n",
            "sample/peer.py": "class Peer:\n    def other(self):\n        return 2\n",
        },
    )
    root = tmp_path / "repo"
    (root / "archkeel.toml").write_text(
        '[scan]\nroots=["sample"]\nnamespace="sample"\ncontract="contract.json"\n'
    )
    output = tmp_path / "architecture.json"
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 0
    detail = output.with_suffix(".detail.html")
    data = json.loads(
        re.search(r'<script id="flow-data"[^>]*>(.*?)</script>', detail.read_text(), re.S)[1]
    )
    ids = {
        item["qualified_name"]: item["id"]
        for item in data["observed"]["entities"]
        if item["kind"] in ("module", "class", "method")
    }
    return output.with_suffix(".report.html"), detail, ids


@pytest.mark.parametrize(
    ("document", "query", "recovery"),
    [
        ("detail", "component=peer&module={core}", "notice"),
        ("detail", "component=missing&module={core}", "notice"),
        ("detail", "component=core&module=missing", "notice"),
        ("detail", "module=missing", "notice"),
        ("detail", "component=core&module={core}&scope={peer_class}", "notice"),
        ("detail", "component=core&module={core}&scope={peer_method}", "back"),
        ("detail", "component=core&origin=declared&scope=peer", "notice"),
        ("detail", "component=core&module=core-module&origin=declared&scope=peer-module", "notice"),
        ("detail", "component=unassigned&module={core}&return_scope=core", "notice"),
        ("atlas", "scope=missing&component=core&module={core}", "notice"),
        ("atlas", "scope=missing&component=core&module={core}", "breadcrumb"),
        ("detail", "component=%70eer&component=core&module={core}&module=missing", "notice"),
    ],
)
def test_rejected_offline_routes_retain_complete_url_until_explicit_recovery(
    tmp_path, document, query, recovery
):
    api = pytest.importorskip("playwright.sync_api")
    index, detail, ids = _cli_route_pages(tmp_path)
    query = query.format(
        core=ids["sample.core"],
        peer_class=ids["sample.peer.Peer"],
        peer_method=ids["sample.peer.Peer.other"],
    )
    requested = (detail if document == "detail" else index).as_uri()
    requested += "?" + query + "&view=diagram&theme=dark&extra=a%2Fb+z&extra=two#retained%2Fhash"
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(requested)
        assert page.locator("#flow-heading").inner_text() == "Requested scope unavailable"
        assert page.locator(".flow-canvas").is_hidden()
        assert page.url == requested
        page.reload()
        assert page.locator("#flow-heading").inner_text() == "Requested scope unavailable"
        assert page.url == requested
        history_length = page.evaluate("history.length")
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert page.locator("#flow-heading").inner_text() == "Requested scope unavailable"
            assert page.url == requested
        page.get_by_role("button", name="Switch to light theme", exact=True).click()
        page.locator(".flow-details-toggle").click()
        page.locator(".flow-details-toggle").click()
        assert page.url == requested
        assert page.evaluate("history.length") == history_length
        if recovery == "breadcrumb":
            page.locator(".flow-breadcrumb button").first.click()
        elif recovery == "back":
            page.locator(".flow-back").click()
        else:
            page.locator(".flow-alternative button").click()
        page.wait_for_function(
            "document.querySelector('#flow-heading').textContent !== 'Requested scope unavailable'"
        )
        recovered = page.url
        assert recovered != requested and "theme=light" in recovered
        assert not urlsplit(recovered).fragment
        page.reload()
        assert page.locator("#flow-heading").inner_text() != "Requested scope unavailable"
        assert page.url == recovered
        page.go_back()
        assert page.locator("#flow-heading").inner_text() == "Requested scope unavailable"
        assert page.url == requested
        assert page.locator("html").get_attribute("data-theme") == "dark"
        page.go_forward()
        assert page.locator("#flow-heading").inner_text() != "Requested scope unavailable"
        assert page.url == recovered
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_cli_offline_valid_routes_still_normalize_and_reload(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, detail, ids = _cli_route_pages(tmp_path)
    queries = [
        "component=core&module=" + ids["sample.core"],
        "component=core&module=" + ids["sample.core"] + "&scope=" + ids["sample.core.Client"],
        "component=core&module=" + ids["sample.core"] + "&scope=" + ids["sample.core.Client.run"],
        "component=core&module=core-module&origin=declared",
        "component=unassigned&module=" + ids["sample.unowned"] + "&return_scope=",
    ]
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        for query in queries:
            page.goto(
                detail.as_uri() + "?" + query + "&view=diagram&theme=light&extra=discard#discard"
            )
            assert page.locator("#flow-heading").inner_text() != "Requested scope unavailable"
            assert "extra=" not in page.url and not urlsplit(page.url).fragment
            normalized = page.url
            page.reload()
            assert page.locator("#flow-heading").inner_text() != "Requested scope unavailable"
            assert page.url == normalized
            assert page.locator("html").get_attribute("data-theme") == "light"
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_offline_atlas_and_uml_share_shell_empty_scope_and_url_theme(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, graph = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?theme=dark")
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.get_by_role("button", name="Switch to light theme", exact=True).click()
        page.locator('.flow-nodes [data-label="empty.py"]').press("Enter")
        page.wait_for_selector(".atlas-heading")
        assert page.locator(".atlas-heading").count() == 1
        assert page.locator(".flow-views [data-flow-view]").count() == 3
        assert page.locator(".theme-toggle").count() == 1
        assert page.locator("html").get_attribute("data-theme") == "light"
        assert "No direct declarations" in page.locator(".flow-alternative").inner_text()
        assert "sample/empty.py" in page.locator(".flow-alternative").inner_text()
        empty = next(item for item in graph.entities if item.qualified_name == "sample.empty")
        assert "module=" + empty.id in page.url
        page.reload()
        assert page.locator("html").get_attribute("data-theme") == "light"
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert "module=" + empty.id in page.url
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "scope=core" in page.url and "theme=light" in page.url
        assert page.locator("#flow-heading").inner_text() == "Architecture map · core"
        page.get_by_role("button", name="Target", exact=True).click()
        assert "No declared subcomponents" in page.locator(".flow-alternative").inner_text()
        module = next(item for item in graph.entities if item.qualified_name == "sample.core")
        page.goto(index.as_uri() + "?scope=core&content=modules&view=diff&theme=light")
        atlas = json.loads(page.locator("#flow-data").text_content())["atlas"]
        assert all(
            module.id not in item["observed_ids"] for item in atlas["module_correspondences"]
        )
        page.locator('.flow-nodes [data-label="core.py"]').dblclick()
        page.wait_for_url("**/architecture.detail.html?*")
        query = parse_qs(urlsplit(page.url).query)
        assert query["module"] == [module.id] and "origin" not in query
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("lens", ["As-Is", "Diff"])
def test_offline_scope_url_history_matches_direct_classifier_and_members(tmp_path, lens):
    api = pytest.importorskip("playwright.sync_api")
    index, graph = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.locator('.flow-nodes [data-label="core.py"]').press("Enter")
        module = next(item for item in graph.entities if item.qualified_name == "sample.core")
        classifier = next(
            item for item in graph.entities if item.qualified_name == "sample.core.Client"
        )
        method = next(
            item for item in graph.entities if item.qualified_name == "sample.core.Client.run"
        )
        page.get_by_role("button", name=lens, exact=True).click()
        _wait_for_layout(page)
        assert page.locator(".flow-canvas").is_visible()
        page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').press("Space")
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').press("Enter")
        _wait_for_layout(page)
        assert "module=" + module.id in page.url and "scope=" + classifier.id in page.url
        page.goto(page.url)
        page.reload()
        _wait_for_layout(page)
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        assert "Client [class]" in page.locator(".flow-breadcrumb").inner_text()
        page.locator(".flow-back").click()
        _wait_for_layout(page)
        assert "scope=" + classifier.id not in page.url
        assert "selected=" + classifier.id in page.url
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        page.go_back()
        _wait_for_layout(page)
        assert "scope=" + classifier.id in page.url
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        page.goto(page.url.replace(classifier.id, "unknown-native-id"))
        assert "scope=unknown-native-id" in page.url
        assert "not recorded inside this module" in page.locator(".flow-alternative").inner_text()
        assert page.locator(".flow-canvas").is_hidden()
        page.get_by_role("button", name="Open recorded module", exact=True).click()
        _wait_for_layout(page)
        assert "scope=unknown-native-id" not in page.url
        assert page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_counterpart_and_planned_classifier_open_declared_members(tmp_path):
    from test_target_graph import _contract
    from test_uml_evaluation import _model, _repository

    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    contract = _contract()
    entities = contract["declarations"]["uml"]["entities"]
    entities[0]["parent_id"] = "declared-module"
    context = {
        "presence": "planned",
        "language": "python",
        "provenance": ["docs/target.md"],
        "responsibilities": ["Own the declared operation."],
    }
    entities.extend(
        [
            {
                **context,
                "id": "declared-module",
                "kind": "module",
                "qualified_name": "sample.core",
                "parent_id": "core",
            },
            {
                **context,
                "id": "future",
                "kind": "class",
                "qualified_name": "sample.core.Future",
                "parent_id": "declared-module",
            },
            {
                **context,
                "id": "execute",
                "kind": "method",
                "qualified_name": "sample.core.Future.execute",
                "parent_id": "future",
            },
        ]
    )
    root, config = _repository(
        tmp_path,
        contract=contract,
        source="class Service:\n    def run(self, request):\n        return request\n",
    )
    model = _model(root, config)
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?theme=dark")
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.locator('.flow-nodes [data-label="core.py"]').press("Enter")
        page.get_by_role("button", name="Target", exact=True).click()
        _wait_for_layout(page)
        for identity, member in (("service", "run"), ("future", "execute")):
            page.locator(f'.flow-nodes [data-uml-id="{identity}"]').press("Enter")
            _wait_for_layout(page)
            assert "origin=declared" in page.url and "scope=" + identity in page.url
            page.goto(page.url)
            page.reload()
            _wait_for_layout(page)
            assert (
                page.get_by_role("button", name="Target", exact=True).get_attribute("aria-pressed")
                == "true"
            )
            assert page.locator(f'.flow-nodes [data-uml-id="{member}"]').count() == 1
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
            page.locator(".flow-back").click()
            _wait_for_layout(page)
            assert "origin=declared" in page.url and "selected=" + identity in page.url
            assert (
                page.locator(f'.flow-nodes [data-uml-id="{identity}"]').get_attribute(
                    "aria-pressed"
                )
                == "true"
            )
        page.goto(index.as_uri() + "?scope=core&view=diagram&theme=dark")
        page.locator('.flow-nodes [data-label="core.py"]').dblclick()
        page.wait_for_url("**/architecture.detail.html?*")
        page.get_by_role("button", name="Diff", exact=True).click()
        _wait_for_layout(page)
        assert "origin=declared" in page.url and "module=declared-module" in page.url
        page.locator('.flow-nodes [data-uml-id="future"]').dblclick()
        _wait_for_layout(page)
        assert page.locator('.flow-nodes [data-uml-id="execute"]').count() == 1
        page.goto(index.as_uri() + "?scope=core&view=diff&theme=dark")
        page.locator('.flow-nodes [data-label="core.py"]').dblclick()
        page.wait_for_url("**/architecture.detail.html?*")
        assert "origin=declared" in page.url and "module=declared-module" in page.url
        page.locator('.flow-nodes [data-uml-id="future"]').dblclick()
        _wait_for_layout(page)
        assert page.locator('.flow-nodes [data-uml-id="execute"]').count() == 1
        page.goto(index.as_uri() + "?scope=core&view=target&theme=dark")
        page.locator('.flow-nodes [data-uml-id="declared-module"]').press("Enter")
        _wait_for_layout(page)
        assert "module=declared-module" in page.url and "origin=declared" in page.url
        assert page.locator('.flow-nodes [data-uml-id="future"]').is_visible()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_offline_import_cell_return_preserves_native_cell_and_source_lens(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?view=diff&theme=dark")
        _open_health_check(page)
        page.locator('.flow-matrix [data-cell="0"]').click()
        assert "cell=0" in page.url
        before = page.locator(".flow-inspector-content").inner_text()
        page.locator(".flow-inspector-content").get_by_role(
            "link", name="Open UML and source evidence", exact=True
        ).click()
        assert "return_cell=0" in page.url
        page.get_by_role("button", name="As-Is", exact=True).click()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "cell=0" in page.url and "view=diff" in page.url and "theme=dark" in page.url
        page.wait_for_function(
            "expected => document.querySelector('.flow-inspector-content').innerText === expected",
            arg=before,
        )
        assert page.locator(".flow-inspector-content").inner_text() == before
        page.goto(index.as_uri() + "?view=target&cell=0&theme=dark")
        assert "cell=" not in page.url
        assert "Observed import cell" not in page.locator(".flow-inspector-content").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_generic_uml_entry_keeps_theme_return_selection_and_has_no_fragment(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?view=diff&theme=dark")
        page.locator('.flow-nodes [data-uml-id="core"]').press("Space")
        page.locator(".flow-inspector-content").get_by_role(
            "button", name="Browse 2 modules", exact=True
        ).click()
        assert "scope=core" in page.url
        page.locator('.flow-nodes [data-label="core.py"]').dblclick()
        page.wait_for_url("**/architecture.detail.html?*")
        page.locator(".flow-canvas").wait_for(state="visible")
        assert "theme=dark" in page.url and "return_scope=core" in page.url
        assert "#" not in page.url and "null" not in page.url
        assert page.locator("html").get_attribute("data-theme") == "dark"
        assert page.locator(".flow-canvas").is_visible()
        page.reload()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "view=diff" in page.url and "theme=dark" in page.url
        assert "scope=core" in page.url
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 0"
        )
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() > 0
        page.goto(index.as_uri() + "?scope=not-a-component&theme=dark")
        assert "scope=not-a-component" in page.url
        assert "not recorded in this snapshot" in page.locator(".flow-alternative").inner_text()
        page.get_by_role("button", name="Open architecture map", exact=True).click()
        assert "scope=not-a-component" not in page.url
        _wait_for_layout(page)
        assert page.locator('.flow-nodes [data-uml-id="core"]').is_visible()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_component_leaf_draws_native_module_cards_and_local_import_cells(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, graph = _route_pages(tmp_path, local_imports=True, package_empty=True)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?theme=dark&view=diff")
        page.locator('.flow-nodes [data-uml-id="core"]').press("Space")
        page.locator(".flow-inspector-content").get_by_role(
            "button", name="Browse 2 modules", exact=True
        ).click()
        assert "scope=core" in page.url and "view=diff" in page.url
        assert page.locator(".flow-canvas").is_visible()
        modules = {
            item.id
            for item in graph.entities
            if item.kind == "module" and item.qualified_name in ("sample.core", "sample")
        }
        cards = page.locator('.flow-nodes [data-uml-kind="module"]')
        assert set(cards.evaluate_all("nodes=>nodes.map(n=>n.dataset.umlId)")) == modules
        assert (
            "2 observed modules · 1 local dependency · 2 import sites"
            in page.locator(".atlas-summary").inner_text()
        )
        assert page.locator(".flow-edges .hit").count() == 1
        page.locator(".flow-edges .hit").press("Enter")
        assert "Permission: UNKNOWN" in page.locator(".flow-inspector-content").inner_text()
        assert page.get_by_role("group", name="Content", exact=True).is_hidden()
        page.locator('.flow-nodes [data-label="core.py"]').dblclick()
        page.wait_for_url("**/architecture.detail.html?*")
        page.locator(".flow-canvas").wait_for(state="visible")
        assert "theme=dark" in page.url and "view=diff" in page.url
        assert page.locator('.flow-nodes [data-label="Client"]').is_visible()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        page.wait_for_function("() => document.querySelector('[data-label=\"core.py\"]') !== null")
        assert page.locator('.flow-nodes [data-label="core.py"]').is_visible()
        page.locator('.flow-nodes [data-label="__init__.py"]').press("Enter")
        page.locator(".flow-alternative", has_text="No direct declarations").wait_for()
        assert "No direct declarations" in page.locator(".flow-alternative").inner_text()
        assert "sample/__init__.py" in page.locator(".flow-alternative").inner_text()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        page.get_by_role("button", name="Target", exact=True).click()
        assert "No declared modules" in page.locator(".flow-alternative").inner_text()
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() == 0
        page.get_by_role("button", name="Show As-Is modules", exact=True).click()
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length === 2"
        )
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() == 2
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_components_and_modules_choice_uses_native_scope_and_survives_return(tmp_path):
    from test_target_graph import _nested_repository
    from test_uml_evaluation import _model

    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    index = tmp_path / "architecture.report.html"
    model = _model(root, config)
    index.write_text(_page(model))
    from archkeel.render.html import render_architecture_details

    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?scope=ROOT&theme=dark")
        choice = page.get_by_role("group", name="Content", exact=True)
        assert choice.is_visible()
        assert (
            choice.get_by_role("button", name=re.compile("^Components")).get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        assert page.locator(".flow-canvas").is_visible()
        choice.get_by_role("button", name=re.compile("^Modules")).click()
        assert "content=modules" in page.url
        assert page.locator(".flow-canvas").is_visible()
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 0"
        )
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() > 0
        page.reload()
        assert "content=modules" in page.url
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 0"
        )
        page.get_by_role("button", name="Diff", exact=True).click()
        assert "content=modules" in page.url and "view=diff" in page.url
        choice.get_by_role("button", name=re.compile("^Components")).click()
        assert "content=components" in page.url and page.locator(".flow-canvas").is_visible()
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=component]').length > 0"
        )
        page.go_back()
        assert "content=modules" in page.url and page.locator(".flow-canvas").is_visible()
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 0"
        )
        page.locator('.flow-nodes [data-uml-kind="module"]').first.press("Enter")
        assert "return_content=modules" in page.url
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "scope=ROOT" in page.url and "content=modules" in page.url
        assert "view=diff" in page.url and "theme=dark" in page.url
        page.wait_for_function(
            "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 0"
        )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_over_budget_module_level_skips_layout_and_keeps_navigation(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    module_count = 84
    extra_files = {
        f"sample/m{index}.py": f"import sample.m{index + 1}\n" if index + 1 < module_count else ""
        for index in range(module_count)
    }
    model = _sample(tmp_path, extra_files=extra_files)
    html = _page(model)
    level = next(item for item in _atlas(html)["levels"] if item["parent_id"] is None)
    modules, edges = len(level["modules"]), len(level["cells"])
    assert modules > 80
    notice = (
        f"Diagram not drawn: {modules} modules and {edges} relationships exceed the diagram "
        "budget of 80 modules / 300 relationships. Open a component, search, or use Health "
        "check. All facts remain in the module list and architecture.json."
    )
    hook = """window.__moduleLayoutCalls = 0;
window.__originalModuleLayout = ELK.prototype.layout;
ELK.prototype.layout = function(graph) {
  window.__moduleLayoutCalls += 1;
  return window.__originalModuleLayout.call(this, graph);
};"""
    index = tmp_path / "architecture.report.html"
    index.write_text(_intercept_elk_publication(html, hook))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        # Target lists declared modules only. This fixture declares none (no uml), so its
        # notice is the declared-module path and is not repeated here.
        for query in ("", "&view=diff"):
            page.goto(index.as_uri() + f"?content=modules{query}&theme=light")
            page.wait_for_selector(
                '#flow[data-layout-state]:not([data-layout-state="pending"])', timeout=30000
            )
            text = page.locator(".flow-alternative").text_content() or ""
            assert notice in " ".join(text.split())
            assert page.locator(".flow-canvas").is_hidden()
            assert page.locator('#flow[data-layout-state="skipped"]').count() == 1
            assert page.locator(".flow-nodes [data-uml-id]").count() == 0
            assert page.evaluate("window.__moduleLayoutCalls") == 0
        first = next(item for item in _atlas(html)["modules"] if item["name"] == "sample.m0")
        page.goto(index.as_uri() + f"?content=modules&selected={first['id']}&theme=light")
        page.wait_for_selector('#flow[data-layout-state="skipped"]')
        assert page.evaluate("window.__moduleLayoutCalls") == 0
        assert "sample.m0" in page.locator(".flow-inspector").inner_text()
        page.goto(index.as_uri() + "?scope=core&content=modules&theme=light")
        page.wait_for_selector('#flow[data-layout-state="ready"]')
        assert page.locator(".flow-alternative").is_hidden()
        page.goto(index.as_uri() + "?content=modules&theme=light")
        page.wait_for_selector('#flow[data-layout-state="skipped"]')
        _open_health_check(page)
        assert page.locator(".flow-matrix svg").count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_over_budget_names_target_facts_and_keeps_authored_relationships(tmp_path):
    from copy import deepcopy
    from dataclasses import asdict

    from archkeel.ir.architecture_graph import Relationship, RelationshipKind
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    model = _sample(tmp_path, uml=True)
    html = _page(model)
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    payload = json.loads(match.group(1))
    atlas = payload["atlas"]
    base = next(item for item in atlas["declared_modules"] if item["name"] == "sample.core")
    extras = [
        {**deepcopy(base), "id": f"{base['id']}-extra{index}", "name": f"sample.extra{index}"}
        for index in range(81)
    ]
    first, second = extras[0], extras[1]
    relationship = asdict(
        Relationship(
            id=f"{first['id']}-requires-{second['id']}",
            kind=RelationshipKind.REQUIRES,
            source_id=first["id"],
            target_id=second["id"],
            evidence_ids=("evidence:extra-requires",),
        )
    )
    first["relationships"] = [relationship]
    atlas["declared_modules"] = [*atlas["declared_modules"], *extras]
    declared = atlas["declared_modules"]
    ids = {item["id"] for item in declared}
    modules = len(declared)
    edges = sum(
        1
        for item in declared
        for edge in item["relationships"]
        if edge["source_id"] == item["id"] and edge["target_id"] in ids
    )
    assert modules > 80
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).replace("<", "\\u003c")
    patched = html[: match.start(1)] + encoded + html[match.end(1) :]
    index = tmp_path / "architecture.report.html"
    index.write_text(patched)
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?view=target&content=modules&theme=light")
        page.wait_for_selector('#flow[data-layout-state="skipped"]', timeout=30000)
        text = page.locator(".flow-alternative").text_content() or ""
        assert " ".join(text.split()) == (
            f"Diagram not drawn: {modules} modules and {edges} relationships exceed the diagram "
            "budget of 80 modules / 300 relationships. Open a component or search for a module. "
            "All declared facts remain in architecture.json."
        )
        page.goto(
            index.as_uri() + f"?view=target&content=modules&selected={first['id']}&theme=light"
        )
        page.wait_for_selector('#flow[data-layout-state="skipped"]')
        assert relationship["id"] in page.locator(".flow-inspector").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_over_budget_share_menu_omits_empty_diagram_exports(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    module_count = 84
    extra_files = {
        f"sample/m{index}.py": f"import sample.m{index + 1}\n" if index + 1 < module_count else ""
        for index in range(module_count)
    }
    model = _sample(tmp_path, extra_files=extra_files)
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?content=modules&theme=light")
        page.wait_for_selector('#flow[data-layout-state="skipped"]', timeout=30000)
        page.get_by_role("button", name="Share", exact=True).click()
        assert page.get_by_role("menuitem", name="Copy link to this view", exact=True).is_visible()
        assert page.get_by_role("menuitem", name="Copy diagram as Mermaid", exact=True).count() == 0
        assert page.get_by_role("menuitem", name="Download SVG", exact=True).count() == 0
        page.goto(index.as_uri() + "?scope=core&content=modules&theme=light")
        page.wait_for_selector('#flow[data-layout-state="ready"]')
        page.get_by_role("button", name="Share", exact=True).click()
        assert page.get_by_role("menuitem", name="Copy diagram as Mermaid", exact=True).count() == 1
        assert page.get_by_role("menuitem", name="Download SVG", exact=True).count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_module_view_is_idle_until_an_element_is_emphasized(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = _route_pages(tmp_path, local_imports=True)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    pulses = "document.getAnimations().filter(a => a.animationName === 'flow-pulse')"
    try:
        page.goto(index.as_uri() + "?content=modules&theme=light")
        page.wait_for_selector('[data-layout-state="ready"]', state="attached")
        assert page.locator(".edge .pulse").count() > 0
        assert page.evaluate(f"{pulses}.length") == 0
        source = page.locator(".edge[data-uml-source]").first.get_attribute("data-uml-source")
        page.locator(f'.flow-nodes [data-uml-id="{source}"]').hover()
        assert page.evaluate(f"{pulses}.length") > 0
        assert page.evaluate(
            f"{pulses}.every(a => !a.effect.target.closest('.edge').classList.contains('dim'))"
        )
        page.mouse.move(1, 1)
        assert page.evaluate(f"{pulses}.length") == 0
        page.locator(".edge .hit").first.focus()
        assert page.evaluate(f"{pulses}.length") > 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_module_graph_keeps_native_fail_evidence_and_count_without_permission_inference(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = _route_pages(tmp_path)
    native = _atlas(index.read_text())
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?view=diff&content=modules&theme=dark")
        cards = page.locator('.flow-nodes [data-uml-kind="module"]')
        assert set(cards.evaluate_all("nodes=>nodes.map(n=>n.dataset.umlId)")) == {
            item["id"] for item in native["modules"]
        }
        assert page.locator('.flow-nodes [data-uml-kind="class"]').count() == 0
        assert page.locator(".flow-edges .hit").count() == len(native["cells"])
        assert "2 import sites" in page.locator(".atlas-summary").inner_text()
        page.locator(".flow-edges .hit").press("Enter")
        sheet = page.locator(".flow-inspector-content").inner_text()
        assert "Core finding status: FAIL" in sheet and "Permission: UNKNOWN" in sheet
        assert all(
            identity in sheet
            for index in native["cells"][0]["evidence_ids"]
            for identity in [native["reference_ids"][index]]
        )
        assert "cell=0" in page.url
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def _boundary_permission_report(tmp_path):
    from test_boundary_type_native_iterables import _fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _fixture(tmp_path, facade=True)
    from test_analyzer import _component

    implementation = tmp_path / "sample/app/impl.py"
    implementation.write_text(
        implementation.read_text()
        + "\nclass BaseLiteralGenerator:\n    def generate(self) -> Iterable[object]: return []\n"
    )
    facade = tmp_path / "sample/app/__init__.py"
    facade.write_text(
        facade.read_text()
        + "\nfrom .impl import BaseLiteralGenerator\n__all__.append('BaseLiteralGenerator')\n"
    )
    (tmp_path / "sample/other.py").write_text("def unrelated() -> None: pass\n")
    contract = json.loads((tmp_path / "contract.json").read_text())
    contract["components"].append(_component("other", public=["sample.other:unrelated"]))
    contract["components"][0]["public"].append("sample.app:BaseLiteralGenerator")
    contract["rules"][0]["allowed_positions"].append(
        {
            "qualified_name": "sample.app.BaseLiteralGenerator.generate",
            "position": "return",
            "annotation": "Iterable[object]",
            "container_depth": 1,
        }
    )
    contract["rules"][0]["allowed_positions"].append(
        {
            "qualified_name": "sample.app.unused",
            "position": "return",
            "annotation": "object",
        }
    )
    contract["schema_version"] = "2.2.0"
    contract["declarations"] = {
        "uml": {
            "schema_version": "1.0.0",
            "entities": [
                {
                    "id": "literal-class",
                    "kind": "class",
                    "qualified_name": "sample.app.BaseLiteralGenerator",
                    "parent_id": "COMP-APP",
                    "language": "python",
                    "presence": "planned",
                    "responsibilities": ["Generate literal values."],
                    "provenance": ["docs/architecture/sample.md"],
                },
                {
                    "id": "literal-generate",
                    "kind": "method",
                    "qualified_name": "sample.app.BaseLiteralGenerator.generate",
                    "parent_id": "literal-class",
                    "language": "python",
                    "presence": "planned",
                    "responsibilities": ["Generate literal values."],
                    "provenance": ["docs/architecture/sample.md"],
                },
            ],
        }
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
    )
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


def _flow_payload(path):
    match = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', path.read_text(), re.S
    )
    assert match
    return json.loads(match.group(1))


def test_boundary_permissions_shared_saved_cli_payload(tmp_path):
    output = _boundary_permission_report(tmp_path)
    overview = _flow_payload(output.with_suffix(".report.html"))
    detail = _flow_payload(output.with_suffix(".detail.html"))
    permissions = overview["boundary_permissions"]
    assert permissions == detail["boundary_permissions"]
    declarations = permissions["declared"]
    applied = permissions["applied"]
    unused = next(row for row in declarations if row["qualified_name"] == "sample.app.unused")
    assert unused["rationale"] and unused["provenance"]
    assert unused["component_ids"] and not unused["entity_ids"]
    assert not any(row["data"]["qualified_name"] == "sample.app.unused" for row in applied)
    opaque = next(row for row in applied if row["data"]["qualified_name"] == "sample.app.read")
    assert opaque["data"]["accepted_opacity"] is True
    assert opaque["declaration_id"]
    assert opaque["entity_ids"] and opaque["locations"]
    assert opaque["id"] not in {row["id"] for row in overview["atlas"]["findings"]}
    assert opaque["id"] not in {row["id"] for row in detail["findings"]}


def _open_permission_records(page):
    """Open the bounded permission lists without eagerly opening record bodies."""
    _open_details(page)
    if page.locator(".flow-canvas").is_visible():
        _wait_for_layout(page)
    audit = page.locator("[data-boundary-audit]")
    if audit.count() and audit.get_attribute("open") is None:
        audit.locator(":scope > summary").click()
        page.locator("[data-boundary-audit][data-boundary-loaded]").wait_for(state="attached")
    for group in page.locator("[data-boundary-group]").all():
        if group.get_attribute("open") is None:
            group.locator(":scope > summary").click()
            group.locator("[data-boundary-permission]").first.wait_for(state="attached")
        while group.locator("[data-boundary-more]").count():
            group.locator("[data-boundary-more]").click()


def _open_permission_record(entry):
    entry.locator("summary").click()
    entry.locator("dl").wait_for(state="attached")


def _open_permission_bodies(entries):
    entries.evaluate_all("rows => rows.forEach(row => row.open = true)")
    for entry in entries.all():
        entry.locator("dl").wait_for(state="attached")


@pytest.mark.parametrize("callable_name", ["read", "BaseLiteralGenerator.generate"])
def test_boundary_permissions_offline_lenses_and_member_routes(tmp_path, callable_name):
    api = pytest.importorskip("playwright.sync_api")
    output = _boundary_permission_report(tmp_path)
    index = output.with_suffix(".report.html")
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        _open_permission_records(page)
        assert (
            "applied boundary permissions" in page.locator(".flow-inspector").inner_text().lower()
        )
        page.locator('.flow-nodes [data-uml-id="COMP-OTHER"]').click()
        assert "boundary permissions" not in page.locator(".flow-inspector").inner_text().lower()
        page.goto(index.as_uri())
        page.get_by_role("button", name="Target", exact=True).click()
        _open_permission_records(page)
        inspector = page.locator(".flow-inspector")
        assert "declared boundary permissions" in inspector.inner_text().lower()
        assert "sample.app.unused" in inspector.inner_text()
        assert "Accepted opacity" not in inspector.inner_text()
        page.get_by_role("button", name="As-Is", exact=True).click()
        _open_permission_records(page)
        _open_permission_record(
            inspector.locator("[data-boundary-permission]").filter(
                has_text=f"sample.app.{callable_name}"
            )
        )
        inspector.locator("[data-boundary-permission]").filter(
            has_text=f"sample.app.{callable_name}"
        ).get_by_role("link", name=f"sample.app.impl.{callable_name}", exact=True).click()
        page.wait_for_url("**/*.detail.html?*")
        _open_permission_records(page)
        assert "applied boundary permissions" in inspector.inner_text().lower()
        _open_permission_record(
            inspector.locator("[data-boundary-permission]").filter(
                has_text=f"sample.app.{callable_name}"
            )
        )
        assert "Accepted opacity; type closure remains unproven." in inspector.inner_text()
        fact_entry = inspector.locator("[data-boundary-permission]").filter(
            has_text=f"sample.app.{callable_name}"
        )
        declaration_id = next(
            row["declaration_id"]
            for row in _flow_payload(index)["boundary_permissions"]["applied"]
            if row["data"]["qualified_name"] == f"sample.app.{callable_name}"
        )
        fact_entry.get_by_role("link", name=declaration_id, exact=True).click()
        page.wait_for_url(lambda url: "view=target" in str(url))
        _open_permission_records(page)
        assert (
            inspector.locator(f'[data-boundary-permission="{declaration_id}"]').get_attribute(
                "open"
            )
            is not None
        )
        assert "applied boundary permissions" not in inspector.inner_text().lower()
        history = page.evaluate("({url: location.href, length: history.length})")
        page.locator(".flow-arrange").click()
        assert page.evaluate("({url: location.href, length: history.length})") == history
        page.go_back()
        page.reload()
        _open_permission_records(page)
        assert f"sample.app.{callable_name}" in inspector.inner_text()
        page.go_back()
        assert page.url.startswith(index.as_uri())
        page.get_by_role("button", name="Diff", exact=True).click()
        _open_permission_records(page)
        assert "declared boundary permissions" in inspector.inner_text().lower()
        assert "applied boundary permissions" in inspector.inner_text().lower()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_boundary_permissions_nested_same_labels_keep_exact_contract_scope(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.render.atlas import boundary_permissions_payload

    root, config = _nested_repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json"):
        raw = json.loads((root / path).read_text())
        raw["components"][0]["label"] = "core"
        raw["rules"].append(
            {
                "id": "NATIVE",
                "kind": "boundary_types",
                "source": "sample.core",
                "rationale": "Accept this exact result.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
                "allowed_positions": [
                    {
                        "qualified_name": "sample.core.Service.run",
                        "position": "return",
                        "annotation": "object",
                    }
                ],
            }
        )
        (root / path).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.architecture_projection is not None
    assert all(item.kind == "rule_without_subjects" for item in result.diagnostics)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    payload = boundary_permissions_payload(
        model, architecture_report(model), result.architecture_projection
    )
    rows = payload["declared"]
    assert len(rows) == 3
    assert len({row["id"] for row in rows}) == 3
    for row in rows:
        expected = [
            component.id
            for component in result.architecture_projection.components
            if component.parent_id == row["contract_scope_id"]
            and component.namespace == "sample.core"
        ]
        assert row["component_ids"] == expected
        assert len(expected) == 1


def test_boundary_permission_unmapped_ambiguous_and_optional_metadata(tmp_path):
    from archkeel.ir.model import RecordData
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(model).architecture_projection
    fact = next(
        row for row in model.records("typing_signals") if row.kind == "boundary_type_allowance"
    )
    changed = replace(
        fact,
        subjects=(),
        fact_ids=(),
        evidence_ids=(),
        title="</script><img src=x onerror=alert(1)>",
        data=RecordData(
            tuple(
                {
                    **dict(fact.data.entries),
                    "unrelated_metadata": RecordData((("nested", "ignored"),)),
                    "annotation": "<script>alert(1)</script>",
                }.items()
            )
        ),
    )
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(changed,)) if section.name == "typing_signals" else section
            for section in model.sections
        ),
    )
    payload = boundary_permissions_payload(model, architecture_report(model), projection)
    row = payload["applied"][0]
    assert row["routes"] == row["component_ids"] == row["entity_ids"] == row["locations"] == []
    assert row["declaration_id"] is None
    assert "unrelated_metadata" not in row["data"]
    json.dumps(payload)
    duplicated = replace(
        projection, permission_rules=(*projection.permission_rules, *projection.permission_rules)
    )
    original = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    duplicate_rows = boundary_permissions_payload(
        original, architecture_report(original), duplicated
    )["applied"]
    assert all(row["declaration_id"] is None for row in duplicate_rows)


def test_boundary_permissions_offline_security_audit_and_old_payload(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    output = _boundary_permission_report(tmp_path)
    html = output.with_suffix(".report.html").read_text()
    data = _flow_payload(output.with_suffix(".report.html"))
    malicious = "</script><img src=x onerror=alert(1)>"
    row = data["boundary_permissions"]["applied"][0]
    row.update(
        entity_ids=[],
        component_ids=[],
        routes=[],
        locations=[],
        declaration_id=None,
        title=malicious,
        provenance=["javascript:alert(1)", malicious],
    )
    row["data"].update(qualified_name=malicious, annotation=malicious)
    encoded = json.dumps(data).replace("<", "\\u003c")
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    edited = html[: match.start(1)] + encoded + html[match.end(1) :]
    errors = []
    playwright, browser, page = _browser_page(api, edited, errors=errors)
    try:
        _open_permission_records(page)
        inspector = page.locator(".flow-inspector")
        assert "unmapped boundary permission audit" in inspector.inner_text().lower()
        entry = inspector.locator("[data-boundary-permission]").filter(has_text=malicious)
        _open_permission_record(entry)
        assert malicious in entry.inner_text()
        assert not inspector.locator("img, script, [onerror], a[href^='javascript:']").count()
        page.locator('.flow-nodes [data-uml-id="COMP-OTHER"]').click()
        assert "unmapped boundary permission audit" not in inspector.inner_text().lower()
        data.pop("boundary_permissions")
        old = (
            html[: match.start(1)] + json.dumps(data).replace("<", "\\u003c") + html[match.end(1) :]
        )
        page.set_content(old)
        _open_permission_records(page)
        assert "boundary permissions" not in inspector.inner_text().lower()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_boundary_permissions_target_member_without_module_route(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    output = _boundary_permission_report(tmp_path)
    index = output.with_suffix(".report.html")
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.get_by_role("button", name="Target", exact=True).click()
        _open_permission_records(page)
        entry = page.locator("[data-boundary-permission]").filter(
            has_text="sample.app.BaseLiteralGenerator.generate"
        )
        _open_permission_record(entry)
        entry.get_by_role(
            "link", name="sample.app.BaseLiteralGenerator.generate", exact=True
        ).click()
        page.wait_for_url("**/*.detail.html?*")
        _open_permission_records(page)
        assert "Requested scope" not in page.locator(".flow-inspector").inner_text()
        assert (
            "sample.app.BaseLiteralGenerator.generate"
            in page.locator(".flow-inspector").inner_text()
        )
        assert "selected=literal-generate" in page.url
        page.reload()
        _open_permission_records(page)
        assert (
            "sample.app.BaseLiteralGenerator.generate"
            in page.locator(".flow-inspector").inner_text()
        )
        page.go_back()
        assert page.url.startswith(index.as_uri())
        for component, scope in (("COMP-OTHER", "literal-class"), ("COMP-APP", "absent-member")):
            page.goto(
                output.with_suffix(".detail.html").as_uri()
                + f"?component={component}&origin=declared&scope={scope}&view=target"
            )
            _open_permission_records(page)
            assert (
                "No content is inferred for the rejected scope."
                in page.locator(".flow-inspector").inner_text()
            )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_boundary_permission_declared_exact_module_owner_without_application(tmp_path):
    root = _prepare_repo(
        tmp_path,
        {
            "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
            "sample/api.py": "def read() -> int: return 1\n",
            "archkeel.toml": (
                '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
            ),
            "docs/target.md": "Explicit native result decision.\n",
            "contract.json": json.dumps(
                {
                    "schema_version": "2.2.0",
                    "components": [
                        {
                            "id": "API",
                            "label": "api",
                            "role": "component",
                            "packages": [],
                            "exact_modules": ["sample.api"],
                            "responsibilities": ["Own the API."],
                            "forbidden_responsibilities": [],
                            "provenance": ["docs/target.md"],
                            "public": ["sample.api:read"],
                        }
                    ],
                    "rules": [
                        {
                            "id": "NATIVE",
                            "kind": "boundary_types",
                            "source": "sample.api",
                            "rationale": "Accept the planned native result.",
                            "decided_by": "architect",
                            "provenance": ["docs/target.md"],
                            "allowed_positions": [
                                {
                                    "qualified_name": "sample.api.native",
                                    "position": "return",
                                    "annotation": "object",
                                }
                            ],
                        }
                    ],
                }
            ),
        },
    )
    output = root / "out/architecture.json"
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 0
    permissions = _flow_payload(output.with_suffix(".report.html"))["boundary_permissions"]
    assert permissions["applied"] == []
    assert permissions["declared"][0]["component_ids"] == ["API"]
    assert permissions["declared"][0]["entity_ids"] == []


def test_boundary_permission_field_default_keeps_optional_depth_distinct(tmp_path):
    from archkeel.ir.model import RecordData
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    original = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(original).architecture_projection
    fact = next(
        row
        for row in original.records("typing_signals")
        if row.kind == "boundary_type_allowance"
        and row.data.get("qualified_name") == "sample.app.read"
    )
    declaration_id = boundary_permissions_payload(
        original, architecture_report(original), projection
    )["applied"][0]["declaration_id"]
    assert declaration_id
    for missing, expected in (("field_path", declaration_id), ("container_depth", None)):
        changed = replace(
            fact,
            data=RecordData(
                tuple((key, value) for key, value in fact.data.entries if key != missing)
            ),
        )
        model = replace(
            original,
            sections=tuple(
                replace(section, records=(changed,))
                if section.name == "typing_signals"
                else section
                for section in original.sections
            ),
        )
        row = boundary_permissions_payload(model, architecture_report(model), projection)[
            "applied"
        ][0]
        assert row["declaration_id"] == expected


def test_boundary_permissions_offline_module_and_diff_member_selection(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    output = _boundary_permission_report(tmp_path)
    index = output.with_suffix(".report.html")
    payload = _flow_payload(index)
    module = next(row for row in payload["atlas"]["modules"] if row["name"] == "sample.app.impl")
    applied = next(
        row
        for row in payload["boundary_permissions"]["applied"]
        if row["data"]["qualified_name"] == "sample.app.BaseLiteralGenerator.generate"
    )
    route = applied["routes"][0]
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(
            index.as_uri() + f"?scope=COMP-APP&selected={module['id']}&view=diagram&content=modules"
        )
        _open_permission_records(page)
        inspector = page.locator(".flow-inspector")
        assert "applied boundary permissions" in inspector.inner_text().lower()
        page.goto(
            output.with_suffix(".detail.html").as_uri()
            + f"?component=COMP-APP&module={route['module_id']}&scope={route['scope_id']}"
            + f"&selected={route['entity_id']}&origin=observed&view=diff"
        )
        _open_permission_records(page)
        assert "applied boundary permissions" in inspector.inner_text().lower()
        assert "declared boundary permissions" in inspector.inner_text().lower()
        assert "sample.app.unused" not in inspector.inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


_ALIAS_PAIR = {
    "origin": "sample.app.impl:Packet",
    "shape": (
        "tuple[tuple[str, list[object]] | tuple[str, list[object], "
        "sample.app.types.Metadata], list[dict[str, object]]]"
    ),
}
_ABSENT_ALIAS_PAIR = object()


def _alias_permission_payload(
    tmp_path,
    declared,
    applied,
    *,
    duplicate=False,
    key_declared=_ABSENT_ALIAS_PAIR,
    key_applied=_ABSENT_ALIAS_PAIR,
    applied_changes=None,
):
    from archkeel.ir.facts_codec import freeze_data
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(model).architecture_projection
    fact = next(
        row for row in model.records("typing_signals") if row.kind == "boundary_type_allowance"
    )
    permission = next(
        row for row in projection.permission_rules if row.declaration.kind == "boundary_types"
    )
    data = json.loads(value_bytes(fact.data))
    selector = {
        key: value
        for key, value in data.items()
        if key
        in {
            "qualified_name",
            "position",
            "field_path",
            "annotation",
            "container_depth",
            "mapping_depth",
        }
    }
    if declared is not _ABSENT_ALIAS_PAIR:
        selector["alias_body"] = declared
    if key_declared is not _ABSENT_ALIAS_PAIR:
        selector["key_alias_body"] = key_declared
    declaration_data = json.loads(value_bytes(permission.declaration.data))
    declaration = replace(
        permission.declaration,
        data=freeze_data({**declaration_data, "allowed_positions": [selector]}),
    )
    permission = replace(permission, declaration=declaration)
    if applied is not _ABSENT_ALIAS_PAIR:
        data["alias_body"] = applied
    if key_applied is not _ABSENT_ALIAS_PAIR:
        data["key_alias_body"] = key_applied
    for name, value in (applied_changes or {}).items():
        if value is _ABSENT_ALIAS_PAIR:
            data.pop(name, None)
        else:
            data[name] = value
    fact = replace(fact, data=freeze_data(data), provenance=("fact-own-provenance",))
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(fact,))
            if section.name == "typing_signals"
            else replace(
                section,
                records=tuple(
                    declaration if row.id == declaration.id else row for row in section.records
                ),
            )
            if section.name == "declarations"
            else section
            for section in model.sections
        ),
    )
    model = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(model))))
    projection = replace(
        projection, permission_rules=(permission, permission) if duplicate else (permission,)
    )
    return boundary_permissions_payload(model, architecture_report(model), projection), model


@pytest.mark.parametrize(
    "declared,applied,joined",
    [
        (_ALIAS_PAIR, _ALIAS_PAIR, True),
        (_ALIAS_PAIR, dict(reversed(tuple(_ALIAS_PAIR.items()))), True),
        (_ALIAS_PAIR, {**_ALIAS_PAIR, "origin": "sample.app.moved:Packet"}, False),
        (_ALIAS_PAIR, {**_ALIAS_PAIR, "shape": _ALIAS_PAIR["shape"] + " | None"}, False),
        (_ALIAS_PAIR, _ABSENT_ALIAS_PAIR, False),
        (_ABSENT_ALIAS_PAIR, _ALIAS_PAIR, False),
        (_ABSENT_ALIAS_PAIR, _ABSENT_ALIAS_PAIR, True),
        *[
            (bad, bad, False)
            for bad in [
                None,
                [],
                "Packet",
                {},
                {"origin": "only"},
                {"shape": "only"},
                {**_ALIAS_PAIR, "extra": "no"},
                {**_ALIAS_PAIR, "origin": ""},
                {**_ALIAS_PAIR, "shape": ""},
                {**_ALIAS_PAIR, "shape": " "},
                {**_ALIAS_PAIR, "origin": 7},
                {**_ALIAS_PAIR, "shape": []},
            ]
        ],
    ],
)
def test_bound_alias_permission_join_requires_exact_valid_pair(tmp_path, declared, applied, joined):
    payload, model = _alias_permission_payload(tmp_path, declared, applied)
    row = payload["applied"][0]
    assert bool(row["declaration_id"]) is joined
    assert bool(row["rationale"]) is joined
    assert row["provenance"] == ("fact-own-provenance",)
    if applied is not _ABSENT_ALIAS_PAIR:
        assert row["data"]["alias_body"] == applied
    if declared is not _ABSENT_ALIAS_PAIR:
        assert payload["declared"][0]["alias_body"] == declared
    json.dumps(payload)
    audit = json.loads(value_bytes(model.records("typing_signals")[0].data))
    assert ("alias_body" in audit) is (applied is not _ABSENT_ALIAS_PAIR)
    if applied is not _ABSENT_ALIAS_PAIR:
        assert audit["alias_body"] == applied


@pytest.mark.parametrize(
    "declared",
    [
        _ALIAS_PAIR,
        {**_ALIAS_PAIR, "shape": _ALIAS_PAIR["shape"] + " | None"},
        {**_ALIAS_PAIR, "origin": "sample.app.other:Packet"},
    ],
)
def test_bound_alias_duplicate_exact_or_near_declarations_do_not_join(tmp_path, declared):
    payload, _ = _alias_permission_payload(tmp_path, declared, _ALIAS_PAIR, duplicate=True)
    assert payload["applied"][0]["declaration_id"] is None


@pytest.mark.parametrize(
    "binding",
    [
        None,
        [],
        "Packet",
        {},
        {"origin": "only"},
        {**_ALIAS_PAIR, "extra": "no"},
        {**_ALIAS_PAIR, "origin": 7},
        {"origin": ["malformed"], "shape": {"bad": "value"}},
    ],
)
def test_bound_alias_malformed_saved_audit_never_borrows_rationale(tmp_path, binding):
    api = pytest.importorskip("playwright.sync_api")
    payload, model = _alias_permission_payload(tmp_path, binding, binding)
    fact = payload["applied"][0]
    errors = []
    playwright, browser, page = _browser_page(api, _page(model), errors=errors)
    try:
        _open_permission_records(page)
        entry = page.locator(f'[data-boundary-permission="{fact["id"]}"]')
        _open_permission_record(entry)
        assert "Unavailable or ambiguous" in entry.inner_text()
        assert "Rationale unavailable" in entry.inner_text()
        assert "fact-own-provenance" in entry.inner_text()
        assert "alias_body" in entry.inner_text()
        assert "[object Object]" not in entry.inner_text()
        assert entry.get_by_role("link", name="Complete audit JSON", exact=True).count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "applied,joined",
    [
        (_ALIAS_PAIR, True),
        ({**_ALIAS_PAIR, "origin": "sample.app.changed:Packet"}, False),
        ({**_ALIAS_PAIR, "shape": _ALIAS_PAIR["shape"] + " | None"}, False),
        (_ABSENT_ALIAS_PAIR, False),
    ],
)
def test_bound_alias_saved_body_origin_and_presence_match_in_browser(tmp_path, applied, joined):
    api = pytest.importorskip("playwright.sync_api")
    payload, model = _alias_permission_payload(tmp_path, _ALIAS_PAIR, applied)
    fact = payload["applied"][0]
    errors = []
    playwright, browser, page = _browser_page(api, _page(model), errors=errors)
    try:
        _open_permission_records(page)
        entry = page.locator(f'[data-boundary-permission="{fact["id"]}"]')
        _open_permission_record(entry)
        assert ("Unavailable or ambiguous" not in entry.inner_text()) is joined
        assert ("Rationale unavailable" not in entry.inner_text()) is joined
        assert "fact-own-provenance" in entry.inner_text() and not errors
    finally:
        browser.close()
        playwright.stop()


def _bound_alias_report(tmp_path, *, facade=True):
    from test_boundary_type_bound_aliases import _fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _fixture(tmp_path, facade=facade)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


@pytest.mark.parametrize("facade", [False, True])
def test_bound_alias_real_cli_wire_and_shared_reports(tmp_path, facade):
    output = _bound_alias_report(tmp_path, facade=facade)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert canonical_report_bytes(model) == output.read_bytes()
    overview = _flow_payload(output.with_suffix(".report.html"))
    detail = _flow_payload(output.with_suffix(".detail.html"))
    assert overview["boundary_permissions"] == detail["boundary_permissions"]
    permissions = overview["boundary_permissions"]
    assert len(permissions["declared"]) == len(permissions["applied"]) == 4
    assert all(row["alias_body"] == _ALIAS_PAIR for row in permissions["declared"])
    for row in permissions["applied"]:
        assert row["data"]["alias_body"] == _ALIAS_PAIR
        assert row["declaration_id"] and row["rationale"] and row["routes"]
        assert row["data"]["observed_container_depth"] == (
            3 if row["data"].get("accepted_opacity") else 2
        )
        assert ("container_depth" in row["data"]) is bool(row["data"].get("accepted_opacity"))
        assert row["locations"] and row["evidence_ids"] and row["fact_ids"]
    assert len(model.records("violations")) == 1
    assert model.records("unknowns")


@pytest.mark.parametrize("facade", [False, True])
def test_bound_alias_real_offline_navigation_and_target_purity(tmp_path, facade):
    api = pytest.importorskip("playwright.sync_api")
    output = _bound_alias_report(tmp_path, facade=facade)
    index = output.with_suffix(".report.html")
    payload = _flow_payload(index)
    opaque = next(
        row
        for row in payload["boundary_permissions"]["applied"]
        if row["data"].get("accepted_opacity")
    )
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        _open_permission_records(page)
        entry = page.locator(f'[data-boundary-permission="{opaque["id"]}"]')
        _open_permission_record(entry)
        assert _ALIAS_PAIR["origin"] in entry.inner_text()
        assert _ALIAS_PAIR["shape"] in entry.inner_text()
        assert "Accepted opacity; type closure remains unproven." in entry.inner_text()
        route = next(
            row
            for row in opaque["routes"]
            if row["label"].endswith("." + opaque["data"]["qualified_name"].rsplit(".", 1)[1])
        )
        entry.get_by_role("link", name=route["label"], exact=True).click()
        page.wait_for_url("**/*.detail.html?*")
        _open_permission_records(page)
        _open_permission_bodies(page.locator("[data-boundary-permission]"))
        assert f"selected={route['entity_id']}" in page.url
        assert "Requested scope" not in page.locator(".flow-inspector").inner_text()
        assert _ALIAS_PAIR["shape"] in page.locator(".flow-inspector").inner_text()
        page.reload()
        _open_permission_records(page)
        _open_permission_bodies(page.locator("[data-boundary-permission]"))
        assert _ALIAS_PAIR["origin"] in page.locator(".flow-inspector").inner_text()
        implementation = tmp_path / "sample/app/impl.py"
        implementation.write_text(
            implementation.read_text().replace("dict[str, object]", "dict[int, object]")
        )
        changed = tmp_path / "out/changed.json"
        assert main(["report", "--root", str(tmp_path), "--output", str(changed), "--json"]) == 0
        changed_payload = _flow_payload(changed.with_suffix(".report.html"))
        assert (
            changed_payload["boundary_permissions"]["declared"]
            == payload["boundary_permissions"]["declared"]
        )
        assert changed_payload["boundary_permissions"]["applied"] == []
        page.goto(changed.with_suffix(".report.html").as_uri() + "?view=target")
        _open_permission_records(page)
        _open_permission_bodies(page.locator("[data-boundary-permission]"))
        text = page.locator(".flow-inspector").inner_text()
        assert _ALIAS_PAIR["shape"] in text
        assert "applied boundary permissions" not in text.lower()
        assert "[object Object]" not in text and not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "binding",
    [
        _ALIAS_PAIR,
        {"origin": "</script><img src=x onerror=alert(1)>", "shape": "<script>alert(1)</script>"},
        {"origin": ["malformed"], "shape": {"bad": "value"}},
    ],
)
def test_bound_alias_offline_rows_are_complete_escaped_and_lens_specific(tmp_path, binding):
    api = pytest.importorskip("playwright.sync_api")
    output = _boundary_permission_report(tmp_path)
    html = output.with_suffix(".report.html").read_text()
    data = _flow_payload(output.with_suffix(".report.html"))
    data["boundary_permissions"]["declared"][0]["alias_body"] = binding
    data["boundary_permissions"]["applied"][0]["data"]["alias_body"] = binding
    data["boundary_permissions"]["applied"][0]["data"]["observed_container_depth"] = 2
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    html = html[: match.start(1)] + json.dumps(data).replace("<", "\\u003c") + html[match.end(1) :]
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_permission_records(page)
        inspector = page.locator(".flow-inspector")
        for lens, declared, applied in [
            ("As-Is", False, True),
            ("Target", True, False),
            ("Diff", True, True),
        ]:
            page.get_by_role("button", name=lens, exact=True).click()
            _open_permission_records(page)
            entries = inspector.locator("[data-boundary-permission]")
            _open_permission_bodies(entries)
            text = inspector.inner_text()
            assert ("declared boundary permissions" in text.lower()) is declared
            assert ("applied boundary permissions" in text.lower()) is applied
            assert ("Observed container depth" in text) is applied
            assert "alias_body.origin" in text and "alias_body.shape" in text
            for value in binding.values():
                assert (
                    value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
                ) in text
            assert "[object Object]" not in text
            assert not inspector.locator("img, script, [onerror], a[href^='javascript:']").count()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("pair_name", ["alias_body", "key_alias_body"])
@pytest.mark.parametrize(
    "mutation,joined",
    [
        ("valid", True),
        ("reordered", True),
        ("missing", False),
        ("undeclared", False),
        ("provider", False),
        ("shape", False),
        *[
            (bad, False)
            for bad in [
                None,
                [],
                "Alias",
                {},
                {"origin": "only"},
                {"shape": "only"},
                {"origin": "provider:Alias", "shape": "str | None", "extra": "no"},
                {"origin": "", "shape": "str | None"},
                {"origin": "provider:Alias", "shape": " "},
                {"origin": 7, "shape": "str | None"},
                {"origin": "provider:Alias", "shape": []},
            ]
        ],
    ],
)
def test_both_alias_permission_pairs_join_exactly(tmp_path, pair_name, mutation, joined):
    from test_boundary_type_bound_aliases import _GROUP_BINDING, _KEY_BINDING

    declared = {"alias_body": _GROUP_BINDING, "key_alias_body": _KEY_BINDING}
    applied = dict(declared)
    good = declared[pair_name]
    if mutation == "reordered":
        applied[pair_name] = dict(reversed(tuple(good.items())))
    elif mutation == "missing":
        applied[pair_name] = _ABSENT_ALIAS_PAIR
    elif mutation == "undeclared":
        declared[pair_name] = _ABSENT_ALIAS_PAIR
    elif mutation == "provider":
        applied[pair_name] = {**good, "origin": "sample.app.other:Alias"}
    elif mutation == "shape":
        applied[pair_name] = {**good, "shape": good["shape"] + " | None"}
    elif mutation != "valid":
        declared[pair_name] = applied[pair_name] = mutation
    payload, model = _alias_permission_payload(
        tmp_path,
        declared["alias_body"],
        applied["alias_body"],
        key_declared=declared["key_alias_body"],
        key_applied=applied["key_alias_body"],
    )
    row = payload["applied"][0]
    assert bool(row["declaration_id"]) is joined
    assert bool(row["rationale"]) is joined
    audit = json.loads(value_bytes(model.records("typing_signals")[0].data))
    for name, pair in applied.items():
        assert (name in row["data"]) is (pair is not _ABSENT_ALIAS_PAIR)
        if pair is not _ABSENT_ALIAS_PAIR:
            assert row["data"][name] == audit[name] == pair
    assert row["provenance"] == ("fact-own-provenance",)
    json.dumps(payload)


def test_both_alias_permission_pairs_are_complete_escaped_and_lens_specific(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root = {
        "origin": "root.<unsafe>:" + "Long" * 80,
        "shape": "dict[str, float] | <script>alert(1)</script>" + " | map" * 100,
    }
    key = {
        "origin": "key.<img src=x onerror=alert(1)>:" + "Key" * 80,
        "shape": "str | None <escaped>" + " suffix" * 100,
    }
    payload, model = _alias_permission_payload(
        tmp_path,
        root,
        root,
        key_declared=key,
        key_applied=key,
    )
    saved = tmp_path / "both-bindings.html"
    saved.write_text(_page(model))
    errors = []
    playwright, browser, page = _browser_page(api, saved.read_text(), errors=errors)
    try:
        page.goto(saved.as_uri())
        for lens, applied in [("As-Is", True), ("Target", False), ("Diff", True)]:
            page.get_by_role("button", name=lens, exact=True).click()
            _open_permission_records(page)
            row = payload["applied" if applied else "declared"][0]
            entry = page.locator(f'[data-boundary-permission="{row["id"]}"]')
            _open_permission_record(entry)
            text = entry.inner_text()
            for name, binding in [("alias_body", root), ("key_alias_body", key)]:
                for field, value in binding.items():
                    assert f"{name}.{field}" in text and value in text
            assert not entry.locator("img, script, [onerror], a[href^='javascript:']").count()
            assert "fact-own-provenance" in text if applied else "Source" in text
            assert (
                page.locator(".boundary-permissions")
                .filter(has_text="Applied boundary permissions")
                .count()
                > 0
            ) is applied
        assert not errors
    finally:
        browser.close()
        playwright.stop()


_TYPED_UNION_BODY = "dict[str, float] | dict[tuple[int, int], float] | dict[SexKey, float]"
_EXPANDED_UNION_BODY = _TYPED_UNION_BODY.replace("SexKey", "str | None")


def _typed_union_report(
    tmp_path, *, facade=False, annotation="GroupMask", body=_TYPED_UNION_BODY, local_key=False
):
    from test_boundary_type_bound_aliases import _typed_union_fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _typed_union_fixture(
        tmp_path, facade=facade, annotation=annotation, body=body, local_key=local_key
    )
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize(
    "annotation,body,local_key,root_pair,key_pair,count",
    [
        ("GroupMask", _TYPED_UNION_BODY, False, True, True, 3),
        (_TYPED_UNION_BODY, _TYPED_UNION_BODY, False, False, True, 3),
        (_EXPANDED_UNION_BODY, _TYPED_UNION_BODY, False, False, False, 3),
        ("GroupMask", _EXPANDED_UNION_BODY, False, True, False, 3),
        ("GroupMask", _TYPED_UNION_BODY, True, True, True, 3),
        (_TYPED_UNION_BODY, _TYPED_UNION_BODY, True, False, True, 3),
        (
            "dict[str, float] | dict[tuple[int, int], int]",
            _TYPED_UNION_BODY,
            False,
            False,
            False,
            2,
        ),
    ],
)
def test_typed_union_real_cli_wire_and_shared_reports(
    tmp_path,
    facade,
    annotation,
    body,
    local_key,
    root_pair,
    key_pair,
    count,
):
    output = _typed_union_report(
        tmp_path, facade=facade, annotation=annotation, body=body, local_key=local_key
    )
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert canonical_report_bytes(model) == output.read_bytes()
    permissions = _flow_payload(output.with_suffix(".report.html"))["boundary_permissions"]
    assert permissions == _flow_payload(output.with_suffix(".detail.html"))["boundary_permissions"]
    assert len(permissions["declared"]) == 1 and len(permissions["applied"]) == count
    declaration = permissions["declared"][0]
    grants = {
        row.id: json.loads(value_bytes(row.data))
        for row in model.records("typing_signals")
        if row.kind == "boundary_type_allowance"
    }
    for applied in permissions["applied"]:
        assert applied["declaration_id"] == declaration["id"] and applied["rationale"]
        for pair_name, present in [("alias_body", root_pair), ("key_alias_body", key_pair)]:
            assert (pair_name in applied["data"]) is (pair_name in declaration) is present
            if present:
                assert (
                    applied["data"][pair_name]
                    == declaration[pair_name]
                    == grants[applied["id"]][pair_name]
                )
        assert (
            applied["routes"]
            and applied["locations"]
            and applied["fact_ids"]
            and applied["evidence_ids"]
        )
    assert len(model.records("violations")) == 1 and model.records("unknowns")


def test_typed_union_real_offline_entry_preserves_both_bindings_and_routes(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    output = _typed_union_report(tmp_path, facade=True)
    index = output.with_suffix(".report.html")
    permissions = _flow_payload(index)["boundary_permissions"]
    fact = permissions["applied"][0]
    declaration = permissions["declared"][0]
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        _open_permission_records(page)
        entry = page.locator(f'[data-boundary-permission="{fact["id"]}"]')
        _open_permission_record(entry)
        for binding in ("alias_body", "key_alias_body"):
            for field, value in fact["data"][binding].items():
                assert f"{binding}.{field}" in entry.inner_text() and value in entry.inner_text()
        for location in fact["locations"]:
            assert location["file"] in entry.inner_text()
        entry.get_by_role("link", name=declaration["id"], exact=True).click()
        page.wait_for_url("**/*.detail.html?*view=target*#*")
        _open_permission_records(page)
        declared_entry = page.locator(f'[data-boundary-permission="{declaration["id"]}"]')
        assert declared_entry.get_attribute("open") is not None
        for binding in ("alias_body", "key_alias_body"):
            assert declaration[binding]["origin"] in declared_entry.inner_text()
            assert declaration[binding]["shape"] in declared_entry.inner_text()
        assert (
            not page.locator(".boundary-permissions")
            .filter(has_text="Applied boundary permissions")
            .count()
        )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.other"},
        {"position": "argument"},
        {"annotation": "Changed"},
        {"field_path": "payload"},
        {"container_depth": 2},
        {"container_depth": _ABSENT_ALIAS_PAIR},
        {"mapping_depth": 1},
    ],
)
def test_both_alias_permission_pairs_cannot_cross_selector_coordinates(tmp_path, change):
    from test_boundary_type_bound_aliases import _GROUP_BINDING, _KEY_BINDING

    payload, _ = _alias_permission_payload(
        tmp_path,
        _GROUP_BINDING,
        _GROUP_BINDING,
        key_declared=_KEY_BINDING,
        key_applied=_KEY_BINDING,
        applied_changes=change,
    )
    applied = payload["applied"][0]
    assert applied["declaration_id"] is None and applied["rationale"] is None


@pytest.mark.parametrize(
    "filter",
    [
        None,
        ReportFilter(only_violations=True),
        ReportFilter(only_calls=True),
        ReportFilter(only_architecture=True),
        ReportFilter(only_architecture=True, full_architecture=True),
        ReportFilter(rule="R1"),
        ReportFilter(component="core"),
    ],
)
def test_pair_preserves_every_filter(tmp_path, filter):
    model = _sample(tmp_path, uml=True)
    result = replace(_result(model), report_filter=filter)
    payload = canonical_report_bytes(model)
    kw = dict(repository="One target", architecture_href="custom.name.json")
    expected = html_renderer.render_architecture_details(result, payload, **kw)
    expected["custom.name.report.html"] = html_renderer.render_architecture_html(
        result, payload, **kw
    )
    assert html_renderer.render_architecture_pages(result, payload, **kw) == tuple(expected.items())


def test_pair_without_projection_preserves_legacy_page(tmp_path):
    model = _sample(tmp_path)
    result = replace(_result(model), architecture_projection=None)
    payload = canonical_report_bytes(model)
    kw = dict(repository="One target", architecture_href="architecture.json")
    assert html_renderer.render_architecture_pages(result, payload, **kw) == (
        ("architecture.report.html", html_renderer.render_architecture_html(result, payload, **kw)),
    )


def test_pair_decodes_and_projects_once(tmp_path, monkeypatch):
    model = _sample(tmp_path, uml=True)
    result = _result(model)
    payload = canonical_report_bytes(model)
    calls = []
    parse = html_renderer.parse_observation
    graph = html_renderer.architecture_report

    def decode(*args):
        calls.append("decode")
        return parse(*args)

    def project(*args):
        calls.append("graph")
        return graph(*args)

    monkeypatch.setattr(html_renderer, "parse_observation", decode)
    monkeypatch.setattr(html_renderer, "architecture_report", project)
    assert (
        len(
            html_renderer.render_architecture_pages(
                result, payload, repository="One target", architecture_href="architecture.json"
            )
        )
        == 2
    )
    assert calls == ["decode", "graph"]


def test_pair_rejects_mismatched_projection(tmp_path):
    model = _sample(tmp_path)
    result = _result(model)
    projection = result.architecture_projection
    assert projection is not None
    result = replace(
        result,
        architecture_projection=replace(
            projection, source=replace(projection.source, source_digest="0" * 64)
        ),
    )
    with pytest.raises(ValueError, match="matching authenticated Core projection"):
        html_renderer.render_architecture_pages(
            result,
            canonical_report_bytes(model),
            repository="One",
            architecture_href="architecture.json",
        )


@pytest.mark.parametrize("payload", [b"{}", b"not JSON"])
def test_pair_keeps_strict_decode(tmp_path, payload):
    model = _sample(tmp_path)
    result = _result(model)
    with pytest.raises((ValueError, KeyError, TypeError)):
        html_renderer.render_architecture_pages(
            result, payload, repository="One", architecture_href="architecture.json"
        )


def test_cli_main_render_failure_publishes_no_html(tmp_path, monkeypatch, capsys):
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "published" / "architecture.json"

    def fail_main(*_args, **_kwargs):
        raise ValueError("injected main render failure")

    monkeypatch.setattr(html_renderer, "_atlas_document", fail_main)
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 2
    assert "injected main render failure" in capsys.readouterr().out
    assert output.is_file()
    assert not tuple(output.parent.glob("*.html"))


@pytest.mark.parametrize("open_map", [True, False])
def test_paired_page_carrier_preserves_original_render_type_rule(tmp_path, open_map):
    from test_analyzer import _component

    from archkeel.ir.trace import trace_valid_violations

    original = json.loads((Path(__file__).parents[1] / "architecture-contract.json").read_text())
    rule = next(rule for rule in original["rules"] if rule["id"] == "RENDER-TYPES-DECLARED")
    package = tmp_path / "archkeel/render"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    annotation = (
        "dict[str, bytes]"
        if open_map
        else html_renderer.render_architecture_pages.__annotations__["return"]
    )
    (package / "html.py").write_text(
        "def render_architecture_details() -> dict[str, bytes]: pass\n"
        f"def render_architecture_pages() -> {annotation}: pass\n"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "render",
                        packages=["archkeel.render"],
                        public=[
                            "archkeel.render.html:render_architecture_details",
                            "archkeel.render.html:render_architecture_pages",
                        ],
                    )
                ],
                "rules": [rule],
            }
        )
    )
    result = observe(
        tmp_path,
        roots=(".",),
        namespace="archkeel",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert len(violations) == int(open_map)
    assert not [
        record
        for record in result.observation.records("unknowns") or ()
        if record.kind == "boundary_type_position"
    ]
    assert not result.diagnostics
