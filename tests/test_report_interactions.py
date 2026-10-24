# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared report navigation remains usable without the retired frame renderer."""

import pytest
from browser_report_support import _browser_page
from test_uml_rendering import _open_module, _uml_report, _wait_for_layout


@pytest.mark.browser
def test_native_card_drag_reroutes_all_hits_and_keeps_architecture_unchanged(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "Diff")
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset and fit", exact=True
        ).click()
        _wait_for_layout(page)
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
        manual_position = card.get_attribute("transform")
        card.click()
        page.get_by_role("button", name="Open selected Client", exact=True).click()
        _wait_for_layout(page)
        page.locator(".flow-back").click()
        _wait_for_layout(page)
        card = page.locator('.flow-nodes [data-label="Client"]')
        assert card.get_attribute("transform") == manual_position
        page.get_by_role("button", name="Fit overview").click()
        assert card.get_attribute("transform") == manual_position
        page.locator(".flow-zoom-100").click()
        _wait_for_layout(page)
        assert card.get_attribute("transform") == before
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()
