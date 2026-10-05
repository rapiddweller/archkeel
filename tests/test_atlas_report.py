# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re

import pytest
from browser_report_support import _browser_page
from test_module_explore import _sample

from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.model import RunResult
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


def _atlas(page):
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))["atlas"]
    data["cells"] = [
        dict(
            zip(
                (
                    "source_id",
                    "target_id",
                    "import_sites",
                    "status",
                    "permission",
                    "permission_reason",
                    "evidence_ids",
                    "finding_ids",
                    "reasons",
                ),
                (data["modules"][row[0]]["id"], data["modules"][row[1]]["id"], *row[2:]),
                strict=True,
            )
        )
        for row in data["cells"]
    ]
    data["assignments"] = [
        dict(
            zip(
                ("id", "component_id", "candidate_ids", "ownership_status", "ownership_reason"),
                (data["modules"][row[0]]["id"], *row[1:4], data["reference_ids"][row[4]]),
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
    assert data["source"]["git_head"] == model.source.git_head
    assert data["source"]["source_digest"] == model.source.source_digest
    assert {item["id"] for item in data["components"]} == {"core", "peer"}
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


def test_component_detail_links_are_relative_and_keep_shared_uml(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    encoded = canonical_report_bytes(model)
    result = _result(model)
    details = render_architecture_details(
        result, encoded, repository="One target", architecture_href="architecture.json"
    )
    data = _atlas(_page(model))
    assert len(details) >= 2
    for component in data["components"]:
        href = component["detail_href"]
        assert "/" not in href and href.endswith(".html")
        page = details[href].decode()
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
            assert page.locator(".flow-canvas").bounding_box()["y"] < 370
        position = card.get_attribute("transform")
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert card.get_attribute("transform") == position
        page.locator('.flow-matrix [data-cell="0"]').click()
        assert "Permission: UNKNOWN" in page.locator(".flow-inspector-content").inner_text()
        assert "FAIL" in page.locator(".flow-inspector-content").inner_text()
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
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.core", exact=True
        ).click()
        assert page.url.startswith("file:") and "?module=" in page.url
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
        assert page.url == index.as_uri()
        assert "Architecture map" == page.locator("#flow-heading").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_component_details_retain_outside_method_classifier_context(tmp_path):
    from archkeel.render.atlas import detail_report

    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "from sample.peer import Client\nClient.run()\n",
            "sample/peer.py": (
                "class Client:\n    @staticmethod\n    def run() -> int:\n        return 1\n"
            ),
        },
    )
    report = architecture_report(model)
    methods = {entity.id for entity in report.observed.entities if entity.kind == "method"}
    assert any(
        edge.kind == "calls" and edge.target_id in methods for edge in report.observed.relationships
    )
    scoped = detail_report(report, "core")
    scoped.validate()
    method = next(entity for entity in scoped.observed.entities if entity.kind == "method")
    classifier = next(
        entity for entity in scoped.observed.entities if entity.id == method.parent_id
    )
    assert classifier.kind == "class" and classifier.qualified_name == "sample.peer.Client"


def test_nested_detail_scope_retains_authentic_component_ancestors(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.render.atlas import detail_report

    root, config = _nested_repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    report = architecture_report(parse_observation(decode_canonical_model(json.loads(encoded))))
    assert any(intent.parent_id for intent in report.target.component_intents)
    for intent in report.target.component_intents:
        scoped = detail_report(report, intent.component_id)
        scoped.validate()
        ids = {item.component_id for item in scoped.target.component_intents}
        assert intent.component_id in ids
        if intent.parent_id:
            assert intent.parent_id in ids
