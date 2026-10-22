# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""ArchQ Explorer is the default, offline architecture report."""

from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

import pytest
from browser_report_support import _browser_page, _open_details
from test_atlas_report import _page, _result
from test_module_explore import _sample
from test_uml_rendering import _wait_for_layout

from archkeel.ir.codec import canonical_report_bytes
from archkeel.render.html import render_architecture_details


@pytest.fixture
def explorer(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    model = _sample(tmp_path, uml=True, other_component=True)
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
    playwright, browser, page = _browser_page(api, "", errors=errors)
    page.goto(index.as_uri())
    _wait_for_layout(page)
    try:
        yield page, index
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_explorer_is_default_and_keeps_architecture_evidence(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    document = _page(_sample(tmp_path))
    errors = []
    playwright, browser, page = _browser_page(api, document, errors=errors)
    try:
        _wait_for_layout(page)
        assert page.locator("html").evaluate("e => e.classList.contains('ak-canvas')")
        assert "ArchQ Explorer" in page.title()
        assert page.locator(".ak-brand").inner_text() == "ArchQ Explorer"
        assert page.locator(".ak-brand").is_visible()
        assert page.get_by_role("button", name="Search", exact=True).is_visible()
        assert page.get_by_role("button", name="Target", exact=True).is_visible()
        assert page.get_by_role("button", name="Diff", exact=True).is_visible()
        assert page.locator(".report-heading").is_visible()
        assert page.locator(".verdict-line").is_visible()
        assert page.locator("#flow").evaluate("e => getComputedStyle(e).position") == "relative"
        assert page.get_by_role("button", name="Fullscreen", exact=True).is_visible()
        assert page.get_by_role("button", name="Report evidence", exact=True).count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_search_selects_components_rules_and_declared_modules(explorer):
    page, _ = explorer
    page.get_by_role("button", name="Search", exact=True).click()
    search = page.get_by_role("combobox", name="Search", exact=True)
    search.fill("peer")
    search.press("Enter")
    assert parse_qs(urlsplit(page.url).query)["selected"] == ["peer"]
    assert page.locator('.flow-nodes [data-uml-id="peer"]').get_attribute("aria-pressed") == "true"
    page.keyboard.press("/")
    search.fill("dependencies")
    search.press("Enter")
    assessment = page.locator("#atlas-assessment-dependencies")
    assert assessment.is_visible()
    assert "FAIL" in assessment.inner_text()
    page.get_by_role("button", name="Target", exact=True).click()
    page.keyboard.press("/")
    search.fill("core")
    page.get_by_role("option").filter(has=page.locator(".ak-kind", has_text="M")).click()
    _wait_for_layout(page)
    query = parse_qs(urlsplit(page.url).query)
    assert query["module"] == ["core-module"]
    assert query["origin"] == ["declared"]
    assert "Requested scope unavailable" not in page.locator("body").inner_text()
    assert urlsplit(page.url).path.endswith("architecture.detail.html")
    assert page.locator(".ak-brand").is_visible()
    assert not page.locator(".flow-toolbar").is_visible()
    page.get_by_role("button", name="Search", exact=True).click()
    assert page.get_by_role("combobox").get_attribute("placeholder") == "Search this diagram"
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Legend", exact=True).click()
    assert page.locator(".ak-pop .flow-legend").is_visible()
    page.keyboard.press("Escape")
    page.locator(".flow-filters > summary").click()
    page.get_by_role("button", name="Reset and fit", exact=True).click()
    page.locator(".flow-filters > summary").click()
    page.get_by_role("button", name="Fullscreen", exact=True).click()
    pytest.importorskip("playwright.sync_api").expect(page.locator("#flow")).to_have_attribute(
        "data-expanded", "native"
    )
    page.get_by_role("button", name="Restore", exact=True).click()
    page.get_by_role("link", name="Back to architecture map", exact=True).click()
    _wait_for_layout(page)
    assert page.locator(".ak-brand").is_visible()


def test_dialog_keyboard_and_object_sorting(explorer):
    page, _ = explorer
    trigger = page.get_by_role("button", name="Search", exact=True)
    trigger.click()
    search = page.get_by_role("combobox", name="Search", exact=True)
    search.fill("no such component")
    search.press("p")
    assert search.input_value().endswith("p")
    assert (
        page.get_by_role("button", name="None", exact=True).get_attribute("aria-pressed") == "true"
    )
    assert not search.get_attribute("aria-activedescendant")
    search.press("Tab")
    assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert trigger.evaluate("e => e === document.activeElement")
    page.keyboard.press("o")
    table = page.locator(".ak-table")
    table.get_by_role("button", name="Component").press("Enter")
    assert (
        table.get_by_role("columnheader", name="Component").get_attribute("aria-sort")
        == "descending"
    )
    assert table.locator("tbody tr td:first-child").all_text_contents() == ["peer", "other", "core"]
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Share", exact=True).click()
    page.keyboard.press("End")
    assert page.get_by_role("menuitem", name="Download SVG").evaluate(
        "e => e === document.activeElement"
    )
    page.keyboard.press("Escape")
    assert page.get_by_role("button", name="Share", exact=True).evaluate(
        "e => e === document.activeElement"
    )
    page.get_by_role("button", name="Health check", exact=True).click()
    trigger.click()
    search.press("Escape")
    assert page.locator(".ak-drawer").is_visible()
    page.keyboard.press("Escape")
    assert page.locator(".ak-drawer").count() == 0


def test_perspective_history_and_hover_preserve_verdicts(explorer):
    page, _ = explorer
    statuses = page.locator(".atlas-rule-status").all_text_contents()
    peer = page.locator('.flow-nodes [data-uml-id="peer"]')
    peer.hover()
    assert page.locator('.flow-nodes [data-uml-id="other"]').evaluate(
        "e => e.classList.contains('dim')"
    )
    assert not page.locator('.flow-nodes [data-uml-id="core"]').evaluate(
        "e => e.classList.contains('dim')"
    )
    page.get_by_role("button", name="Decided by", exact=True).click()
    page.keyboard.press("/")
    page.get_by_role("combobox").fill("peer")
    page.get_by_role("combobox").press("Enter")
    page.get_by_role("button", name="Evidence", exact=True).click()
    assert parse_qs(urlsplit(page.url).query)["perspective"] == ["evidence"]
    page.go_back()
    _wait_for_layout(page)
    assert (
        page.get_by_role("button", name="Decided by", exact=True).get_attribute("aria-pressed")
        == "true"
    )
    page.get_by_role("button", name="Zoom in", exact=True).click()
    assert page.locator(".atlas-rule-status").all_text_contents() == statuses


def test_zoom_stays_under_pointer_and_middle_drag_pans(explorer):
    page, _ = explorer
    canvas = page.locator(".flow-canvas")
    box = canvas.bounding_box()
    point = {"x": box["x"] + box["width"] * 0.65, "y": box["y"] + box["height"] * 0.4}
    world = page.evaluate(
        """p => {
          const matrix = document.querySelector('.flow-viewport').getScreenCTM();
          const q = new DOMPoint(p.x, p.y).matrixTransform(matrix.inverse());
          return {x:q.x,y:q.y};
        }""",
        point,
    )
    for delta in (-260, 140):
        canvas.dispatch_event(
            "wheel",
            {"deltaY": delta, "ctrlKey": True, "clientX": point["x"], "clientY": point["y"]},
        )
        after = page.evaluate(
            """p => {
              const matrix = document.querySelector('.flow-viewport').getScreenCTM();
              const q = new DOMPoint(p.x, p.y).matrixTransform(matrix);
              return {x:q.x,y:q.y};
            }""",
            world,
        )
        assert abs(after["x"] - point["x"]) <= 2
        assert abs(after["y"] - point["y"]) <= 2
    peer = page.locator('.flow-nodes [data-uml-id="peer"]')
    position = peer.get_attribute("transform")
    before = page.locator(".flow-viewport").get_attribute("transform")
    peer.hover()
    mouse = peer.bounding_box()
    page.mouse.down(button="middle")
    page.mouse.move(mouse["x"] + 60, mouse["y"] + 80, steps=4)
    page.mouse.up(button="middle")
    assert peer.get_attribute("transform") == position
    assert page.locator(".flow-viewport").get_attribute("transform") != before


def test_perspective_and_tag_activation_keep_keyboard_focus(explorer):
    page, _ = explorer
    perspective = page.get_by_role("button", name="Decided by", exact=True)
    perspective.focus()
    perspective.press("Enter")
    assert perspective.evaluate("e => e === document.activeElement")
    tag = page.locator(".ak-chip").first
    tag.focus()
    tag.press("Enter")
    assert tag.evaluate("e => e === document.activeElement")
    assert tag.get_attribute("aria-pressed") == "true"


def test_space_pan_does_not_scroll_an_overflowing_detail_diagram(explorer):
    page, index = explorer
    page.set_viewport_size({"width": 844, "height": 390})
    module = page.evaluate("ArchkeelFlow.atlas.modules.find(m => m.name === 'sample.core').id")
    page.goto(index.with_name("architecture.detail.html").as_uri() + f"?module={module}")
    _wait_for_layout(page)
    page.get_by_role("button", name="Fullscreen", exact=True).click()
    zoom = page.get_by_role("button", name="Zoom in", exact=True)
    for _ in range(12):
        zoom.click()
    canvas = page.locator(".flow-canvas")
    assert canvas.evaluate("e => e.scrollHeight > e.clientHeight")
    canvas.focus()
    canvas.evaluate("e => e.scrollTop = 0")
    page.keyboard.press("Space", delay=300)
    assert canvas.evaluate("e => e.scrollTop") == 0
    before = page.evaluate("ArchkeelFlow.state().zoom")
    page.get_by_role("button", name="Zoom out", exact=True).press("Space")
    assert page.evaluate("ArchkeelFlow.state().zoom") < before


def test_perspective_pin_clears_on_untagged_modules_and_invalid_urls(explorer):
    page, index = explorer
    page.get_by_role("button", name="Decided by", exact=True).click()
    page.locator(".ak-chip").first.click()
    page.get_by_role("button", name="Modules (").click()
    _wait_for_layout(page)
    assert page.locator(".flow-nodes .ak-dim").count() == 0
    for value in ("constructor", "__proto__", "toString", "unknown"):
        page.goto(index.as_uri() + f"?perspective={value}")
        _wait_for_layout(page)
        assert (
            page.get_by_role("button", name="None", exact=True).get_attribute("aria-pressed")
            == "true"
        )


def test_existing_finding_links_open_visible_health_check(explorer):
    page, index = explorer
    page.goto(index.as_uri() + "#atlas-rule-dependencies")
    _wait_for_layout(page)
    assert page.locator(".ak-drawer #atlas-rule-dependencies").is_visible()
    page.keyboard.press("Escape")
    _open_details(page)
    page.locator(".atlas-rule-assessments > summary").click()
    page.locator(".atlas-rule-assessments").get_by_role(
        "link", name="dependencies", exact=True
    ).click()
    assert page.locator(".ak-drawer #atlas-rule-dependencies").is_visible()


def test_svg_export_is_standalone_and_old_mode_keeps_new_explorer(explorer):
    page, index = explorer
    page.get_by_role("button", name="Decided by", exact=True).click()
    page.get_by_role("button", name="Share", exact=True).click()
    anchor = page.get_by_role("button", name="Share", exact=True).bounding_box()
    menu = page.get_by_role("menu").bounding_box()
    assert (
        min(
            abs(menu["y"] - anchor["y"] - anchor["height"]),
            abs(anchor["y"] - menu["y"] - menu["height"]),
        )
        <= 9
    )
    with page.expect_download() as download:
        page.get_by_role("menuitem", name="Download SVG").click()
    svg = download.value.path().read_text()
    root = ElementTree.fromstring(svg)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert "var(--" not in svg
    assert "rgb(" in svg
    assert "peer" in svg and "core" in svg
    assert any('url("#flow-arrow' in node.get("style", "") for node in root.iter())
    page.goto(index.as_uri() + "?explorer=0&view=target&perspective=decision")
    _wait_for_layout(page)
    assert page.get_by_text("Snapshot and audit", exact=True).is_visible()
    assert page.locator(".ak-brand").is_visible()
    assert page.get_by_role("link", name="Open ArchQ Explorer", exact=True).count() == 0
    assert parse_qs(urlsplit(page.url).query)["perspective"] == ["decision"]
    assert parse_qs(urlsplit(page.url).query)["view"] == ["target"]


@pytest.mark.parametrize("native", [False, True])
def test_fullscreen_is_the_same_explorer_and_restores_report(explorer, native):
    expect = pytest.importorskip("playwright.sync_api").expect
    page, _ = explorer
    if not native:
        page.evaluate("Element.prototype.requestFullscreen = undefined")
    page.get_by_role("button", name="Target", exact=True).click()
    _wait_for_layout(page)
    page.locator('.flow-nodes [data-uml-id="peer"]').click()
    page.get_by_role("button", name="Decided by", exact=True).click()
    page.get_by_role("button", name="Zoom in", exact=True).click()
    page.get_by_role("button", name="Fullscreen", exact=True).scroll_into_view_if_needed()
    before = page.evaluate("({url: location.href, scroll: scrollY, state: ArchkeelFlow.state()})")
    page.get_by_role("button", name="Fullscreen", exact=True).click()
    expect(page.locator("#flow")).to_have_attribute(
        "data-expanded", "native" if native else "fallback"
    )
    assert page.locator("#flow").get_attribute("data-expanded") == (
        "native" if native else "fallback"
    )
    box = page.locator("#flow").bounding_box()
    assert box["x"] == 0 and box["y"] == 0
    assert box["height"] == page.viewport_size["height"]
    page.get_by_role("button", name="Search", exact=True).click()
    page.get_by_role("combobox").fill("core")
    page.keyboard.press("Escape")
    assert page.locator("#flow").get_attribute("data-expanded")
    page.get_by_role("button", name="Share", exact=True).click()
    assert page.get_by_role("menuitem", name="Download SVG").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#flow").get_attribute("data-expanded")
    page.get_by_role("button", name="Restore", exact=True).click()
    expect(page.locator("#flow")).not_to_have_attribute("data-expanded")
    assert page.url == before["url"]
    assert page.evaluate("ArchkeelFlow.state().selection") == before["state"]["selection"]
    assert page.evaluate("ArchkeelFlow.state().zoom") == before["state"]["zoom"]
    assert page.evaluate("scrollY") == before["scroll"]
    assert page.locator(".report-heading").is_visible()


@pytest.mark.parametrize("health_open", [False, True])
def test_fallback_fullscreen_keeps_moved_audit_interactive(explorer, health_open):
    page, _ = explorer
    health = page.get_by_role("button", name="Health check", exact=True)
    if health_open:
        health.click()
    page.evaluate("Element.prototype.requestFullscreen = undefined")
    page.get_by_role("button", name="Fullscreen", exact=True).click()
    if health_open:
        health.click()
    assert page.locator(".report-shell > .atlas-source").evaluate("e => e.inert")
    health.click()
    audit = page.locator(".ak-drawer .atlas-source")
    assert not audit.evaluate("e => e.inert")
    audit.locator("summary").click()
    assert audit.get_by_role(
        "link", name="Complete architecture JSON and recorded evidence"
    ).is_visible()
    page.get_by_role("button", name="Restore", exact=True).click()
    health.click()
    assert not page.locator(".report-shell > .atlas-source").evaluate("e => e.inert")


def test_print_retains_the_document_evidence(explorer):
    page, _ = explorer
    page.emulate_media(media="print")
    assert page.locator(".verdict-line").is_visible()
    assert page.locator("#findings-heading").is_visible()
    assert page.locator(".atlas-source > summary").is_visible()
    assert page.locator(".report-heading").is_visible()
    assert not page.locator(".flow-section").is_visible()


@pytest.mark.parametrize("detail", [False, True])
def test_landscape_fullscreen_keeps_diagram_and_details_visible(explorer, detail):
    page, index = explorer
    page.set_viewport_size({"width": 844, "height": 390})
    if detail:
        module = page.evaluate("ArchkeelFlow.atlas.modules.find(m => m.name === 'sample.core').id")
        page.goto(
            index.with_name("architecture.detail.html").as_uri() + f"?module={module}&view=diagram"
        )
        _wait_for_layout(page)
    page.evaluate("Element.prototype.requestFullscreen = undefined")
    page.get_by_role("button", name="Fullscreen", exact=True).click()
    canvas = page.locator(".flow-canvas").bounding_box()
    inspector = page.locator(".flow-inspector").bounding_box()
    assert canvas["height"] >= 200 and canvas["width"] >= 350
    assert inspector["height"] >= 200
    assert canvas["x"] + canvas["width"] <= inspector["x"]
    if detail:
        node = page.locator(".flow-nodes [data-uml-id]").first
        identity = node.get_attribute("data-uml-id")
        page.get_by_role("button", name="Search", exact=True).click()
        search = page.get_by_role("combobox")
        search.fill(identity)
        search.press("Enter")
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{identity}"]').get_attribute("aria-pressed")
            == "true"
        )


def test_mobile_matrix_selection_reveals_details(explorer):
    page, _ = explorer
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Health check", exact=True).click()
    page.locator('.flow-matrix [data-cell="0"]').click()
    assert page.locator(".ak-drawer").count() == 0
    assert page.locator(".flow-inspector").is_visible()
    assert "Permission: UNKNOWN" in page.locator(".flow-inspector-content").inner_text()


@pytest.mark.parametrize("width", [390, 768, 1024, 1280, 1440])
def test_explorer_controls_fit_without_overlap(explorer, width):
    page, _ = explorer
    page.set_viewport_size({"width": width, "height": 844})
    page.evaluate("ArchkeelFlow.atlas.components[0].label = 'very_long_component_name'.repeat(8)")
    page.locator('.flow-nodes [data-uml-kind="component"]').first.press("Space")
    controls = [
        page.get_by_role("button", name=name, exact=True)
        for name in ("Search", "Target", "Health check", "Objects", "Share", "Zoom in", "Evidence")
    ]
    boxes = []
    for control in controls:
        assert control.is_visible()
        control.scroll_into_view_if_needed()
        box = control.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        # Page coordinates: the findings above the explorer make each scroll differ.
        box["y"] += page.evaluate("window.scrollY")
        boxes.append(box)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert (
                a["x"] + a["width"] <= b["x"]
                or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"]
                or b["y"] + b["height"] <= a["y"]
            )
    page.get_by_role("button", name="Target", exact=True).click()
