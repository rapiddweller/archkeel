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


def test_compact_target_requirements_do_not_cross_component_cards(tmp_path: Path) -> None:
    from test_consistent_explorer_acceptance import _replace_flow_payload
    from test_target_hierarchy_independent_acceptance import _cross_frame_domains_page

    api = pytest.importorskip("playwright.sync_api")
    html, payload = _cross_frame_domains_page(tmp_path)
    graph = payload["explorers"]["target_diagrams"]["root"]
    ranks = {
        "authoring": 1,
        "domains": 3,
        "dsl": 5,
        "errors": 6,
        "interfaces": 0,
        "io": 4,
        "python_compat": 6,
        "randomness": 6,
        "resources": 1,
        "runtime": 2,
    }

    def node_id(name: str) -> str:
        return "COMP-" + name.upper().replace("_", "-")

    graph["nodes"] = [n for n in graph["nodes"] if n["id"] in graph["containers"]]
    graph["nodes"].extend(
        {
            "id": node_id(name),
            "kind": "component",
            "label": name,
            "dependency_rank": rank,
            "details": [
                {
                    "label": "Responsibility",
                    "value": "Keep the shared structural contract and reusable primitives "
                    "below the runtime, "
                    "without adding lifecycle or generation policy.",
                }
            ],
        }
        for name, rank in ranks.items()
    )
    for key, container in graph["containers"].items():
        container["members"] = [
            node_id(n)
            for n in ranks
            if (n in {"dsl", "io", "runtime"}) == (key == "layout:LAYOUT-ENGINE")
        ]
    requires = {
        "authoring": ("domains", "dsl", "io", "python_compat", "runtime"),
        "domains": ("dsl", "errors", "io", "randomness"),
        "dsl": ("python_compat",),
        "interfaces": ("authoring", "domains", "python_compat", "resources", "runtime"),
        "io": ("dsl", "randomness"),
        "resources": ("domains", "dsl", "io", "runtime"),
        "runtime": ("domains", "dsl", "io", "python_compat", "randomness"),
    }
    graph["edges"] = [
        {
            "source": node_id(source),
            "target": node_id(target),
            "kind": "requires",
            "declaration": f"requires:{source}:{target}",
            "details": [],
            "label": "requires",
        }
        for source, targets in requires.items()
        for target in targets
    ]
    html = _replace_flow_payload(html, payload)
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator(".flow-fullscreen").click()
            page.locator(".flow-fit-overview").click()
            crossings = page.evaluate("""() => {
              const graph = JSON.parse(document.querySelector('#flow-data').textContent)
                .explorers.target_diagrams.root;
              const cards = [...document.querySelectorAll('.target-node:not(.target-container)')]
                .map(n => ({id: n.dataset.targetNode,
                  rect: n.querySelector('rect').getBoundingClientRect()}));
              const hits = [];
              for (const node of document.querySelectorAll('.target-edge')) {
                const edge = graph.edges.find(e => e.declaration === node.dataset.targetEdge);
                const path = node.querySelector('path.line'), matrix = path.getScreenCTM();
                for (let s = 2; s < path.getTotalLength() - 2; s += 2) {
                  const point = path.getPointAtLength(s);
                  const p = new DOMPoint(point.x, point.y).matrixTransform(matrix);
                  for (const card of cards) {
                    const r = card.rect;
                    if (p.x > r.left + 2 && p.x < r.right - 2
                        && p.y > r.top + 2 && p.y < r.bottom - 2)
                      hits.push([edge.declaration, card.id]);
                  }
                }
              }
              return hits;
            }""")
            assert not crossings, crossings
            assert page.locator("[data-route-warning]").count() == 0
        finally:
            browser.close()
