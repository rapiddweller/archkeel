# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_consistent_explorer_acceptance import (
    _replace_flow_payload,
    _target_diagram_page,
    _visible_svg_text,
    _walk,
)
from test_target_hierarchy_independent_acceptance import _ce_nested_route_page


def _activate_card(page: Any, card: Any, mode: str) -> None:
    if mode == "click":
        card.click()
    elif mode == "touch":
        card.tap()
    else:
        focused = False
        for _ in range(100):
            page.keyboard.press("Tab")
            focused = card.evaluate(
                "node => node === document.activeElement || node.contains(document.activeElement)"
            )
            if focused:
                break
        assert focused, "Tab did not reach the target card"
        page.keyboard.press("Space")
    assert card.get_attribute("aria-pressed") == "true"


def _set_details(page: Any, mode: str, opened: bool) -> None:
    toggle = page.locator("[data-flow-details-toggle]")
    assert toggle.is_visible()
    if (toggle.get_attribute("aria-expanded") == "true") != opened:
        if mode == "click":
            toggle.click()
        elif mode == "touch":
            toggle.tap()
        else:
            toggle.focus()
            page.keyboard.press("Space")
    assert (toggle.get_attribute("aria-expanded") == "true") == opened


def test_target_compact_labels_keep_exact_selected_details(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    prefix = "datamimic_ce.runtime.configuration." + "shared_segment_" * 4
    identities = {
        "COMP-STORE": prefix + "store_backend",
        "COMP-ARCHIVE": prefix + "store_backup",
    }
    nodes = {
        node["id"]: node
        for node in _walk(payload["explorers"]["target"])
        if node.get("id") in identities
    }
    assert set(nodes) == set(identities)
    for node_id, label in identities.items():
        node = nodes[node_id]
        responsibilities = [
            detail["value"]
            for detail in node["details"]
            if detail.get("label") == "Responsibility" and not detail.get("missing")
        ]
        assert responsibilities
        node["label"] = label
        for layout in [
            payload["explorers"]["target_diagrams"]["root"],
            *payload["explorers"]["target_diagrams"]["nested"].values(),
        ]:
            for card in layout["nodes"]:
                if card.get("id") == node_id:
                    card["label"] = label
                    card["details"] = deepcopy(node["details"])
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        for mode in ("click", "space", "touch"):
            context = browser.new_context(
                viewport={"width": 1024, "height": 768}, has_touch=mode == "touch"
            )
            page = context.new_page()
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            cards = {
                node_id: page.locator(f'[data-target-node="{node_id}"]') for node_id in identities
            }
            assert all(card.count() == 1 and card.is_visible() for card in cards.values())
            labels = {
                node_id: _visible_svg_text(card.locator(".target-label"))[0]
                for node_id, card in cards.items()
            }
            assert len(set(labels.values())) == len(identities)

            for node_id, card in cards.items():
                inspector = page.locator("#flow-inspector")
                assert not inspector.is_visible()
                _activate_card(page, card, mode)
                selected = page.locator(
                    f'.flow-selected-responsibility[data-declaration-id="{node_id}"]'
                )
                assert selected.count() == 1
                assert selected.get_attribute("data-declaration-id") == node_id
                selected_text = " ".join(selected.inner_text().split())
                assert selected_text

                _set_details(page, mode, True)
                assert inspector.is_visible()
                details = " ".join(page.locator(".flow-inspector-content").inner_text().split())
                assert identities[node_id] in details
                responsibilities = [
                    detail["value"]
                    for detail in nodes[node_id]["details"]
                    if detail.get("label") == "Responsibility" and not detail.get("missing")
                ]
                assert all(" ".join(sentence.split()) in details for sentence in responsibilities)
                _set_details(page, mode, False)
            context.close()
    finally:
        browser.close()
        playwright.stop()


def test_actual_module_inspector_preserves_exact_file_metadata(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    physical = {
        node["id"]: node
        for node in _walk(payload["explorers"]["actual"])
        if node.get("id") == "shop.cli.main"
    }
    assert set(physical) == {"shop.cli.main"}
    file_detail = next(
        detail["value"]
        for detail in physical["shop.cli.main"]["details"]
        if detail.get("label") == "File"
    )

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.set_content(page_html, wait_until="load")
        page.locator('[data-flow-view="actual"]').click()
        for projection_id in ("shop", "shop.cli"):
            entry = page.locator(f'[data-projection-id="{projection_id}"]')
            assert entry.count() == 1 and entry.is_visible()
            entry.focus()
            page.keyboard.press("Enter")
        module = page.locator('[data-projection-id="shop.cli.main"]')
        assert module.count() == 1 and module.is_visible()
        module.click()
        assert module.get_attribute("aria-pressed") == "true"
        _set_details(page, "click", True)
        details = " ".join(page.locator(".flow-inspector-content").inner_text().split())
        assert module.get_attribute("data-projection-id") == "shop.cli.main"
        assert file_detail in details
    finally:
        browser.close()
        playwright.stop()


def test_long_target_frame_header_measured_bounds_and_route_identity(
    tmp_path: Path,
) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    frame_id = "layout:ROOT-LAYOUT"
    long_header = "datamimic_ce.engine." + "namespace_part." * 8 + "backend"
    container = payload["explorers"]["target_diagrams"]["root"]["containers"][frame_id]
    container["scope"] = long_header
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.set_content(page_html, wait_until="load")
        page.locator('[data-flow-view="target"]').click()
        page.locator("[data-flow-details-toggle]").click()
        frame = page.locator(f'[data-target-container="{frame_id}"]')
        assert frame.count() == 1 and frame.is_visible()
        title = frame.locator(".target-frame-title")
        title_box = title.bounding_box()
        frame_box = frame.evaluate(
            "node => {const plate=node.previousElementSibling.querySelector('.target-frame');"
            "const b=plate.getBBox(),m=plate.getScreenCTM();"
            "const p=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],"
            "[b.x+b.width,b.y+b.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));"
            "return {left:Math.min(...p.map(v=>v.x)),right:Math.max(...p.map(v=>v.x)),"
            "top:Math.min(...p.map(v=>v.y)),bottom:Math.max(...p.map(v=>v.y))};}"
        )
        assert _visible_svg_text(title)
        assert title_box
        natural_width = title.evaluate(
            "(node, text) => {const style=getComputedStyle(node),"
            "canvas=document.createElement('canvas'),"
            "ctx=canvas.getContext('2d');ctx.font=style.font;return ctx.measureText(text).width;}",
            long_header,
        )
        displayed = title.evaluate(
            "node => {const tspans=[...node.querySelectorAll('tspan')];"
            "const lines=tspans.length?tspans:[node];"
            "return {lineWidths:lines.map(line=>line.getComputedTextLength()),"
            "text:node.textContent.replace(/\\s+/g,' ').trim()};}"
        )
        available_width = frame_box["right"] - frame_box["left"] - 16
        assert natural_width > available_width, "fixture did not create measured title overflow"
        assert len(displayed["lineWidths"]) == 1
        assert max(displayed["lineWidths"]) < natural_width
        assert title_box["x"] >= frame_box["left"] + 8
        assert title_box["x"] + title_box["width"] <= frame_box["right"] - 8
        assert title_box["y"] >= frame_box["top"] + 8
        assert title_box["y"] + title_box["height"] <= frame_box["bottom"] - 8

        children = container["members"]
        gaps = frame.evaluate(
            "(frame, ids) => {const title=frame.querySelector('.target-frame-title')"
            ".getBoundingClientRect();"
            "return ids.map(id=>{const child=document.querySelector("
            '`[data-target-node="${id}"] .target-card`);'
            "return Boolean(child)&&child.getBoundingClientRect().top-title.bottom;});}",
            children,
        )
        assert gaps and min(gaps) >= 12

        edges = page.locator(".flow-edges .edge").all()
        assert edges
        for edge in edges:
            paths = edge.locator("path").evaluate_all(
                "nodes => Object.fromEntries(nodes.map(node=>["
                "[...node.classList].find(name=>name==='line'||name==='hit')||'',"
                "node.getAttribute('d')]))"
            )
            assert paths.get("line") and paths.get("line") == paths.get("hit")
        for line in page.locator(".flow-edges .edge path.line").all():
            crosses_header = line.evaluate(
                "(path, box) => {const m=path.getScreenCTM(),length=path.getTotalLength();"
                "for(let d=0;d<=length;d+=0.5){const p=new DOMPoint(path.getPointAtLength(d).x,"
                "path.getPointAtLength(d).y).matrixTransform(m);if(p.x>=box.x-1&&"
                "p.x<=box.x+box.width+1&&p.y>=box.y-1&&p.y<=box.y+box.height+1)return true;}"
                "return false;}",
                title_box,
            )
            assert not crosses_header

        container["scope"] = "datamimic_ce"
        short_html = _replace_flow_payload(page_html, payload)
        page.set_content(short_html, wait_until="load")
        page.locator('[data-flow-view="target"]').click()
        page.locator("[data-flow-details-toggle]").click()
        short_title = page.locator(f'[data-target-container="{frame_id}"] .target-frame-title')
        assert _visible_svg_text(short_title) == ["datamimic_ce"]
    finally:
        browser.close()
        playwright.stop()


def test_four_views_keep_explorer_height_and_shared_anchors(tmp_path: Path) -> None:
    page_html, _ = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_content(page_html, wait_until="load")
        page.evaluate(
            "document.fonts.ready.then(() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve))))"
        )
        measurements: dict[str, dict[str, dict[str, float]]] = {}
        for view in ("diagram", "actual", "target", "diff"):
            button = page.locator(f'[data-flow-view="{view}"]')
            button.click()
            page.evaluate(
                "new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )
            assert button.get_attribute("aria-pressed") == "true"
            measurements[view] = page.locator("#flow").evaluate(
                "root => {const box=el=>{const r=el.getBoundingClientRect();"
                "return {top:r.top+scrollY,height:r.height,bottom:r.bottom+scrollY};};"
                "const find=selector=>{const el=root.querySelector(selector);"
                "if(!el||!el.getClientRects().length)"
                "throw Error('missing visible anchor '+selector);"
                "return box(el);};return {explorer:box(root),tabs:find('.flow-views'),"
                "toolbar:find('.flow-toolbar'),layout:find('.flow-layout'),legend:find('.flow-legend')};}"
            )
        reference = measurements["diagram"]
        for view, anchors in measurements.items():
            for anchor in reference:
                assert abs(anchors[anchor]["top"] - reference[anchor]["top"]) <= 2, (
                    view,
                    anchor,
                    anchors[anchor],
                    reference[anchor],
                )
                assert abs(anchors[anchor]["height"] - reference[anchor]["height"]) <= 2, (
                    view,
                    anchor,
                    anchors[anchor],
                    reference[anchor],
                )
    finally:
        browser.close()
        playwright.stop()


def test_engine_frame_header_routes_clear_of_exact_incoming_edges(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    frame_id = "layout:LAYOUT-ENGINE"
    assert frame_id in payload["explorers"]["target_diagrams"]["root"]["containers"]
    payload["components"] = [
        component for component in payload["components"] if component["label"] not in {"dsl", "io"}
    ]
    sources = {
        "authoring": "datamimic_ce.authoring",
        "interfaces": "datamimic_ce.interfaces",
        "resources": "datamimic_ce.resources",
    }
    for label, package in sources.items():
        payload["components"].append(
            {
                "declared_component": f"COMP-{label.upper()}",
                "inner_edges": [],
                "inside": None,
                "label": label,
                "modules": [package],
                "public": [],
                "requires": [],
            }
        )
        payload["edges"].append(
            {
                "import_sites": 1,
                "names": ["runtime"],
                "requirement": {},
                "rule_ids": [],
                "sites": [f"{package.replace('.', '/')}/__init__.py:1"],
                "source": label,
                "state": "conforms",
                "target": "runtime",
            }
        )
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_content(page_html, wait_until="load")
        page.evaluate(
            "document.fonts.ready.then(() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve))))"
        )
        page.locator('[data-flow-view="diagram"]').click()
        frame = page.locator(f'[data-diagram-frame="{frame_id}"]')
        assert frame.count() == 1 and frame.is_visible()
        title = frame.locator(".target-frame-title")
        assert title.is_visible()
        header_box = frame.locator(".target-frame-header-hit").bounding_box()
        assert header_box
        edge_keys = [f"{source}>runtime" for source in sources]
        visible_edge_keys = page.locator(".flow-edges .edge .hit").evaluate_all(
            "nodes => nodes.map(node=>node.getAttribute('data-key'))"
        )
        collisions: list[str] = []
        for key in edge_keys:
            hit = page.locator(f'.flow-edges .edge .hit[data-key="{key}"]')
            assert hit.count() == 1, (key, visible_edge_keys)
            route = hit.evaluate(
                "(hit, box) => {const edge=hit.closest('g.edge');"
                "const parts=Object.fromEntries(['line','hit','pulse'].map(name=>[name,"
                "edge?.querySelector('path.'+name)?.getAttribute('d')]));"
                "const path=edge?.querySelector('path.line');if(!path)return {parts,crosses:false};"
                "const m=path.getScreenCTM(),length=path.getTotalLength();"
                "const step=0.5/Math.max(1,Math.hypot(m.a,m.b));"
                "for(let d=0;d<=length;d+=step){const p=new DOMPoint(path.getPointAtLength(d).x,"
                "path.getPointAtLength(d).y).matrixTransform(m);if(p.x>=box.x-1&&"
                "p.x<=box.x+box.width+1&&p.y>=box.y-1&&p.y<=box.y+box.height+1)"
                "return {parts,crosses:true};}return {parts,crosses:false};}",
                header_box,
            )
            path_data = route["parts"]
            assert path_data.get("line") and path_data.get("line") == path_data.get("hit")
            assert path_data.get("pulse") == path_data.get("line")
            if route["crosses"]:
                collisions.append(key)
        assert not collisions, {"incoming_edges": edge_keys, "header_collisions": collisions}
    finally:
        browser.close()
        playwright.stop()


def test_long_frame_scope_remains_available_in_keyboard_details(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    frame_id = "layout:ROOT-LAYOUT"
    long_scope = "shop.namespace_part." + "shared_segment_" * 5 + "backend"
    container = payload["explorers"]["target_diagrams"]["root"]["containers"][frame_id]
    layout = next(
        node for node in _walk(payload["explorers"]["target"]) if node.get("id") == frame_id
    )
    container["scope"] = long_scope
    layout["label"] = long_scope
    layout["_layout_scope"] = long_scope
    layout["details"] = [
        {"label": "Layout scope", "value": long_scope},
        {"label": "Provenance", "value": "docs/architecture/shop.md"},
        *[detail for detail in layout["details"] if detail.get("label") != "Provenance"],
    ]
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.set_content(page_html, wait_until="load")
        page.evaluate(
            "document.fonts.ready.then(() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve))))"
        )
        page.locator('[data-flow-view="target"]').click()
        frame = page.locator(f'[data-target-container="{frame_id}"]')
        assert frame.count() == 1 and frame.is_visible()
        frame.focus()
        page.keyboard.press("Space")
        assert frame.get_attribute("aria-pressed") == "true"
        toggle = page.locator("[data-flow-details-toggle]")
        assert toggle.get_attribute("aria-expanded") == "false"
        toggle.focus()
        page.keyboard.press("Space")
        assert toggle.get_attribute("aria-expanded") == "true"
        inspector = page.locator("#flow-inspector")
        assert inspector.is_visible()
        details = " ".join(page.locator(".flow-inspector-content").inner_text().split())
        assert long_scope in details
        assert "docs/architecture/shop.md" in details
        assert _visible_svg_text(frame.locator(".target-frame-title"))
    finally:
        browser.close()
        playwright.stop()
