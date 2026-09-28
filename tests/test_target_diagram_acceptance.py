# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target diagrams describe declared architecture, not the observed graph."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def _target_diagram_page(
    tmp_path: Path, *, include_module_target: bool = False
) -> tuple[str, dict[str, Any]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    contract["components"].append(
        {
            "id": "COMP-ARCHIVE",
            "label": "archive",
            "role": "component",
            "packages": ["shop.archive"],
            "responsibilities": ["Retain archived orders."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    app = next(component for component in contract["components"] if component["id"] == "COMP-APP")
    app["requires"] = [
        {
            "component": "archive",
            "rationale": "Archived orders stay behind the declared archive boundary.",
        }
    ]
    if include_module_target:
        contract.setdefault("declarations", {}).setdefault("modules", []).append(
            {
                "path": "shop/app/orders.py",
                "responsibility": "Coordinate order workflows.",
            }
        )
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    root_layout["allowed_children"].append("shop.archive")
    root_layout["allowed_children"].append("shop.missing")
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        "shop/orphan.py": "VALUE = 1\n",
    }
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def test_target_diagram_shows_declared_root_and_nested_graphs_only(tmp_path: Path) -> None:
    _, payload = _target_diagram_page(tmp_path)
    explorers = payload["explorers"]
    target_nodes = list(_walk(explorers["target"]))
    target_ids = {node["id"] for node in target_nodes}
    require_ids = {node["id"] for node in target_nodes if node["kind"] == "requires"}
    assert len(require_ids) == sum(node["kind"] == "requires" for node in target_nodes)

    diagrams = explorers["target_diagrams"]
    root = diagrams["root"]
    root_nodes = {node["id"]: node for node in root["nodes"]}
    assert "COMP-ARCHIVE" in root_nodes
    assert root_nodes["COMP-ARCHIVE"]["kind"] == "component"
    assert "physical:shop.archive" not in root_nodes
    archive_requirement = next(
        edge for edge in root["edges"] if edge.get("declaration") == "requires:COMP-APP:archive"
    )
    assert (archive_requirement["source"], archive_requirement["target"]) == (
        "COMP-APP",
        "COMP-ARCHIVE",
    )

    layout = diagrams["nested"]["layout:ROOT-LAYOUT"]
    layout_nodes = {node["id"]: node for node in layout["nodes"]}
    assert layout_nodes["physical:shop.archive"]["kind"] == "physical_child"
    assert layout_nodes["physical:shop.missing"]["kind"] == "physical_child"
    assert any(
        edge["source"] == "layout:ROOT-LAYOUT" and edge["target"] == "physical:shop.archive"
        for edge in layout["edges"]
    )
    assert set(layout_nodes) <= target_ids

    nested = diagrams["nested"]["COMP-STORE"]
    nested_labels = {node["label"] for node in nested["nodes"]}
    assert {"api", "backend", "codec", "repository"} <= nested_labels
    assert any(edge["kind"] == "requires" for edge in nested["edges"])

    # Tree records are exhaustively reachable as nodes or declared requirement edges.
    reachable: set[str] = set()
    graph_node_ids: set[str] = set()
    edge_declarations: list[str] = []
    pending = [node["id"] for node in root["nodes"]]
    graphs = [root]
    while pending:
        owner = pending.pop()
        if owner in reachable:
            continue
        reachable.add(owner)
        graph = diagrams["nested"].get(owner)
        if graph is None:
            continue
        assert graph["owner"] == owner
        graphs.append(graph)
        pending.extend(node["id"] for node in graph["nodes"])
    for graph in graphs:
        graph_node_ids.update(node["id"] for node in graph["nodes"])
        edge_declarations.extend(
            edge["declaration"] for edge in graph["edges"] if "declaration" in edge
        )
    assert graph_node_ids | set(edge_declarations) == target_ids
    assert set(diagrams["nested"]) <= reachable
    represented_requires = (graph_node_ids | set(edge_declarations)) & require_ids
    assert represented_requires == require_ids
    assert set(edge_declarations) <= target_ids

    for graph in graphs:
        ids = {node["id"] for node in graph["nodes"]}
        assert all(edge["source"] in ids and edge["target"] in ids for edge in graph["edges"])
        assert all(edge.get("state") not in {"violation", "observed"} for edge in graph["edges"])
        assert all(
            node["kind"]
            in {"component", "package_scope", "physical_child", "requires", "root_layout"}
            for node in graph["nodes"]
        )
        assert all(
            edge["kind"] in {"allowed_child", "contains", "owns_package", "requires"}
            for edge in graph["edges"]
        )
    assert all(node["label"] != "shop.orphan" for node in root["nodes"])


def test_target_diagram_is_visible_and_drillable_without_filter_status(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL"),
        )
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()
            assert page.locator(".flow-canvas").is_visible()
            assert page.locator(".flow-nodes .node").count() >= 6
            root_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert "archive" in root_labels
            assert page.locator(".flow-edges .edge").count() > 0
            assert (
                page.locator(
                    '.target-node[data-target-node="COMP-STORE"] .target-meta'
                ).text_content()
                == "4 components · Open"
            )
            assert page.locator(".flow-filter-status").text_content().strip() != (
                "No diagram filters active"
            )
            requirement_edge = page.locator(".flow-edges .target-edge.requires").first
            hit_path = requirement_edge.locator(".target-hit")
            hit_path.scroll_into_view_if_needed()
            point = hit_path.evaluate(
                "path => {"
                " const length = path.getTotalLength();"
                " const matrix = path.getScreenCTM();"
                " if (!length || !matrix) return null;"
                " const edge = path.closest('[data-target-edge]');"
                " for (let ratio = 0.2; ratio <= 0.8; ratio += 0.05) {"
                "   const svgPoint = path.getPointAtLength(length * ratio);"
                "   const screen = new DOMPoint(svgPoint.x, svgPoint.y).matrixTransform(matrix);"
                "   const under = document.elementFromPoint(screen.x, screen.y);"
                "   if (under && edge.contains(under)) return {x: screen.x, y: screen.y};"
                " }"
                " return null;"
                "}"
            )
            assert point is not None, "Target requirement edge has no visible hit point in Chrome"
            assert hit_path.evaluate(
                "(path, point) => { const under = document.elementFromPoint(point.x, point.y);"
                " return Boolean(under && path.closest('[data-target-edge]').contains(under)); }",
                point,
            ), "Computed SVG point does not hit the Target requirement edge"
            page.mouse.click(point["x"], point["y"])
            assert (
                page.locator(".flow-inspector")
                .get_by_text("Archived orders stay behind the declared archive boundary.")
                .is_visible()
            )
            requirement_edge.focus()
            page.keyboard.press("Enter")
            assert requirement_edge.get_attribute("aria-pressed") == "true"

            page.locator('.flow-nodes .node[data-target-node="layout:ROOT-LAYOUT"]').click()
            layout_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert {"shop.archive", "shop.missing"} <= layout_labels
            assert page.locator(".flow-edges .edge.allowed_child").count() > 0
            page.keyboard.press("Escape")
            assert page.locator(
                '.flow-nodes .node[data-target-node="layout:ROOT-LAYOUT"]'
            ).is_visible()

            page.locator('.flow-nodes .node[data-target-node="COMP-STORE"]').click()
            nested_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert {"api", "backend", "codec", "repository"} <= nested_labels
            assert page.locator(".flow-edges .edge").count() > 0
            assert page.locator(".flow-filter-status").text_content().strip() != (
                "No diagram filters active"
            )
            page.locator(".flow-back").click()
            assert page.locator('.flow-nodes .node[data-target-node="COMP-STORE"]').is_visible()

            page.get_by_role("button", name="Diff").click()
            for category, entry in (
                ("diff:unmapped", "unmapped:shop.orphan"),
                ("diff:absent", "absent:ROOT-LAYOUT:shop.missing"),
            ):
                page.locator(f'[data-projection-id="{category}"]').click()
                page.locator(f'[data-projection-id="{entry}"]').click()
                assert page.locator('.flow-projection [aria-label="Selected entry"]').is_visible()
                page.locator("[data-projection-root]").click()

            page.set_viewport_size({"width": 375, "height": 844})
            page.get_by_role("button", name="Actual").click()
            page.locator('[data-projection-id="shop"]').click()
            assert page.locator('[data-projection-id="shop.orphan"]').is_visible()
            page.get_by_role("button", name="Diff").click()
            page.locator('[data-projection-id="diff:unmapped"]').click()
            assert page.locator('[data-projection-id="unmapped:shop.orphan"]').is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


def test_target_diagram_opens_exact_module_leaf_as_module(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path, include_module_target=True)
    target_nodes = list(_walk(payload["explorers"]["target"]))
    leaf = next(
        node
        for node in target_nodes
        if any(
            detail["label"] == "File" and detail["value"] == "shop/app/orders.py"
            for detail in node["details"]
        )
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL"),
        )
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()
            responsibilities = page.locator(".flow-responsibilities")
            responsibilities.locator("summary").click()
            declared_count = sum(
                detail["label"] == "Responsibility"
                for node in target_nodes
                for detail in node["details"]
            )
            assert (
                responsibilities.locator(".flow-responsibility-list button").count()
                == declared_count
            )
            responsibilities.locator("input").fill("Coordinate order workflows")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {declared_count} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert (
                page.locator(".flow-inspector")
                .get_by_text("Coordinate order workflows.", exact=True)
                .is_visible()
            )
            page.locator('.flow-views [data-flow-view="target"]').click()
            page.locator('.flow-nodes .node[data-target-node="module-targets"]').click()
            page.locator('.flow-nodes .node[data-target-node="module-folder:shop"]').click()
            page.locator('.flow-nodes .node[data-target-node="module-folder:shop/app"]').click()
            card = page.locator(f'.flow-nodes .node[data-target-node="{leaf["id"]}"]')
            assert card.is_visible()
            assert card.locator(".target-kind").text_content() == "MODULE"
            card.click()
            inspector = page.locator(".flow-inspector")
            assert inspector.get_by_text("shop/app/orders.py", exact=True).is_visible()
            assert inspector.get_by_text("Coordinate order workflows.", exact=True).is_visible()
        finally:
            browser.close()
