# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared report navigation remains usable without the retired frame renderer."""

import pytest
from browser_report_support import _browser_page, _open_details
from test_uml_rendering import _open_module, _uml_report

from archkeel.ir.architecture_graph import Relationship


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
