# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target overview keeps readable names and metadata on its declaring owner."""

from pathlib import Path

import pytest
from test_target_diagram_acceptance import _target_diagram_page


@pytest.mark.parametrize("width", [1600, 1024])
def test_target_fit_keeps_readable_labels_even_when_the_scope_must_scroll(
    tmp_path: Path, width: int
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _target_diagram_page(tmp_path, cross_frame_chain=True)
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator(".flow-fullscreen").click()
            page.locator(".flow-fit-overview").click()
            sizes = page.locator(".target-label").evaluate_all(
                """nodes => nodes.map(node => {
                  const matrix = node.getScreenCTM();
                  return parseFloat(getComputedStyle(node).fontSize)
                    * Math.hypot(matrix.a, matrix.b);
                })"""
            )
            assert sizes and min(sizes) >= 12
        finally:
            browser.close()


def test_target_rule_metadata_is_reachable_on_its_owner_without_peer_cards(tmp_path: Path) -> None:
    api = pytest.importorskip("playwright.sync_api")
    html, payload = _target_diagram_page(tmp_path)
    graph = payload["explorers"]["target_diagrams"]["nested"]["COMP-STORE"]
    metadata = [
        node
        for node in graph["nodes"]
        if node["id"] != graph["owner"]
        and node["kind"] in ("package_scope", "requires", "root_layout")
    ]
    assert metadata
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-node="COMP-STORE"]').press("Enter")
            assert (
                page.locator(".flow-nodes .target-node:is(.package,.layout,.requires)").count() == 0
            )
            page.locator(".flow-details-toggle").click()
            for node in metadata:
                button = page.locator(f'[data-target-detail="{node["id"]}"]')
                assert button.count() == 1
        finally:
            browser.close()


def test_folded_layout_remains_openable_from_its_component_details(tmp_path: Path) -> None:
    from test_target_hierarchy_independent_acceptance import _folded_single_component_page

    api = pytest.importorskip("playwright.sync_api")
    html, _ = _folded_single_component_page(tmp_path)
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(5000)
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-node="COMP-APP"]').press(" ")
            page.locator(".flow-details-toggle").click()
            page.locator('[data-target-detail="layout:ROOT-SOLO"]').press("Enter")
            page.locator(".flow-open-selected").press("Enter")
            assert page.locator('[data-target-node="physical:shop.app.orders"]').count() == 1
        finally:
            browser.close()
