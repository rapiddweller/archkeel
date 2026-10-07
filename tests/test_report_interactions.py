# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared report navigation remains usable without the retired frame renderer."""

import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo
from test_atlas_report import _atlas
from test_atlas_report import _page as _atlas_page
from test_atlas_report import _result as _atlas_result
from test_module_explore import _sample
from test_report_159_160_e2e_oracle import _variant
from test_target_graph import _nested_repository
from test_uml_rendering import _open_module, _uml_report

from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import Relationship
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.model import stable_id
from archkeel.render.html import _atlas_document, render_architecture_html


def test_atlas_labels_count_scopes_and_oversized_evidence_without_losing_route_state(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    positive = _sample(
        tmp_path / "positive",
        extra_files={
            "sample/core/helper.py": "def one():\n    return 1\n",
            "sample/core/helper2.py": "def two():\n    return 2\n",
        },
    )
    empty = _sample(tmp_path / "empty")
    unavailable_model = replace(
        empty,
        sections=tuple(section for section in empty.sections if section.name != "dependency_edges"),
    )
    unavailable = _atlas_document(
        _atlas_result(unavailable_model),
        unavailable_model,
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    assert _atlas(unavailable)["oversized_insides"]["status"] == "UNKNOWN"
    cases = (
        (_atlas_page(positive), "1 candidate", "core\t3\t0"),
        (_atlas_page(empty), "no candidates measured", None),
        (unavailable, "UNKNOWN", None),
    )
    for index, (html, claim_label, measurement) in enumerate(cases):
        report = tmp_path / f"atlas-{index}.report.html"
        report.write_text(html)
        errors = []
        playwright, browser, page = _browser_page(api, html, errors=errors)
        try:
            page.goto(f"{report.as_uri()}?view=target&theme=dark")
            assert "whole-contract components" in page.locator(".report-heading").inner_text()
            summary = page.locator(".atlas-summary").inner_text()
            assert "Current level: 2 components" in summary
            assert "agent-authored contract entries (authorship only): 0/2 components" in summary
            claim = page.locator(".atlas-review-claim")
            assert claim.locator("summary").inner_text().endswith(claim_label)
            claim.locator("summary").click()
            if measurement:
                assert measurement in claim.inner_text()
                link = claim.get_by_role("link", name="core")
                link.click()
                query = parse_qs(urlsplit(page.url).query)
                assert query["component"] == ["core"]
                assert query["view"] == ["target"]
                assert query["theme"] == ["dark"]
                assert page.locator("html").get_attribute("data-theme") == "dark"
            else:
                assert claim.locator("table").count() == 0
            assert not errors
        finally:
            browser.close()
            playwright.stop()


def test_atlas_unknown_rule_links_its_analyzer_gap_while_failures_remain_visible(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    config = load_config(root, variant.config)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None and result.declared_rules == "UNKNOWN"
    html = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    unknown = next(item for item in atlas["rule_assessments"] if item["status"] == "UNKNOWN")
    assert any(entry["evidence_class"] == "UNKNOWN" for entry in unknown["evidence"])
    component = next(item for item in atlas["components"] if item["label"] in unknown["components"])
    report = tmp_path / "atlas-unknown.report.html"
    report.write_text(html)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.goto(f"{report.as_uri()}?view=diagram&theme=dark")
        assert page.locator('.flow-nodes [data-uml-id="' + component["id"] + '"]').count() == 1
        page.locator('.flow-nodes [data-uml-id="' + component["id"] + '"]').press("Space")
        inspector = page.locator(".flow-inspector-content")
        inspector.locator(".atlas-rule-assessments summary").click()
        assert unknown["id"] in inspector.inner_text()
        assert "Analyzer limitation" in inspector.inner_text()
        assert "boundary_type_route" in inspector.inner_text()
        assert "UNKNOWN" in page.locator(".decision-banner").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_unknown_ownership_gap_points_to_the_required_decision(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    observed = _sample(tmp_path)
    model = replace(
        observed,
        sections=tuple(
            replace(section, records=()) if section.name == "violations" else section
            for section in observed.sections
        ),
    )
    result = replace(_atlas_result(model), declared_rules="UNKNOWN")
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    atlas = _atlas(html)
    unknown = next(item for item in atlas["rule_assessments"] if item["status"] == "UNKNOWN")
    assert any(entry["kind"] == "rule_ownership_blocker" for entry in unknown["evidence"])
    component = atlas["components"][0]
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator(f'.flow-nodes [data-uml-id="{component["id"]}"]').press("Space")
        inspector = page.locator(".flow-inspector-content")
        inspector.locator(".atlas-rule-assessments summary").click()
        assert "Ownership decision needed" in inspector.inner_text()
        assert "Assign it to one existing component" in inspector.inner_text()
        assert "code changes alone" not in inspector.inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_atlas_whole_contract_and_nested_level_counts_have_distinct_scopes(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None and result.architecture_projection is not None
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    components = atlas["components"]
    parent = next(
        item for item in components if any(child["parent_id"] == item["id"] for child in components)
    )
    children = [item for item in components if item["parent_id"] == parent["id"]]
    roots = [item for item in components if item["parent_id"] is None]
    report = tmp_path / "nested.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?view=target&theme=dark")
        assert (
            f"{len(components)} whole-contract components"
            in page.locator(".report-heading").inner_text()
        )
        root_count = len(roots)
        root_label = "component" if root_count == 1 else "components"
        assert (
            f"Current level: {root_count} {root_label}"
            in page.locator(".atlas-summary").inner_text()
        )
        page.goto(f"{report.as_uri()}?view=target&component={parent['id']}&theme=dark")
        assert (
            f"{len(components)} whole-contract components"
            in page.locator(".report-heading").inner_text()
        )
        child_count = len(children)
        child_label = "component" if child_count == 1 else "components"
        assert (
            f"Current level: {child_count} {child_label}"
            in page.locator(".atlas-summary").inner_text()
        )
    finally:
        browser.close()
        playwright.stop()


def test_atlas_unperformed_check_is_only_a_legend_definition(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    model = _sample(tmp_path)
    result = replace(
        _atlas_result(model),
        observation_complete="UNKNOWN",
        declared_rules="UNKNOWN",
        rule_assessments=None,
    )
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    playwright, browser, page = _browser_page(api, html)
    try:
        card = page.locator(".verdict-card").nth(3)
        assert "NOT CHECKED" in card.inner_text()
        assert "Status definition" in card.inner_text()
        assert "A check was not performed or could not be completed" in card.inner_text()
        assert "Count unavailable" not in card.inner_text()
        assert "0 rules" not in card.inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_equal_root_diagram_uses_one_viewport_alignment_in_every_architecture_view(
    tmp_path, width, height
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html, width, height)
    try:
        geometry = []
        for name in ("As-Is", "Target", "Diff", "As-Is"):
            page.get_by_role("button", name=name, exact=True).click()
            card = page.locator('.flow-nodes [data-label="core"] .card')
            assert card.count() == 1
            box = card.bounding_box()
            canvas = page.locator(".flow-canvas").bounding_box()
            geometry.append(
                {
                    "x": box["x"] - canvas["x"],
                    "y": box["y"] - canvas["y"],
                    "width": box["width"],
                    "height": box["height"],
                }
            )
        for box in geometry[1:]:
            assert box == pytest.approx(geometry[0], abs=1)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_architecture_views_are_grouped_separately_from_evidence_views(tmp_path, width, height):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html, width, height)
    try:
        architecture = page.get_by_role("group", name="Architecture diagrams", exact=True)
        evidence = page.get_by_role("group", name="Evidence views", exact=True)
        assert architecture.locator("button").all_text_contents() == ["As-Is", "Target", "Diff"]
        assert evidence.locator("button").all_text_contents() == ["Structure", "Review", "Actual"]
        for name in ("Target", "Diff", "Review", "As-Is"):
            page.get_by_role("button", name=name, exact=True).click()
            assert (
                page.get_by_role("button", name=name, exact=True).get_attribute("aria-pressed")
                == "true"
            )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_scope_selection_and_geometry_survive_view_switch_and_resize(tmp_path, view, width, height):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width, height, errors)
    try:
        _open_module(page, view)
        payload = page.locator("#flow-data").text_content()
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.click()
        identity = client.get_attribute("data-uml-id")
        scope = page.locator(".flow-breadcrumb").inner_text()
        page.get_by_role("button", name=view, exact=True).click()
        assert client.get_attribute("aria-pressed") == "true"
        page.get_by_role(
            "button", name="Target" if view != "Target" else "As-Is", exact=True
        ).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert page.locator(".flow-breadcrumb").inner_text() == scope
        assert client.get_attribute("data-uml-id") == identity
        assert client.get_attribute("aria-pressed") == "true"
        transform = client.get_attribute("transform")
        page.set_viewport_size({"width": width + 40, "height": height + 60})
        assert client.get_attribute("transform") == transform
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        _open_details(page)
        assert "Client" in page.locator(".flow-inspector-content").inner_text()
        assert (
            client.locator(".label").evaluate("n => getComputedStyle(n).writingMode")
            == "horizontal-tb"
        )
        assert page.locator(".flow-frames [tabindex]").count() == 0
        assert page.locator(".flow-chips [tabindex]").count() == 0
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_fail_with_undecided_and_mixed_evidence_keeps_all_actions(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    config = load_config(root, variant.config)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assessment = next(item for item in result.rule_assessments if item.status == "UNKNOWN")
    ownership_model = _sample(tmp_path / "ownership")
    blocker = next(
        item
        for item in ownership_model.records("scope_observations") or ()
        if item.kind == "rule_ownership_blocker"
    )
    sections = tuple(
        replace(
            section,
            records=(
                *section.records,
                replace(
                    blocker,
                    id=stable_id("scope-observation", assessment.id, blocker.id),
                    rule_ids=(assessment.id,),
                ),
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in model.sections
    )
    model = replace(model, sections=sections)
    result = replace(
        result,
        rule_assessments=tuple(
            replace(item, status="FAIL", undecided=1) if item.id == assessment.id else item
            for item in result.rule_assessments
        ),
    )
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()
    report = tmp_path / "atlas-mixed-evidence.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark")
        page.locator(".flow-inspector-content .atlas-rule-assessments summary").click()
        inspector = page.locator(".flow-inspector-content")
        assert assessment.id in inspector.inner_text()
        assert "FAIL" in inspector.inner_text()
        assert "undecided result" in inspector.inner_text()
        assert "Analyzer limitation" in inspector.inner_text()
        assert "Ownership decision needed" in inspector.inner_text()
        assert "Assign it to one existing component" in inspector.inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_atlas_nested_rule_scope_link_uses_parent_identity_with_duplicate_labels(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    inside_path = root / "inside.json"
    inside = json.loads(inside_path.read_text())
    inside["components"][0]["label"] = "core"
    inside_path.write_text(json.dumps(inside))
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    assessment = next(item for item in result.rule_assessments if item.id == "core:layout")
    result = replace(
        result,
        rule_assessments=tuple(
            replace(item, status="UNKNOWN", undecided=1) if item.id == assessment.id else item
            for item in result.rule_assessments
        ),
    )
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    parent = next(
        item
        for item in atlas["components"]
        if item["label"] == "core" and item["parent_id"] is None
    )
    child = next(
        item
        for item in atlas["components"]
        if item["label"] == "core" and item["parent_id"] == parent["id"]
    )
    report = tmp_path / "atlas-nested-rule.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark")
        page.locator(f'.flow-nodes [data-uml-id="{parent["id"]}"]').press("Space")
        rules = page.locator(".flow-inspector-content .atlas-rule-assessments")
        rules.locator("summary").click()
        link = rules.get_by_role("link", name="core", exact=True).first
        assert f"component={child['id'].replace(':', '%3A')}" in link.get_attribute("href")
        link.click()
        query = parse_qs(urlsplit(page.url).query)
        assert query["component"] == [child["id"]]
        assert page.locator("html").get_attribute("data-theme") == "dark"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("reject", [False, True])
@pytest.mark.parametrize("width", [375, 1024])
def test_fullscreen_fallback_restores_scope_selection_focus_and_scroll(tmp_path, reject, width):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=width, height=844, errors=errors)
    try:
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').click()
        before = page.locator(".flow-breadcrumb").inner_text()
        selected = page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
        page.evaluate("window.scrollTo(0, 100)")
        page.evaluate(
            """reject => {
          Element.prototype.requestFullscreen = reject
            ? async () => { throw new DOMException('embedding denied', 'NotAllowedError'); }
            : undefined;
        }""",
            reject,
        )
        page.locator(".flow-fullscreen").scroll_into_view_if_needed()
        scroll = page.evaluate("window.scrollY")
        page.locator(".flow-fullscreen").click()
        assert page.locator("#flow").get_attribute("data-expanded") == "fallback"
        assert page.locator("#flow").get_attribute("aria-modal") == "true"
        bounds = page.locator(".flow-canvas").bounding_box()
        assert bounds and bounds["height"] >= 200
        page.keyboard.press("Escape")
        assert page.locator("#flow").get_attribute("data-expanded") is None
        assert page.locator("#flow").get_attribute("aria-modal") is None
        assert page.locator(".flow-breadcrumb").inner_text() == before
        assert (
            page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
            == selected
        )
        assert page.evaluate("window.scrollY") == scroll
        assert page.locator(".flow-fullscreen").evaluate("n => n === document.activeElement")
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_native_card_drag_reroutes_all_hits_and_keeps_architecture_unchanged(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        canvas = page.locator(".flow-canvas")
        canvas.scroll_into_view_if_needed()
        payload = page.locator("#flow-data").text_content()
        card = page.locator('.flow-nodes [data-label="Client"]')
        box = card.bounding_box()
        before = card.get_attribute("transform")
        assert box
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 40, y + 30, steps=4)
        page.mouse.up()
        assert card.get_attribute("transform") != before
        assert page.locator(".flow-edges .line").count()
        assert page.locator(".flow-edges .edge").evaluate_all("""edges => edges.every(edge =>
          edge.querySelector('.line').getAttribute('d')
          === edge.querySelector('.hit').getAttribute('d')
          && getComputedStyle(edge.querySelector('.line')).markerEnd !== 'none')""")
        page.get_by_role("button", name="Fit overview").click()
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("zoom_steps", [0, 2, 4])
def test_left_up_drag_keeps_other_cards_fixed_and_small_scope_starts_unscrolled(
    tmp_path, view, zoom_steps
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        for _ in range(zoom_steps):
            page.get_by_role("button", name="Zoom in", exact=True).click()
        payload = page.locator("#flow-data").text_content()
        client = page.locator('.flow-nodes [data-label="Client"]')
        other = page.locator('.flow-nodes [data-label="Other"]')
        canvas = page.locator(".flow-canvas")
        canvas.scroll_into_view_if_needed()
        before = client.get_attribute("transform")
        anchor = other.bounding_box()
        box = client.bounding_box()
        viewport = canvas.bounding_box()
        assert anchor and box and viewport
        page.mouse.move(box["x"] + 40, box["y"] + 35)
        page.mouse.down()
        page.mouse.move(viewport["x"] + 8, viewport["y"] + 8, steps=32)
        page.mouse.up()
        assert client.get_attribute("transform") != before
        after = other.bounding_box()
        assert after
        assert abs(after["x"] - anchor["x"]) < 1
        assert abs(after["y"] - anchor["y"]) < 1
        assert page.locator(".flow-edges .edge").evaluate_all("""edges => edges.every(edge =>
          edge.querySelector('.line').getAttribute('d')
          === edge.querySelector('.hit').getAttribute('d')
          && getComputedStyle(edge.querySelector('.line')).markerEnd !== 'none')""")
        client.press("Space")
        for _ in range(4):
            page.get_by_role("button", name="Zoom in", exact=True).click()
        scroll = canvas.evaluate(
            """n => {
                n.scrollLeft=n.scrollWidth;
                n.scrollTop=n.scrollHeight;
                return [n.scrollLeft,n.scrollTop];
            }"""
        )
        assert max(scroll) > 0
        page.get_by_role("button", name="Open selected Client", exact=True).click()
        assert canvas.evaluate("n => [n.scrollLeft,n.scrollTop]") == [0, 0]
        assert page.locator('.flow-nodes [data-uml-kind="method"]').count() > 0
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("input_method", ["mouse", "keyboard"])
@pytest.mark.parametrize("width", [375, 1000])
def test_opening_details_reveals_selected_card_without_changing_scene(
    tmp_path, view, input_method, width
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=width, height=1000, errors=errors)
    try:
        _open_module(page, view)
        details = page.locator(".flow-details-toggle")
        if details.get_attribute("aria-expanded") == "true":
            details.click()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        cards = page.locator(".flow-nodes [data-uml-id]")
        rightmost = max(range(cards.count()), key=lambda i: cards.nth(i).bounding_box()["x"])
        card = cards.nth(rightmost)
        card.focus()
        scene = page.locator(".flow-nodes [data-uml-id]").evaluate_all(
            "nodes => nodes.map(n => [n.dataset.umlId,n.getAttribute('transform')])"
        )
        routes = page.locator(".flow-edges .line").evaluate_all(
            "edges => edges.map(e => e.getAttribute('d'))"
        )
        zoom = page.locator(".flow-zoom-value").inner_text()
        payload = page.locator("#flow-data").text_content()
        if input_method == "mouse":
            card.click()
        else:
            card.press("Space")
        assert details.get_attribute("aria-expanded") == "true"
        bounds = card.bounding_box()
        viewport = page.locator(".flow-canvas").bounding_box()
        assert bounds and viewport
        assert bounds["x"] >= viewport["x"] - 1
        assert bounds["x"] + bounds["width"] <= viewport["x"] + viewport["width"] + 1
        assert bounds["y"] >= viewport["y"] - 1
        assert bounds["y"] + bounds["height"] <= viewport["y"] + viewport["height"] + 1
        assert page.locator(".flow-zoom-value").inner_text() == zoom
        assert (
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(n => [n.dataset.umlId,n.getAttribute('transform')])"
            )
            == scene
        )
        assert (
            page.locator(".flow-edges .line").evaluate_all(
                "edges => edges.map(e => e.getAttribute('d'))"
            )
            == routes
        )
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_keyboard_back_restores_the_open_component(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.focus()
        client.press("Enter")
        page.locator(".flow-back").click()
        assert client.is_visible()
        assert client.evaluate("n => n === document.activeElement")
        client.press("Space")
        assert client.get_attribute("aria-pressed") == "true"
        client.press("Escape")
        assert client.get_attribute("aria-pressed") == "false"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("touch", [False, True])
def test_blocked_route_keeps_accessible_warning_endpoints_and_evidence(tmp_path, touch):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(
        tmp_path,
        extra_target_relationships=(
            Relationship(
                "reference", "references", "client", "other", provenance=("docs/target.md",)
            ),
        ),
    )
    playwright, browser, page = _browser_page(api, html, has_touch=touch)
    try:
        _open_module(page, "Target")
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        page.locator(".flow-canvas").scroll_into_view_if_needed()
        payload = page.locator("#flow-data").text_content()
        for label, dx, dy in (("Base", 10, 20), ("Port", -10, -20)):
            client = page.locator('.flow-nodes [data-label="Client"] .card').bounding_box()
            blocker = page.locator(f'.flow-nodes [data-label="{label}"] .card').bounding_box()
            assert client and blocker
            x, y = blocker["x"] + 40, blocker["y"] + 35
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(
                x + client["x"] - blocker["x"] + dx, y + client["y"] - blocker["y"] + dy, steps=4
            )
            page.mouse.up()
        warnings = page.locator(".flow-edges .hit[data-route-warning]")
        assert warnings.count() > 0
        assert "routing warnings" in page.locator(".flow-legend").inner_text()
        edge = page.locator(
            '.flow-edges [data-relationship-kind="references"] .hit[data-route-warning]'
        )
        assert edge.count() == 1
        assert "architectural status is unchanged" in edge.get_attribute("aria-label")
        assert edge.get_attribute("d") == edge.locator("..").locator(".line").get_attribute("d")
        edge.press("Enter")
        assert (
            "Renderer layout warning"
            in page.locator(".flow-inspector-content [role=status]").inner_text()
        )
        assert page.locator("#flow-data").text_content() == payload
        if touch:
            point = edge.evaluate("""node => {
              const matrix = node.getScreenCTM(), length = node.getTotalLength();
              for (let fraction = .1; fraction < .95; fraction += .05) {
                const point = node.getPointAtLength(length * fraction).matrixTransform(matrix);
                if (document.elementFromPoint(point.x, point.y)?.closest('.hit') === node)
                  return {x: point.x, y: point.y};
              }
              return null;
            }""")
            assert point
            page.touchscreen.tap(point["x"], point["y"])
            assert edge.get_attribute("aria-pressed") == "true"
            assert "Renderer layout warning" in page.locator(".flow-inspector-content").inner_text()
            assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_mobile_check_wraps_long_failure_identity_without_changing_result(scheme):
    from dataclasses import replace

    from test_html_report import FAILED_CHECK

    from archkeel.render.html import render_check_html

    api = pytest.importorskip("playwright.sync_api")
    identity = "8ef830a60aba1c9fee50741b004956eafcfe09cf614f86c77ddf48971c36505b"
    result = replace(FAILED_CHECK, failures=(f"guardrail changed unknowns fingerprint {identity}",))
    html = render_check_html(result, repository="sample", result_href="result.json").decode()
    playwright, browser, page = _browser_page(api, html, width=375, height=844)
    try:
        page.emulate_media(color_scheme=scheme)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator(".failure-list code").inner_text().endswith(identity)
        assert (
            page.locator(".verdict-card")
            .filter(has=page.locator(".verdict-key", has_text="expectation_fulfilled"))
            .get_attribute("data-verdict")
            == "fail"
        )
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_native_theme_keeps_target_cards_readable_and_evidence_unchanged(tmp_path, scheme):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=375, height=844, errors=errors)
    try:
        page.emulate_media(color_scheme=scheme)
        before = page.locator("#flow-data").text_content()
        assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == scheme
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').click()
        colors = page.locator(".flow-nodes .node").evaluate_all(r"""nodes => {
          const rgb = s => s.match(/[\d.]+/g).slice(0,3).map(Number);
          const luminance = c => c.map(v => {v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})
            .reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
          const contrast = (a,b) => (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
          return nodes.filter(n => n.getBoundingClientRect().width).map(n => {
            const label=n.querySelector('.label'), card=n.querySelector('.card');
            return contrast(luminance(rgb(getComputedStyle(label).fill)),
              luminance(rgb(getComputedStyle(card).fill)));
          });
        }""")
        assert colors and min(colors) >= 4.5
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#flow-data").text_content() == before
        assert not errors
    finally:
        browser.close()
        playwright.stop()
