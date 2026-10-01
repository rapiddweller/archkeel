# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent browser checks for inventory, placement, evidence and readability."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import CONFIG
from test_target_diagram_acceptance import _replace_flow_payload, _target_diagram_page
from test_target_hierarchy_independent_acceptance import (
    _ce_nested_route_page,
    _placement_page_data,
)

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node.get("children", []))


def _browser_page(playwright_api: Any, html: str, width: int = 1440, height: int = 1000):
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})
    page.set_default_timeout(2500)
    page.set_content(html, wait_until="load")
    return playwright, browser, page


def _open_details(page: Any) -> None:
    toggle = page.locator("[data-flow-details-toggle]")
    if toggle.count() and toggle.is_visible() and toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def _report_page(root: Path) -> tuple[str, dict[str, Any]]:
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page_html = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    marker = page_html.index('id="flow-data"')
    start = page_html.index(">", marker) + 1
    payload = json.loads(page_html[start : page_html.index("</script>", start)])
    return page_html, payload


def _frame(page: Any, frame_id: str):
    return page.locator(
        f'[data-diagram-frame="{frame_id}"], [data-target-container="{frame_id}"]'
    ).filter(visible=True)


def _frame_relation(page: Any, frame_id: str, node_selector: str, relation: str) -> bool:
    return _frame(page, frame_id).evaluate(
        "(frame, args) => { const [selector, relation] = args;"
        " const rect = frame.querySelector('rect.target-frame') ||"
        " frame.previousElementSibling.querySelector('rect.target-frame');"
        " const b = rect.getBBox(), m = rect.getScreenCTM();"
        " const framePoints = [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],"
        " [b.x+b.width,b.y+b.height]].map(([x,y]) => new DOMPoint(x,y).matrixTransform(m));"
        " const fb = {left:Math.min(...framePoints.map(p=>p.x)),"
        " right:Math.max(...framePoints.map(p=>p.x)),top:Math.min(...framePoints.map(p=>p.y)),"
        " bottom:Math.max(...framePoints.map(p=>p.y))};"
        " const node = document.querySelector(selector); if (!node) return false;"
        " const n=node.getBBox(), nm=node.getScreenCTM();"
        " const points=[[n.x,n.y],[n.x+n.width,n.y],[n.x,n.y+n.height],"
        " [n.x+n.width,n.y+n.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(nm));"
        " const inside=Math.min(...points.map(p=>p.x))>=fb.left+12&&"
        " Math.max(...points.map(p=>p.x))<=fb.right-12&&"
        " Math.min(...points.map(p=>p.y))>=fb.top+12&&"
        " Math.max(...points.map(p=>p.y))<=fb.bottom-12;"
        " const disjoint=Math.max(...points.map(p=>p.x))<fb.left||"
        " Math.min(...points.map(p=>p.x))>fb.right||"
        " Math.max(...points.map(p=>p.y))<fb.top||"
        " Math.min(...points.map(p=>p.y))>fb.bottom;"
        " return relation==='inside'?inside:disjoint; }",
        [node_selector, relation],
    )


def _visible_svg_text(locator: Any) -> list[str]:
    return locator.evaluate_all(
        "nodes=>nodes.filter(node=>{let alpha=1,visible=true;for(let p=node;p;p=p.parentElement){"
        "const s=getComputedStyle(p);alpha*=Number(s.opacity||1);"
        "visible=visible&&s.display!=='none'&&s.visibility==='visible';}"
        "const b=node.getBBox();return visible&&alpha>0&&b.width>0&&b.height>0;})"
        ".map(node=>{const spans=[...node.querySelectorAll('tspan')];const text=spans.length"
        "?spans.map(span=>span.textContent).join(''):[...node.childNodes]"
        ".filter(child=>child.nodeType===Node.TEXT_NODE).map(child=>child.textContent).join('');"
        "return text.replace(/\\s+/g,' ').trim();})"
    )


def _diagram_inventory(page: Any) -> tuple[list[str], list[str]]:
    return (
        page.locator(".flow-nodes .node").evaluate_all(
            "nodes => nodes.map(node => node.dataset.label)"
        ),
        page.locator(".flow-edges .edge .hit").evaluate_all(
            "nodes => nodes.map(node => node.dataset.key)"
        ),
    )


def _placement_page_with_observed_packages(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    _placement_page_data(tmp_path, neutral_labels=True)
    root = tmp_path / "repo"
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    frame_template = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    contract["rules"].extend(
        [
            dict(
                frame_template,
                id="FRAME-ALPHA",
                root="shop.alpha",
                allowed_children=["shop.alpha.api"],
            ),
            dict(
                frame_template,
                id="FRAME-BETA",
                root="shop.beta",
                allowed_children=["shop.beta.api"],
            ),
        ]
    )
    contract_path.write_text(json.dumps(contract))
    modules = {
        "shop/alpha/api.py": "VALUE = 1\n",
        "shop/beta/api.py": "VALUE = 2\n",
        "shop/ambiguous/api.py": "VALUE = 3\n",
    }
    for name, source in modules.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return _report_page(root)


def test_diagram_physical_frame_preserves_ce_inventory(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    expected_labels = {
        item["label"]
        for item in [
            *payload["components"],
            *(payload.get("libraries") or []),
            *([payload["unassigned"]] if payload.get("unassigned") else []),
        ]
    }
    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, page_html)
    try:
        page.get_by_role("button", name="Diagram", exact=True).click()
        rendered_labels, rendered_edges = _diagram_inventory(page)
        assert len(rendered_labels) == len(set(rendered_labels)) == len(expected_labels)
        assert set(rendered_labels) == expected_labels
        expected_edge_keys = {f"{edge['source']}>{edge['target']}" for edge in payload["edges"]}
        assert len(rendered_edges) == len(set(rendered_edges)) == len(expected_edge_keys)
        assert set(rendered_edges) == expected_edge_keys

        root_graph = payload["explorers"]["target_diagrams"]["root"]
        engine_frames = [
            (frame_id, container)
            for frame_id, container in root_graph["containers"].items()
            if container.get("scope") == "datamimic_ce.engine"
        ]
        assert len(engine_frames) == 1
        frame_id, _ = engine_frames[0]
        frame = _frame(page, frame_id)
        assert frame.count() == 1
        assert _visible_svg_text(frame.locator(".target-frame-role")) == ["Physical package"]
        assert _visible_svg_text(frame.locator(".target-frame-title")) == ["engine"]
        assert "datamimic_ce.engine" in frame.get_attribute("aria-label")
        assert "datamimic_ce.engine" in frame.locator("title").text_content()
        engine_cards = {
            item["label"]
            for item in payload["components"]
            if item["modules"]
            and all(
                module == "datamimic_ce.engine" or module.startswith("datamimic_ce.engine.")
                for module in item["modules"]
            )
        }
        assert engine_cards == {"runtime", "io", "dsl"}
        for label in engine_cards:
            assert _frame_relation(
                page, frame_id, f'.flow-nodes .node[data-label="{label}"]', "inside"
            )
        unassigned_selector = f'.flow-nodes .node[data-label="{payload["unassigned"]["label"]}"]'
        assert _frame_relation(page, frame_id, unassigned_selector, "disjoint")
        root_frames = [
            key
            for key, value in root_graph["containers"].items()
            if value.get("scope") == "datamimic_ce"
        ]
        assert len(root_frames) == 1
        assert _frame(page, root_frames[0]).count() == 1
        assert _frame_relation(page, root_frames[0], f'[data-diagram-frame="{frame_id}"]', "inside")
    finally:
        browser.close()
        playwright.stop()


def test_fullscreen_preserves_explorer_content_across_views(tmp_path: Path) -> None:
    """Native and policy-denied fullscreen keep every CE view usable."""
    html, _ = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, native_page = _browser_page(playwright_api, html, width=375, height=844)
    views = ("diagram", "actual", "target", "diff")

    def measure_views(page: Any) -> tuple[list[dict[str, Any]], list[dict[str, float]]]:
        measurements: list[dict[str, Any]] = []
        anchors: list[dict[str, float]] = []
        for view in views:
            tab = page.locator(f'[data-flow-view="{view}"]')
            assert tab.is_visible() and tab.is_enabled()
            tab.click()
            assert (
                page.locator('[data-flow-view][aria-pressed="true"]').get_attribute(
                    "data-flow-view"
                )
                == view
            )
            measurement = page.locator("#flow").evaluate(
                "root => { const box=selector=>{"
                "const r=root.querySelector(selector).getBoundingClientRect();"
                "return {x:r.x,y:r.y,width:r.width,height:r.height};};"
                "return {view:root.dataset.view,viewportHeight:innerHeight,"
                "content:box('.flow-layout'),tabs:box('.flow-views'),toolbar:box('.flow-toolbar'),"
                "horizontalOverflow:root.ownerDocument.documentElement.scrollWidth>innerWidth,"
                "fullscreenControlVisible:!!root.querySelector('.flow-fullscreen')&&"
                "root.querySelector('.flow-fullscreen').getClientRects().length>0}; }"
            )
            measurements.append(measurement)
            anchors.append(
                {
                    name: measurement[name][axis]
                    for name, axis in (("tabs", "y"), ("toolbar", "y"), ("content", "y"))
                }
            )
        return measurements, anchors

    try:
        native_page.locator(".flow-fullscreen").click()
        native_page.wait_for_function(
            "() => document.querySelector('#flow')?.dataset.expanded==='native'"
        )
        assert native_page.evaluate("document.fullscreenElement===document.querySelector('#flow')")
        native, native_anchors = measure_views(native_page)

        fallback_context = browser.new_context(viewport={"width": 375, "height": 844})
        fallback_page = fallback_context.new_page()
        fallback_page.set_content(
            '<iframe title="report" sandbox="allow-scripts allow-same-origin" '
            "allow=\"fullscreen 'none'\" "
            'style="position:fixed;inset:0;width:100vw;height:100vh;border:0"></iframe>'
        )
        fallback_page.locator("iframe").evaluate(
            "(frame, source) => { frame.srcdoc=source; }", html
        )
        frame = fallback_page.frame_locator('iframe[title="report"]')
        frame.locator(".flow-fullscreen").wait_for(state="visible")
        policy = frame.locator("#flow").evaluate(
            "() => ({allowed:(document.permissionsPolicy||document.featurePolicy)"
            ".allowsFeature('fullscreen'),enabled:document.fullscreenEnabled})"
        )
        assert policy == {"allowed": False, "enabled": False}
        frame.locator(".flow-fullscreen").click()
        frame.locator('#flow[data-expanded="fallback"]').wait_for(state="attached")
        fallback, fallback_anchors = measure_views(frame)

        floor = 0.4 * 844
        assert all(item["content"]["height"] >= floor for item in native + fallback), (
            f"content geometry by view; native={native}; fallback={fallback}"
        )
        assert all(
            not item["horizontalOverflow"] and item["fullscreenControlVisible"]
            for item in native + fallback
        )
        for group in (native_anchors, fallback_anchors):
            for name in ("tabs", "toolbar", "content"):
                assert max(item[name] for item in group) - min(item[name] for item in group) <= 2

        native_page.locator('[data-flow-view="diagram"]').focus()
        native_page.keyboard.press("Enter")
        assert (
            native_page.locator('[data-flow-view="diagram"]').get_attribute("aria-pressed")
            == "true"
        )
        touch_context = browser.new_context(viewport={"width": 375, "height": 844}, has_touch=True)
        touch_page = touch_context.new_page()
        touch_page.set_content(html, wait_until="load")
        touch_page.locator('[data-flow-view="actual"]').tap()
        assert (
            touch_page.locator('[data-flow-view="actual"]').get_attribute("aria-pressed") == "true"
        )
        touch_context.close()
        fallback_context.close()
    finally:
        browser.close()
        playwright.stop()


def test_diagram_edges_show_endpoints_relation_weight_and_evidence(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    expected_edges = {f"{edge['source']}>{edge['target']}": edge for edge in payload["edges"]}
    assert expected_edges

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, page_html)
    try:
        page.get_by_role("button", name="Diagram").click()
        _open_details(page)
        rendered_edge_keys = page.locator(".flow-edges .edge .hit").evaluate_all(
            "nodes => nodes.map(node => node.dataset.key)"
        )
        assert len(rendered_edge_keys) == len(set(rendered_edge_keys)) == len(expected_edges)
        assert set(rendered_edge_keys) == set(expected_edges)
        for key, expected in expected_edges.items():
            hit = page.locator(f'.flow-edges .edge .hit[data-key="{key}"]')
            assert hit.count() == 1
            edge = hit.locator("xpath=..").first
            assert expected["state"] in (edge.get_attribute("class") or "").split()
            labels = {item["label"]: item["label"] for item in payload["components"]}
            labels.update({item["label"]: item["display"] for item in payload.get("libraries", [])})
            source_label = labels.get(expected["source"], expected["source"])
            target_label = labels.get(expected["target"], expected["target"])
            assert f"{expected['source']} to {expected['target']}" in hit.get_attribute(
                "aria-label"
            )
            title = hit.locator("title").evaluate("node => node.textContent")
            assert f"{expected['source']} uses {expected['target']}" in title
            if expected.get("kind") == "symbol_use":
                assert "symbol-use edge" in title
            else:
                sites = expected["import_sites"]
                assert f"{sites} import site" in title
            for site in expected["sites"]:
                assert site in title

            hit.focus()
            page.keyboard.press("Enter")
            inspector = page.locator(".flow-inspector")
            assert inspector.is_visible()
            details = inspector.inner_text()
            assert f"{source_label} → {target_label}" in details
            assert expected["state"] in details
            if expected.get("kind") == "symbol_use":
                assert "Relationship" in details and "Symbol use" in details
            else:
                assert "Observed import sites" in details
                assert str(expected["import_sites"]) in details
            for site in expected["sites"]:
                assert site in details

        model = page.locator('.flow-nodes .node[data-label="model"]')
        model.dblclick()
        page.locator('.flow-nodes .node[data-label="shop.model.entities"]').dblclick()
        symbol_edges = payload["modules"]["shop.model.entities"]["edges"]
        assert symbol_edges
        rendered_symbol_keys = {
            item.get_attribute("data-key") for item in page.locator(".flow-edges .edge .hit").all()
        }
        assert len(rendered_symbol_keys) == len(symbol_edges)
        assert rendered_symbol_keys == {
            f"{edge['source']}>{edge['target']}" for edge in symbol_edges
        }
        symbol_hit = page.locator(".flow-edges .edge .hit").first
        symbol_title = symbol_hit.locator("title").evaluate("node => node.textContent")
        assert "symbol-use edge" in symbol_title
        assert set(page.locator(".flow-chips .chip text").all_text_contents()) == {"1"}
        symbol_hit.focus()
        page.keyboard.press("Enter")
        inspector = page.locator(".flow-inspector")
        assert inspector.is_visible()
        details = inspector.inner_text()
        assert "Relationship" in details and "Symbol use" in details
        assert "Observed import sites" not in details
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("case", ["ambiguous", "multi-package", "absent-target"])
def test_unresolved_target_placement_does_not_create_diagram_ownership(
    tmp_path: Path, case: str
) -> None:
    if case == "absent-target":
        from test_actual_target_diff_acceptance import _acceptance_page

        page_html, payload, observed_modules = _acceptance_page(
            tmp_path, include_absent_component=True
        )
        assert "shop.ghost" not in observed_modules
    else:
        page_html, payload = _placement_page_with_observed_packages(tmp_path)
    target_nodes = list(_walk(payload["explorers"]["target"]))
    expected_target_id = {
        "ambiguous": "COMP-AMBIG",
        "multi-package": "COMP-MULTI",
        "absent-target": "COMP-GHOST",
    }[case]
    assert any(node["id"] == expected_target_id for node in target_nodes)
    if case != "absent-target":
        root = payload["explorers"]["target_diagrams"]["root"]
        root_node = next(node for node in root["nodes"] if node["id"] == expected_target_id)
        assert root_node["placement"]["container"] is None
        if case == "ambiguous":
            assert root_node["placement"]["status"] == "ambiguous"
            card_label = "Catalog API"
            expected_modules = {"shop.ambiguous.api"}
        elif case == "multi-package":
            assert root_node["placement"]["status"] == "multiple"
            assert len(root_node["placement"]["scopes"]) == 2
            card_label = "Orders API"
            expected_modules = {"shop.alpha.api", "shop.beta.api"}
        component = next(item for item in payload["components"] if item["label"] == card_label)
        assert set(component["modules"]) == expected_modules
    else:
        card_label = "ghost"

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, page_html)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        _open_details(page)
        assert page.locator(".flow-zoom-value").inner_text() == "100%"
        cards = page.locator(".flow-nodes .target-node:not(.target-container)")
        labels = cards.evaluate_all("nodes => nodes.map(node => node.dataset.label)")
        assert len(labels) == len(set(labels))
        if case == "absent-target":
            assert "ghost" in labels, "the absent Target component must remain visible"
            absent = page.locator('[data-target-node="COMP-GHOST"]')
            assert absent.is_visible()
            assert "shop.ghost" not in observed_modules
            assert payload["unassigned"]["modules"]
            assert "shop.orphan" in payload["unassigned"]["modules"]
            diff_ids = {node["id"] for node in _walk(payload["explorers"]["diff"])}
            assert "absent:COMP-GHOST" in diff_ids
            target_node = next(
                node for node in _walk(payload["explorers"]["target"]) if node["id"] == "COMP-GHOST"
            )
            root = payload["explorers"]["target_diagrams"]["root"]
            ghost = next(node for node in root["nodes"] if node["id"] == "COMP-GHOST")
            frame_id = ghost["placement"]["container"]
            assert frame_id in root["containers"]
            assert ghost["placement"]["status"] == "declared"
            assert _frame_relation(page, frame_id, '[data-target-node="COMP-GHOST"]', "inside")
            absent.click()
            assert "Own the absent ghost package." in " ".join(
                detail["value"] for detail in target_node["details"]
            )
            page.get_by_role("button", name="Actual", exact=True).click()
            fallback = " ".join(
                page.locator(
                    ".flow-alternative:visible, .flow-selected-responsibility:visible, "
                    ".flow-projection-context:visible"
                ).all_text_contents()
            )
            assert "No matching entry in this view" in fallback
            page.locator("[data-projection-root]").click()
            page.locator('[data-projection-id="shop"]').focus()
            page.keyboard.press("Enter")
            actual_orphan = page.locator('.flow-alternative [data-projection-id="shop.orphan"]')
            assert actual_orphan.is_visible()
            assert not page.locator('.flow-alternative [data-projection-id="shop.ghost"]').count()
            assert not page.locator('.flow-alternative [data-projection-id="shop.phantom"]').count()
            actual_orphan.click()
            assert actual_orphan.get_attribute("aria-pressed") == "true"
            page.get_by_role("button", name="Diff").click()
            page.locator("[data-projection-root]").click()
            page.locator('[data-projection-id="diff:absent"]').focus()
            page.keyboard.press("Enter")
            assert page.locator('[data-projection-id="absent:COMP-GHOST"]').is_visible()
            page.get_by_role("button", name="Diagram", exact=True).click()
            ghost_card = page.locator('.flow-nodes .node[data-label="ghost"]')
            assert ghost_card.count() == 1 and ghost_card.is_visible()
            ghost_card.click()
            ghost_details = page.locator(".flow-inspector").inner_text().lower()
            assert "modules\n0" in ghost_details
            assert "no modules observed" in ghost_details
            graph = payload["explorers"]["target_diagrams"]
            ghost_node = next(node for node in graph["root"]["nodes"] if node["id"] == "COMP-GHOST")
            assert ghost_node["placement"]["status"] == "declared"
            frames = {
                frame_id
                for layout in [graph["root"], *graph["nested"].values()]
                for frame_id in layout["containers"]
            }
            for frame_id in frames:
                if _frame(page, frame_id).count():
                    assert _frame_relation(
                        page, frame_id, '.flow-nodes .node[data-label="ghost"]', "disjoint"
                    )
            rendered_labels, rendered_edge_keys = _diagram_inventory(page)
            assert len(rendered_labels) == len(set(rendered_labels))
            assert "ghost" in rendered_labels
            expected_keys = {f"{edge['source']}>{edge['target']}" for edge in payload["edges"]}
            assert len(rendered_edge_keys) == len(set(rendered_edge_keys))
            assert set(rendered_edge_keys) == expected_keys
        else:
            assert (
                page.locator(f'[data-target-node="{expected_target_id}"]').get_attribute(
                    "data-placement-status"
                )
                == root_node["placement"]["status"]
            )
            target_node = page.locator(f'[data-target-node="{expected_target_id}"]')
            assert target_node.is_visible()
            target_node.click()
            details = page.locator(".flow-inspector").inner_text().lower()
            status = root_node["placement"]["status"]
            assert status in details
            assert "frame" in details

            page.get_by_role("button", name="Diagram", exact=True).click()
            diagram_card = page.locator(f'.flow-nodes .node[data-label="{card_label}"]')
            assert diagram_card.is_visible()
            assert set(component["modules"]) == expected_modules
            graph = payload["explorers"]["target_diagrams"]
            frame_ids = {
                frame_id
                for layout in [graph["root"], *graph["nested"].values()]
                for frame_id in layout["containers"]
            }
            for frame_id in frame_ids:
                frame = _frame(page, frame_id)
                if frame.count():
                    assert _frame_relation(
                        page,
                        frame_id,
                        f'.flow-nodes .node[data-label="{card_label}"]',
                        "disjoint",
                    )
            diagram_card.click()
            reason = page.locator(".flow-inspector").inner_text().lower()
            assert status in reason
    finally:
        browser.close()
        playwright.stop()


def test_unassigned_actual_module_remains_outside_declared_engine_frame(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    engine = [
        (frame_id, frame)
        for frame_id, frame in payload["explorers"]["target_diagrams"]["root"]["containers"].items()
        if frame.get("scope") == "datamimic_ce.engine"
    ]
    assert len(engine) == 1
    frame_id, _ = engine[0]
    unassigned = payload["unassigned"]
    assert "datamimic_ce.unlisted" in unassigned["modules"]

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, page_html)
    try:
        page.get_by_role("button", name="Diagram", exact=True).click()
        _open_details(page)
        page.locator(f'.flow-nodes .node[data-label="{unassigned["label"]}"]').click()
        details = page.locator(".flow-inspector").inner_text()
        assert "no unique declared owner" in details
        assert "does not add a component boundary" in details
        assert "datamimic_ce.unlisted" in unassigned["modules"]
        frame = _frame(page, frame_id)
        if frame.count():
            assert _frame_relation(
                page,
                frame_id,
                f'.flow-nodes .node[data-label="{unassigned["label"]}"]',
                "disjoint",
            )
        page.get_by_role("button", name="Actual", exact=True).click()
        page.locator("[data-projection-root]").click()
        page.locator('[data-projection-id="datamimic_ce"]').focus()
        page.keyboard.press("Enter")
        observed_module = page.locator(
            '.flow-alternative [data-projection-id="datamimic_ce.unlisted"]'
        )
        assert observed_module.is_visible()
        observed_module.click()
        assert observed_module.get_attribute("aria-pressed") == "true"
        assert (
            "No matching target declaration"
            in page.locator(".flow-selected-responsibility").inner_text()
        )
    finally:
        browser.close()
        playwright.stop()


def test_long_target_text_remains_readable_after_selection(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    long_name = "N" * 80
    long_header = "shop.namespace_part." + "shared_segment_" * 20 + "backend"
    long_responsibilities = [
        "Own a complete responsibility sentence that must remain visible, including "
        + "unbroken_identifier_" * 12,
        "Handle deterministic retries without hiding this second responsibility sentence. " * 4,
    ]
    target = next(
        node for node in _walk(payload["explorers"]["target"]) if node["id"] == "COMP-STORE"
    )
    target["label"] = long_name
    target["details"] = [
        detail for detail in target["details"] if detail["label"] != "Responsibility"
    ] + [
        {"label": "Responsibility", "value": responsibility}
        for responsibility in long_responsibilities
    ]
    target_copy = deepcopy(target)
    for node in payload["explorers"]["target_diagrams"]["root"]["nodes"]:
        if node["id"] == "COMP-STORE":
            node["label"] = long_name
            node["details"] = deepcopy(target_copy["details"])
    for layout in payload["explorers"]["target_diagrams"]["nested"].values():
        for node in layout["nodes"]:
            if node["id"] == "COMP-STORE":
                node["label"] = long_name
                node["details"] = deepcopy(target_copy["details"])
    graph_nodes = [
        node
        for layout in [
            payload["explorers"]["target_diagrams"]["root"],
            *payload["explorers"]["target_diagrams"]["nested"].values(),
        ]
        for node in layout["nodes"]
        if node["id"] == "COMP-STORE"
    ]
    assert graph_nodes and all(node["details"] == target["details"] for node in graph_nodes)
    root_graph = payload["explorers"]["target_diagrams"]["root"]
    root_graph["containers"]["layout:ROOT-LAYOUT"]["scope"] = long_header
    layout_record = next(
        node for node in _walk(payload["explorers"]["target"]) if node["id"] == "layout:ROOT-LAYOUT"
    )
    layout_record["label"] = long_header
    layout_record["_layout_scope"] = long_header
    layout_record["details"] = [
        {"label": "Layout scope", "value": long_header},
        {"label": "Provenance", "value": "docs/architecture/shop.md"},
        *[
            detail
            for detail in layout_record["details"]
            if detail.get("label") not in {"Layout scope", "Provenance"}
        ],
    ]
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, page_html)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        _open_details(page)
        assert page.locator(".flow-zoom-value").inner_text() == "100%"
        header = page.locator('[data-target-container="layout:ROOT-LAYOUT"]')
        assert _visible_svg_text(header.locator(".target-frame-role")) == ["Package layout"]
        title_text = _visible_svg_text(header.locator(".target-frame-title"))
        assert title_text and title_text[0].startswith("shared_segment_")
        assert long_header in header.get_attribute("aria-label")
        assert long_header in header.locator("title").text_content()
        measured_header = header.evaluate(
            "(frame, name) => {const text=frame.querySelector('.target-frame-title');"
            "const box=frame.querySelector('.target-frame-header-hit').getBBox();"
            "const ctx=document.createElement('canvas').getContext('2d');"
            "ctx.font=getComputedStyle(text).font;"
            "return {textWidth:text.getComputedTextLength(),availableWidth:box.width-28,"
            "naturalWidth:ctx.measureText(name).width};}",
            long_header.rsplit(".", 1)[-1],
        )
        assert measured_header["naturalWidth"] > measured_header["availableWidth"]
        assert title_text[0].endswith("…")
        assert measured_header["textWidth"] <= measured_header["availableWidth"] + 1
        header_sizes = header.locator(".target-frame-title").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        assert header_sizes and min(header_sizes) >= 14
        header.focus()
        page.keyboard.press("Space")
        details = " ".join(page.locator(".flow-inspector-content").inner_text().split())
        assert long_header in details
        assert "docs/architecture/shop.md" in details
        root_container = payload["explorers"]["target_diagrams"]["root"]["containers"][
            "layout:ROOT-LAYOUT"
        ]
        expected_children = root_container["members"]
        assert "COMP-STORE" in expected_children
        for child_id in expected_children:
            assert _frame_relation(
                page,
                "layout:ROOT-LAYOUT",
                f'[data-target-node="{child_id}"]',
                "inside",
            )
        header_geometry = header.evaluate(
            "frame => {"
            " const screenBox = element => { const b=element.getBBox(),m=element.getScreenCTM();"
            " const p=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]"
            " ].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));"
            " return {left:Math.min(...p.map(v=>v.x)),right:Math.max(...p.map(v=>v.x)),"
            " top:Math.min(...p.map(v=>v.y)),bottom:Math.max(...p.map(v=>v.y))}; };"
            " const rect=screenBox(frame.previousElementSibling.querySelector('.target-frame'));"
            " const title=screenBox(frame.querySelector('.target-frame-title'));"
            " const open=frame.querySelector('.target-frame-open');"
            " const openBox=open ? screenBox(open) : null;"
            " return {titleInFrame:title.left>=rect.left+8 && title.right<=rect.right-8 &&"
            " title.top>=rect.top+8, noHeaderControlOverlap:!openBox ||"
            " title.right<=openBox.left ||"
            " openBox.right<=title.left || title.bottom<=openBox.top || openBox.bottom<=title.top,"
            " headerBandClear:title.bottom<=rect.bottom-8}; }"
        )
        assert header_geometry["titleInFrame"]
        assert header_geometry["noHeaderControlOverlap"]
        assert header_geometry["headerBandClear"]
        children_clear = header.evaluate(
            "(frame, ids) => { const screenBox=element=>{"
            "const b=element.getBBox(),m=element.getScreenCTM();"
            "const p=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]]"
            ".map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));"
            "return {top:Math.min(...p.map(v=>v.y)),bottom:Math.max(...p.map(v=>v.y))};};"
            "const title=screenBox(frame.querySelector('.target-frame-title'));"
            "return ids.map(id=>{const node=document.querySelector("
            '`[data-target-node="${id}"] .target-card`);'
            "return Boolean(node)&&screenBox(node).top>=title.bottom+12;});}",
            expected_children,
        )
        assert len(children_clear) == len(expected_children) and all(children_clear)
        selected = page.locator('[data-target-node="COMP-STORE"]')
        selected_name = _visible_svg_text(selected.locator(".target-label"))
        selected_responsibilities = _visible_svg_text(selected.locator(".target-responsibility"))
        assert selected_name == [long_name]
        expected_responsibilities = [" ".join(text.split()) for text in long_responsibilities]
        assert selected_responsibilities == expected_responsibilities
        assert all("…" not in text for text in selected_name + selected_responsibilities)

        page.locator('[data-target-node="COMP-ARCHIVE"]').click()
        dim = page.locator('[data-target-node="COMP-STORE"]:not(.selected)')
        assert dim.count() == 1
        dim_name = _visible_svg_text(dim.locator(".target-label"))
        dim_responsibilities = _visible_svg_text(dim.locator(".target-responsibility"))
        assert dim_name == [long_name]
        assert dim_responsibilities == expected_responsibilities
        assert all("…" not in text for text in dim_name + dim_responsibilities)
        sizes = dim.locator("text").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        assert sizes and min(sizes) >= 11
        name_sizes = dim.locator(".target-label").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        assert name_sizes and min(name_sizes) >= 14
        responsibility_sizes = dim.locator(".target-responsibility").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        assert responsibility_sizes and min(responsibility_sizes) >= 13
        readability = dim.evaluate(
            "node => {"
            "const rgba=value=>{const m=value.match(/[\\d.]+/g)?.map(Number)||[0,0,0,1];"
            "return [m[0]||0,m[1]||0,m[2]||0,m.length>3?m[3]:1];};"
            "const blend=(front,back,alpha)=>front.slice(0,3).map("
            "(v,i)=>v*alpha+back[i]*(1-alpha));"
            "const lum=color=>{const c=color.map(v=>{v/=255;"
            "return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});"
            "return .2126*c[0]+.7152*c[1]+.0722*c[2];};"
            "const alphaTo=(element,stop=null)=>{let opacity=1;"
            "for(let current=element;current&&current!==stop;current=current.parentElement)"
            "opacity*=Number(getComputedStyle(current).opacity||1);return opacity;};"
            "let canvas=[255,255,255];const ancestors=[];"
            "for(let current=node.parentElement;current;current=current.parentElement)"
            "ancestors.push(current);ancestors.reverse().forEach(element=>{"
            "const color=rgba(getComputedStyle(element).backgroundColor);"
            "canvas=blend(color,canvas,color[3]);});"
            "const card=node.querySelector('.target-card');"
            "const cardStyle=getComputedStyle(card), cardColor=rgba(cardStyle.fill);"
            "const cardAlpha=cardColor[3]*Number(cardStyle.fillOpacity||1);"
            "const cardLayer=blend(cardColor,canvas,cardAlpha*alphaTo(card,node));"
            "const sharedAlpha=alphaTo(node);"
            "const paintedCard=blend(cardLayer,canvas,sharedAlpha);"
            "return [...node.querySelectorAll('.target-label,.target-responsibility')].map(text=>{"
            "const style=getComputedStyle(text),color=rgba(style.fill);"
            "const textAlpha=color[3]*Number(style.fillOpacity||1)*alphaTo(text,node);"
            "const textLayer=blend(color,cardLayer,textAlpha);"
            "const foreground=blend(textLayer,canvas,sharedAlpha);"
            "const [a,b]=[lum(foreground),lum(paintedCard)].sort((x,y)=>y-x);"
            "const r=(a+.05)/(b+.05);const box=text.getBBox();"
            "return {visible:style.display!=='none'&&style.visibility==='visible'&&"
            "textAlpha*sharedAlpha>0&&box.width>0&&box.height>0,contrast:r};});}"
        )
        assert len(readability) == len(dim.locator(".target-label,.target-responsibility").all())
        assert all(item["visible"] and item["contrast"] >= 4.5 for item in readability)
        bounds = page.locator(".flow-nodes").evaluate(
            "layer => [...layer.querySelectorAll('.target-card')].every(card => {"
            " const box = card.getBBox(); const node = card.parentElement;"
            " const texts=[...node.querySelectorAll('text')];"
            " const contained=texts.every(text => {"
            " const t = text.getBBox(); return t.x >= box.x + 8 &&"
            " t.x + t.width <= box.x + box.width - 8 &&"
            " t.y >= box.y + 8 && t.y + t.height <= box.y + box.height - 8;"
            " }); const noOverlap=texts.every((a,i)=>texts.slice(i+1).every(b=>{"
            " const x=a.getBBox(),y=b.getBBox();return x.x+x.width<=y.x || y.x+y.width<=x.x ||"
            " x.y+x.height<=y.y || y.y+y.height<=x.y;}));return contained&&noOverlap; })"
        )
        assert bounds
    finally:
        browser.close()
        playwright.stop()
