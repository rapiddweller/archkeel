# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re
import sys
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo
from test_module_explore import _sample
from test_report_filter import CONFIG as TOUR_CONFIG
from test_report_filter import _tour_root

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.baseline import select_violations
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import ReportFilter, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
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
            "id": data["reference_ids"][row[0]],
            "kind": data["reference_ids"][row[1]],
            "status": row[2],
            "count": row[3],
            "undecided": row[4],
            "reason": data["reference_ids"][row[5]],
            "scope": data["reference_ids"][row[6]],
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
    assert len(page.encode()) < 1_000_000


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
            assert "Count unavailable" in card
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


@pytest.mark.parametrize("width", [1440, 400])
def test_atlas_browser_keeps_positions_and_unknown_cells_across_lenses(tmp_path, width):
    api = pytest.importorskip("playwright.sync_api")
    page_html = _page(_sample(tmp_path))
    errors = []
    playwright, browser, page = _browser_page(api, page_html, width=width, errors=errors)
    try:
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


def test_diff_balance_links_select_the_deviation_source(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html = _page(_sample(tmp_path))
    path = tmp_path / "architecture.report.html"
    path.write_text(html)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.goto(path.as_uri())
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


def test_target_view_is_independent_of_observed_evidence(tmp_path):
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
              transform: node.getAttribute('transform'),
              height: node.querySelector('.card')?.getAttribute('height'),
              text: [...node.querySelectorAll('text')].map(item => item.textContent).join(' | '),
              findingChips: node.querySelectorAll('.atlas-finding-chip').length,
              deviationChips: node.querySelectorAll('.atlas-deviation-chip').length
            }))""")
            assert all(item["findingChips"] == item["deviationChips"] == 0 for item in cards)
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
            target_views.append((root_sheet, cards, legend, component_sheet, module_sheet))
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
            panel = page.locator(".atlas-findings")
            for group in panel.locator(".atlas-finding-group").all():
                group.locator("summary").click()
            if lens != "Target":
                modules = page.locator(".atlas-module-list")
                modules.locator("summary").click()
                assert (
                    page.locator(".atlas-module-list")
                    .get_by_role("link", name="remove_none_or_empty_element_converter.py")
                    .count()
                    == 1
                )
            assert_visible_links_fit()
            page.locator(".flow-details-toggle").click()
            assert_visible_links_fit()
            page.locator(".flow-details-toggle").click()

        page.set_viewport_size({"width": 1440, "height": 900})
        page.get_by_role("button", name="Diff", exact=True).click()
        page.set_viewport_size({"width": 375, "height": 900})
        page.locator(".atlas-module-list summary").click()
        assert (
            page.locator(".atlas-module-list")
            .get_by_role("link", name="remove_none_or_empty_element_converter.py")
            .count()
            == 1
        )
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
            assert spacing["summaryTop"] >= spacing["breadcrumbBottom"] + 12
            assert spacing["canvasTop"] >= spacing["breadcrumbBottom"] + 12
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
                assert store_card.locator(".card").get_attribute("height") == "164"
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
        assert scene_ids() == {
            item.id
            for item in graph.entities
            if item.parent_id == module.id and item.kind == "class"
        }
        page.get_by_label("Element kind", exact=True).select_option("")
        page.locator(".flow-filters > summary").click()
        page.locator('.flow-legend [data-relationship-kind="inherits"]').click()
        assert (
            "in context"
            in page.locator('.flow-legend [data-relationship-kind="inherits"]').inner_text()
        )
        assert page.locator('.flow-nodes [data-label="Base"]').count() == 1
        assert page.locator(".flow-edges .hit").count() > 0
        page.locator('.flow-legend [data-relationship-kind=""]').click()
        assert scene_ids() == direct_ids(module.id)
        for name in ("Client", "State"):
            classifier = next(
                item
                for item in graph.entities
                if item.parent_id == module.id and item.qualified_name.endswith("." + name)
            )
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').click()
            page.locator(".flow-open-selected").click()
            assert scene_ids() == direct_ids(classifier.id)
            page.locator(".flow-back").click()
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
        page.goto(index.as_uri())
        page.locator(f'.flow-nodes [data-uml-id="{component_id}"]').dblclick()
        page.locator(".atlas-module-list > summary").click()
        page.locator(".atlas-module-list").get_by_role("link", name="core.py", exact=True).click()
        assert "component=unassigned" in page.url
        assert page.locator('.flow-nodes [data-label="Service"]').count() == 1
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert page.url.startswith(index.as_uri())
        assert "scope=" in page.url
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
        assert page.locator(".flow-canvas").is_visible()
        page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').press("Space")
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').press("Enter")
        assert "module=" + module.id in page.url and "scope=" + classifier.id in page.url
        page.goto(page.url)
        page.reload()
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        assert "Client [class]" in page.locator(".flow-breadcrumb").inner_text()
        page.locator(".flow-back").click()
        assert "scope=" + classifier.id not in page.url
        assert "selected=" + classifier.id in page.url
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        page.go_back()
        assert "scope=" + classifier.id in page.url
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        page.goto(page.url.replace(classifier.id, "unknown-native-id"))
        assert "scope=unknown-native-id" in page.url
        assert "not recorded inside this module" in page.locator(".flow-alternative").inner_text()
        assert page.locator(".flow-canvas").is_hidden()
        page.get_by_role("button", name="Open recorded module", exact=True).click()
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
        for identity, member in (("service", "run"), ("future", "execute")):
            page.locator(f'.flow-nodes [data-uml-id="{identity}"]').press("Enter")
            assert "origin=declared" in page.url and "scope=" + identity in page.url
            page.goto(page.url)
            page.reload()
            assert (
                page.get_by_role("button", name="Target", exact=True).get_attribute("aria-pressed")
                == "true"
            )
            assert page.locator(f'.flow-nodes [data-uml-id="{member}"]').count() == 1
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
            page.locator(".flow-back").click()
            assert "origin=declared" in page.url and "selected=" + identity in page.url
            assert (
                page.locator(f'.flow-nodes [data-uml-id="{identity}"]').get_attribute(
                    "aria-pressed"
                )
                == "true"
            )
        page.goto(index.as_uri() + "?scope=core&view=target&theme=dark")
        page.locator('.flow-nodes [data-uml-id="declared-module"]').press("Enter")
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
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() > 0
        page.goto(index.as_uri() + "?scope=not-a-component&theme=dark")
        assert "scope=not-a-component" in page.url
        assert "not recorded in this snapshot" in page.locator(".flow-alternative").inner_text()
        page.get_by_role("button", name="Open architecture map", exact=True).click()
        assert "scope=not-a-component" not in page.url
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
        assert page.locator('.flow-nodes [data-label="core.py"]').is_visible()
        page.locator('.flow-nodes [data-label="__init__.py"]').press("Enter")
        assert "No direct declarations" in page.locator(".flow-alternative").inner_text()
        assert "sample/__init__.py" in page.locator(".flow-alternative").inner_text()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        page.get_by_role("button", name="Target", exact=True).click()
        assert "No declared modules" in page.locator(".flow-alternative").inner_text()
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() == 0
        page.get_by_role("button", name="Show As-Is modules", exact=True).click()
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
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() > 0
        page.reload()
        assert "content=modules" in page.url
        page.get_by_role("button", name="Diff", exact=True).click()
        assert "content=modules" in page.url and "view=diff" in page.url
        choice.get_by_role("button", name=re.compile("^Components")).click()
        assert "content=components" in page.url and page.locator(".flow-canvas").is_visible()
        page.go_back()
        assert "content=modules" in page.url and page.locator(".flow-canvas").is_visible()
        page.locator('.flow-nodes [data-uml-kind="module"]').first.press("Enter")
        assert "return_content=modules" in page.url
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "scope=ROOT" in page.url and "content=modules" in page.url
        assert "view=diff" in page.url and "theme=dark" in page.url
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
