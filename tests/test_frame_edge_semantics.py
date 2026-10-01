# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_consistent_explorer_acceptance import _replace_flow_payload
from test_target_hierarchy_independent_acceptance import (
    _ce_nested_route_page,
    _cross_frame_domains_page,
)


def _add_external_target_owners(payload: dict[str, Any]) -> None:
    graph = payload["explorers"]["target_diagrams"]["root"]
    target_records = payload["explorers"]["target"]
    template_node = next(node for node in graph["nodes"] if node.get("id") == "COMP-DOMAINS")
    template_record = next(node for node in target_records if node.get("id") == "COMP-DOMAINS")
    root_frame = graph["containers"]["layout:LAYOUT-ROOT"]
    root_layout = next(node for node in graph["nodes"] if node.get("id") == "layout:LAYOUT-ROOT")
    layout_record = next(node for node in target_records if node.get("id") == "layout:LAYOUT-ROOT")
    allowed = [
        "datamimic_ce.authoring",
        "datamimic_ce.domains",
        "datamimic_ce.engine",
        "datamimic_ce.resources",
    ]
    root_frame["members"].extend(["COMP-AUTHORING", "COMP-RESOURCES"])
    root_layout["details"] = [{"label": "Allowed children", "value": ", ".join(allowed)}]
    layout_record["details"] = deepcopy(root_layout["details"])
    layout_record["children"].extend(
        {
            "id": f"physical:{package}",
            "kind": "physical_child",
            "label": package,
            "details": [{"label": "Allowed by", "value": "datamimic_ce"}],
            "children": [],
        }
        for package in ("datamimic_ce.authoring", "datamimic_ce.resources")
    )
    for component_id, label, package in (
        ("COMP-AUTHORING", "authoring", "datamimic_ce.authoring"),
        ("COMP-RESOURCES", "resources", "datamimic_ce.resources"),
    ):
        details = [
            {"label": "Packages", "value": package},
            {"label": "Declared namespace", "value": package},
            {"label": "Public interface", "value": "Explicitly empty"},
            {"label": "Provenance", "value": "docs/architecture/ce.md"},
            {"label": "Responsibility", "value": f"Own {label} behavior."},
        ]
        target_node = deepcopy(template_node)
        target_node.update(
            id=component_id,
            label=label,
            details=details,
            dependency_rank=-1,
            placement={
                "container": "layout:LAYOUT-ROOT",
                "scopes": [package],
                "status": "declared",
            },
        )
        graph["nodes"].append(target_node)
        edge = {
            "declaration": f"requires:{component_id}:runtime",
            "details": [
                {"label": "Rationale", "value": f"{label} uses runtime."},
                {"label": "Through", "value": "Entire public interface"},
                {"label": "Provenance", "value": "docs/architecture/ce.md"},
                {"label": "Decided by", "value": "architect"},
            ],
            "kind": "requires",
            "label": "requires runtime",
            "source": component_id,
            "target": "COMP-RUNTIME",
        }
        graph["edges"].append(edge)
        record = deepcopy(template_record)
        record.update(
            id=component_id,
            label=label,
            details=details,
            children=[
                {
                    "id": edge["declaration"],
                    "kind": "requires",
                    "label": edge["label"],
                    "details": deepcopy(edge["details"]),
                    "children": [],
                }
            ],
            placement=deepcopy(target_node["placement"]),
            _placement_namespace=package,
            _placement_scope_key=label,
            _placement_scopes=[package],
        )
        target_records.append(record)


def test_target_edges_attach_to_exact_framed_cards_with_clear_tangents(tmp_path: Path) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path)
    _add_external_target_owners(payload)
    graph = payload["explorers"]["target_diagrams"]["root"]
    frame_id = "layout:LAYOUT-ENGINE"
    assert frame_id in graph["containers"]
    assert {"COMP-RUNTIME", "COMP-IO"} <= set(graph["containers"][frame_id]["members"])
    assert "COMP-DOMAINS" not in graph["containers"][frame_id]["members"]
    expected = {
        edge["declaration"]: edge
        for edge in graph["edges"]
        if edge["source"] in {"COMP-AUTHORING", "COMP-RESOURCES"}
    }
    assert set(expected) == {
        "requires:COMP-AUTHORING:runtime",
        "requires:COMP-RESOURCES:runtime",
    }
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
        page.locator('[data-flow-view="target"]').click()
        page.evaluate(
            "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )

        frame = page.locator(f'[data-target-container="{frame_id}"]')
        assert frame.count() == 1 and frame.is_visible()
        header = frame.locator(".target-frame-header-hit").bounding_box()
        assert header
        observed: dict[str, dict[str, Any]] = {}
        for declaration, edge_data in expected.items():
            hit = page.locator(f'[data-target-edge="{declaration}"]')
            assert hit.count() == 1 and hit.is_visible(), declaration
            route = hit.evaluate(
                "(edge, ids) => {"
                "const line=edge?.querySelector('path.line'),"
                "hitPath=edge?.querySelector('path.hit');"
                "if(!line||!hitPath)return {missing:true};"
                "const m=line.getScreenCTM(),length=line.getTotalLength();"
                "const scale=Math.max(1,Math.hypot(m.a,m.b)),step=0.5/scale;"
                "const point=s=>{const p=line.getPointAtLength(Math.max(0,Math.min(length,s)));"
                "const q=new DOMPoint(p.x,p.y).matrixTransform(m);return {x:q.x,y:q.y};};"
                "const box=id=>{const "
                'card=document.querySelector(`[data-target-node="${id}"] .target-card`);'
                "if(!card)return null;const r=card.getBoundingClientRect();"
                "return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};};"
                "const rects={source:box(ids.source),target:box(ids.target)};"
                "const start=point(0),startNear=point(step),end=point(length),"
                "endNear=point(length-step);"
                "const sides=(p,r)=>{const ds={left:Math.abs(p.x-r.left),"
                "right:Math.abs(p.x-r.right),"
                "top:Math.abs(p.y-r.top),bottom:Math.abs(p.y-r.bottom)};"
                "return Object.keys(ds).sort((a,b)=>ds[a]-ds[b])[0];};"
                "const err=(p,r)=>Math.min(Math.abs(p.x-r.left),Math.abs(p.x-r.right),"
                "Math.abs(p.y-r.top),Math.abs(p.y-r.bottom));"
                "const normal=(side)=>({left:[-1,0],right:[1,0],top:[0,-1],bottom:[0,1]})[side];"
                "const dot=(a,b,n)=>((b.x-a.x)*n[0]+(b.y-a.y)*n[1]);"
                "const sourceSide=sides(start,rects.source);"
                "const targetSide=sides(end,rects.target);"
                "const header=ids.header;"
                "let crossesHeader=false;for(let s=0;s<=length;s+=step){const p=point(s);"
                "if(p.x>=header.x-1&&p.x<=header.x+header.width+1&&p.y>=header.y-1&&"
                "p.y<=header.y+header.height+1){crossesHeader=true;break;}}"
                "const parts={line:line.getAttribute('d'),hit:hitPath.getAttribute('d'),"
                "pulse:edge.querySelector('path.pulse')?.getAttribute('d')||null};"
                "const "
                "frame=document.querySelector('[data-target-container=\"layout:LAYOUT-ENGINE\"]');"
                "const frameShape=frame?.querySelector('rect.target-frame')||"
                "frame?.previousElementSibling.querySelector('rect.target-frame');"
                "const fr=frameShape?.getBoundingClientRect();"
                "return {parts,"
                "rects,start,startNear,end,endNear,startError:err(start,rects.source),"
                "endError:err(end,rects.target),sourceSide,targetSide,"
                "step:step*scale,"
                "sourceOutward:dot(start,startNear,normal(sourceSide)),"
                "targetOutward:dot(end,endNear,normal(targetSide)),crossesHeader,"
                "sourceInsideFrame:fr&&start.x>=fr.left&&start.x<=fr.right&&"
                "start.y>=fr.top&&start.y<=fr.bottom,targetInsideFrame:fr&&end.x>=fr.left&&"
                "end.x<=fr.right&&end.y>=fr.top&&end.y<=fr.bottom};}",
                {"source": edge_data["source"], "target": edge_data["target"], "header": header},
            )
            observed[declaration] = route

        assert set(observed) == set(expected)
        failures: dict[str, dict[str, Any]] = {}
        for declaration, route in observed.items():
            problems = []
            if not route["parts"]["line"] or route["parts"]["line"] != route["parts"]["hit"]:
                problems.append("line/hit geometry differs")
            if route["parts"]["pulse"] is not None:
                problems.append("Target requirement unexpectedly has a pulse path")
            if route["startError"] > 1 or route["endError"] > 8:
                problems.append("endpoint is not attached to its exact component card")
            if route["sourceOutward"] < route["step"] / 2:
                problems.append("source path does not leave its card outward")
            if route["targetOutward"] < route["step"] / 2:
                problems.append("target path does not approach its card inward")
            if route["sourceInsideFrame"] or not route["targetInsideFrame"]:
                problems.append("component endpoint confused with physical frame boundary")
            if route["crossesHeader"]:
                problems.append("relationship crosses the engine header band")
            if problems:
                failures[declaration] = {
                    "problems": problems,
                    "startError": route["startError"],
                    "endError": route["endError"],
                    "sourceOutward": route["sourceOutward"],
                    "targetOutward": route["targetOutward"],
                    "step": route["step"],
                    "sourceSide": route["sourceSide"],
                    "targetSide": route["targetSide"],
                    "start": route["start"],
                    "end": route["end"],
                    "crossesHeader": route["crossesHeader"],
                    "sourceInsideFrame": route["sourceInsideFrame"],
                    "targetInsideFrame": route["targetInsideFrame"],
                }
        assert not failures, failures
    finally:
        browser.close()
        playwright.stop()


def test_physical_side_detour_keeps_endpoint_normals_and_avoids_unrelated_cards(
    tmp_path: Path,
) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    payload["components"] = [
        component for component in payload["components"] if component["label"] not in {"dsl", "io"}
    ]
    for label, package in (
        ("authoring", "datamimic_ce.authoring"),
        ("interfaces", "datamimic_ce.interfaces"),
        ("resources", "datamimic_ce.resources"),
    ):
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
        diagram_tab = page.locator('[data-flow-view="diagram"]')
        assert diagram_tab.get_attribute("aria-pressed") == "true"
        page.evaluate(
            "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        frame = page.locator('[data-diagram-frame="layout:LAYOUT-ENGINE"]')
        assert frame.count() == 1 and frame.is_visible()
        header = frame.locator(".target-frame-header-hit").bounding_box()
        assert header
        edge = page.locator('.flow-edges .edge .hit[data-key="resources>runtime"]')
        assert edge.count() == 1 and edge.is_visible()
        route = edge.evaluate(
            "(hit, headerBox) => {const edge=hit.closest('g.edge');"
            "const line=edge?.querySelector('path.line'),hitPath=edge?.querySelector('path.hit'),"
            "pulse=edge?.querySelector('path.pulse');"
            "if(!line||!hitPath||!pulse)return {missing:true};"
            "const m=line.getScreenCTM(),length=line.getTotalLength(),"
            "step=0.5/Math.max(1,Math.hypot(m.a,m.b));"
            "const point=s=>{const p=line.getPointAtLength(Math.max(0,Math.min(length,s)));"
            "const q=new DOMPoint(p.x,p.y).matrixTransform(m);return {x:q.x,y:q.y};};"
            "const card=label=>{const node=document.querySelector(`.flow-nodes "
            '.node[data-label="${label}"]`);'
            "const rect=node?.querySelector('rect.card');if(!rect)return null;"
            "const r=rect.getBoundingClientRect();return {left:r.left,right:r.right,"
            "top:r.top,bottom:r.bottom};};"
            "const source=card('resources'),target=card('runtime'),start=point(0),"
            "end=point(length),"
            "startNear=point(step),endNear=point(length-step);"
            "const sides=(p,r)=>{const ds={left:Math.abs(p.x-r.left),right:Math.abs(p.x-r.right),"
            "top:Math.abs(p.y-r.top),bottom:Math.abs(p.y-r.bottom)};"
            "return Object.keys(ds).sort((a,b)=>ds[a]-ds[b])[0];};"
            "const err=(p,r)=>Math.min(Math.abs(p.x-r.left),Math.abs(p.x-r.right),"
            "Math.abs(p.y-r.top),Math.abs(p.y-r.bottom));"
            "const norm=side=>({left:[-1,0],right:[1,0],top:[0,-1],bottom:[0,1]})[side];"
            "const dot=(a,b,n)=>(b.x-a.x)*n[0]+(b.y-a.y)*n[1];"
            "const sourceSide=sides(start,source),targetSide=sides(end,target),"
            "sourceOutward=dot(start,startNear,norm(sourceSide)),"
            "targetOutward=dot(end,endNear,norm(targetSide));"
            "let crossesHeader=false,crossesUnrelated=[];"
            "const otherCards=[...document.querySelectorAll('.flow-nodes .node')].filter(n=>"
            "!['resources','runtime'].includes(n.dataset.label)).map(n=>({label:n.dataset.label,"
            "r:n.querySelector('rect.card')?.getBoundingClientRect()})).filter(item=>item.r);"
            "for(let s=0;s<=length;s+=step){const p=point(s);"
            "if(p.x>=headerBox.x-1&&p.x<=headerBox.x+headerBox.width+1&&"
            "p.y>=headerBox.y-1&&p.y<=headerBox.y+headerBox.height+1)crossesHeader=true;"
            "for(const item of otherCards){if(p.x>item.r.left+1&&p.x<item.r.right-1&&"
            "p.y>item.r.top+1&&p.y<item.r.bottom-1&&!crossesUnrelated.includes(item.label))"
            "crossesUnrelated.push(item.label);}}"
            "const frame= document.querySelector('[data-diagram-frame=\"layout:LAYOUT-ENGINE\"]');"
            "const frameRect=frame?.querySelector('rect.target-frame')?.getBoundingClientRect();"
            "return {line:line.getAttribute('d'),hit:hitPath.getAttribute('d'),"
            "pulse:pulse.getAttribute('d'),"
            "source,target,start,end,startError:err(start,source),endError:err(end,target),"
            "sourceSide,targetSide,sourceOutward,targetOutward,step:step*Math.max(1,"
            "Math.hypot(m.a,m.b)),"
            "crossesHeader,crossesUnrelated,"
            "otherCards:otherCards.map(item=>({label:item.label,left:item.r.left,"
            "right:item.r.right,"
            "top:item.r.top,bottom:item.r.bottom})),"
            "sourceInsideFrame:frameRect&&start.x>=frameRect.left&&start.x<=frameRect.right&&"
            "start.y>=frameRect.top&&start.y<=frameRect.bottom,targetInsideFrame:frameRect&&"
            "end.x>=frameRect.left&&end.x<=frameRect.right&&end.y>=frameRect.top&&end.y<=frameRect.bottom};}",
            header,
        )
        assert not route.get("missing"), "Diagram line, hit, and pulse paths must all exist"
        assert route["line"] == route["hit"] == route["pulse"]
        assert route["startError"] <= 1 and route["endError"] <= 8, route
        assert route["sourceInsideFrame"] is False and route["targetInsideFrame"] is True, route
        assert route["crossesHeader"] is False, route
        assert route["sourceOutward"] >= route["step"] / 2, route
        assert route["targetOutward"] >= route["step"] / 2, route
        assert not route["crossesUnrelated"], route
    finally:
        browser.close()
        playwright.stop()


def test_upward_target_edge_exits_side_before_engine_header(tmp_path: Path) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path)
    _add_external_target_owners(payload)
    graph = payload["explorers"]["target_diagrams"]["root"]
    declaration = "requires:COMP-RUNTIME:authoring"
    graph["edges"].append(
        {
            "declaration": declaration,
            "details": [],
            "kind": "requires",
            "label": "requires domains",
            "source": "COMP-RUNTIME",
            "target": "COMP-AUTHORING",
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
        page.locator('[data-flow-view="target"]').click()
        page.evaluate(
            "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        frame = page.locator('[data-target-container="layout:LAYOUT-ENGINE"]')
        source = page.locator('[data-target-node="COMP-RUNTIME"] .target-card')
        target = page.locator('[data-target-node="COMP-AUTHORING"] .target-card')
        edge = page.locator(f'[data-target-edge="{declaration}"]')
        assert frame.count() == source.count() == target.count() == edge.count() == 1
        header = frame.locator(".target-frame-header-hit").bounding_box()
        source_box = source.bounding_box()
        target_box = target.bounding_box()
        assert header and source_box and target_box
        route = edge.evaluate(
            "(edge, ids) => {const line=edge.querySelector('path.line'),"
            "hit=edge.querySelector('path.hit');"
            "if(!line||!hit)return {missing:true};const m=line.getScreenCTM(),"
            "length=line.getTotalLength(),"
            "step=0.5/Math.max(1,Math.hypot(m.a,m.b));"
            "const point=s=>{const p=line.getPointAtLength(Math.max(0,Math.min(length,s)));"
            "const q=new DOMPoint(p.x,p.y).matrixTransform(m);return {x:q.x,y:q.y};};"
            "const box=id=>{const "
            'e=document.querySelector(`[data-target-node="${id}"] .target-card`);'
            "const r=e.getBoundingClientRect();return {left:r.left,right:r.right,"
            "top:r.top,bottom:r.bottom};};"
            "const side=(p,r)=>Object.entries({left:Math.abs(p.x-r.left),"
            "right:Math.abs(p.x-r.right),"
            "top:Math.abs(p.y-r.top),bottom:Math.abs(p.y-r.bottom)}).sort((a,b)=>a[1]-b[1])[0][0];"
            "const normal=s=>({left:[-1,0],right:[1,0],top:[0,-1],bottom:[0,1]})[s];"
            "const dot=(a,b,n)=>(b.x-a.x)*n[0]+(b.y-a.y)*n[1];"
            "const a=box(ids.source),b=box(ids.target),start=point(0),near=point(step),"
            "sourceSide=side(start,a);let crossesHeader=false;"
            "for(let s=0;s<=length;s+=step){const p=point(s);if(p.x>=ids.header.x-1&&"
            "p.x<=ids.header.x+ids.header.width+1&&p.y>=ids.header.y-1&&"
            "p.y<=ids.header.y+ids.header.height+1)crossesHeader=true;}"
            "return {d:line.getAttribute('d'),hit:hit.getAttribute('d'),source:a,"
            "target:b,start,near,"
            "sourceSide,sourceOutward:dot(start,near,normal(sourceSide)),"
            "step:step*Math.max(1,Math.hypot(m.a,m.b)),"
            "crossesHeader};}",
            {
                "source": "COMP-RUNTIME",
                "target": "COMP-AUTHORING",
                "header": header,
            },
        )
        assert not route.get("missing"), route
        assert source_box["y"] >= header["y"] + header["height"] - 2, {
            "header": header,
            "source": source_box,
        }
        assert target_box["y"] + target_box["height"] < source_box["y"], {
            "source": source_box,
            "target": target_box,
        }
        assert route["sourceSide"] in {"left", "right"}, route
        assert route["sourceOutward"] >= route["step"] / 2, route
        assert not route["crossesHeader"], route
        assert route["d"] == route["hit"], route
    finally:
        browser.close()
        playwright.stop()


def test_engine_frame_source_attaches_outward_from_horizontal_side(tmp_path: Path) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path)
    _add_external_target_owners(payload)
    graph = payload["explorers"]["target_diagrams"]["root"]
    declaration = "requires:layout:LAYOUT-ENGINE:COMP-DOMAINS"
    graph["edges"].append(
        {
            "declaration": declaration,
            "details": [],
            "kind": "requires",
            "label": "requires domains",
            "source": "layout:LAYOUT-ENGINE",
            "target": "COMP-DOMAINS",
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
        page.locator('[data-flow-view="target"]').click()
        page.evaluate(
            "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        frame = page.locator('[data-target-container="layout:LAYOUT-ENGINE"]')
        target = page.locator('[data-target-node="COMP-DOMAINS"] .target-card')
        edge = page.locator(f'[data-target-edge="{declaration}"]')
        assert frame.count() == target.count() == edge.count() == 1
        frame_box = frame.evaluate(
            "e => {const r=e.querySelector('rect.target-frame')||"
            "e.previousElementSibling?.querySelector('rect.target-frame');"
            "if(!r)return null;const b=r.getBoundingClientRect();"
            "return {x:b.x,y:b.y,width:b.width,height:b.height};}"
        )
        target_box = target.bounding_box()
        assert frame_box and target_box
        frame_rect = {
            "left": frame_box["x"],
            "right": frame_box["x"] + frame_box["width"],
            "top": frame_box["y"],
            "bottom": frame_box["y"] + frame_box["height"],
        }
        route = edge.evaluate(
            "(edge, ids) => {const line=edge.querySelector('path.line'),"
            "hit=edge.querySelector('path.hit');"
            "if(!line||!hit)return {missing:true};const m=line.getScreenCTM(),"
            "length=line.getTotalLength(),"
            "step=0.5/Math.max(1,Math.hypot(m.a,m.b));"
            "const point=s=>{const p=line.getPointAtLength(Math.max(0,Math.min(length,s)));"
            "const q=new DOMPoint(p.x,p.y).matrixTransform(m);return {x:q.x,y:q.y};};"
            "const start=point(0),near=point(step),r=ids.frame;"
            "const sides={left:Math.abs(start.x-r.left),right:Math.abs(start.x-r.right),"
            "top:Math.abs(start.y-r.top),bottom:Math.abs(start.y-r.bottom)};"
            "const sourceSide=Object.entries(sides).sort((a,b)=>a[1]-b[1])[0][0];"
            "const n=({left:[-1,0],right:[1,0],top:[0,-1],bottom:[0,1]})[sourceSide];"
            "const outward=(near.x-start.x)*n[0]+(near.y-start.y)*n[1];"
            "return {d:line.getAttribute('d'),hit:hit.getAttribute('d'),start,near,sourceSide,"
            "startError:Math.min(...Object.values(sides)),outward,"
            "step:step*Math.max(1,Math.hypot(m.a,m.b))};}",
            {"frame": frame_rect},
        )
        assert not route.get("missing"), route
        assert target_box["x"] + target_box["width"] < frame_rect["left"], {
            "frame": frame_rect,
            "target": target_box,
        }
        assert route["sourceSide"] == "left", route
        assert route["startError"] <= 1, route
        assert route["outward"] >= route["step"] / 2, route
        assert route["d"] == route["hit"], route
    finally:
        browser.close()
        playwright.stop()


def test_unroutable_drag_keeps_edge_and_explains_layout_warning_for_all_inputs(
    tmp_path: Path,
) -> None:
    page_html, payload = _cross_frame_domains_page(
        tmp_path,
        observed_cross_frame_edge=True,
        incoming_engine_requirements=True,
    )
    expected_inventory = {component["label"] for component in payload["components"]}
    expected_edges = {f"{edge['source']}>{edge['target']}" for edge in payload["edges"]}
    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    problems: dict[str, list[str]] = {}
    observed: dict[str, dict[str, Any]] = {}
    try:
        for mode in ("mouse", "keyboard", "touch"):
            context = browser.new_context(
                viewport={"width": 1920, "height": 2400},
                has_touch=mode == "touch",
                is_mobile=mode == "touch",
            )
            page = context.new_page()
            page.set_default_timeout(3000)
            page.set_content(page_html, wait_until="load")
            page.evaluate(
                "document.fonts.ready.then(() => new Promise(resolve => "
                "requestAnimationFrame(() => requestAnimationFrame(resolve))))"
            )
            page.locator('[data-flow-view="diagram"]').click()
            if page.locator(".flow-reset-filters").count() == 1:
                page.locator(".flow-reset-filters").click()
            frame = page.locator('[data-diagram-frame="layout:LAYOUT-ENGINE"]')
            header = frame.locator(".target-frame-header-hit")
            card = page.locator('.flow-nodes .node[data-label="domains"]')
            edge = page.locator('.flow-edges .edge .hit[data-key="runtime>domains"]')
            labels_before = set(
                page.locator(".flow-nodes .node[data-label]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.label)"
                )
            )
            assert frame.count() == header.count() == card.count() == edge.count() == 1
            assert labels_before == expected_inventory
            header_box = header.bounding_box()
            card_box = card.bounding_box()
            assert header_box and card_box
            flow_data_before = page.locator("#flow-data").text_content()
            start_x = card_box["x"] + card_box["width"] / 2
            start_y = card_box["y"] + card_box["height"] / 2
            end_x = header_box["x"] + header_box["width"] / 2
            end_y = header_box["y"] + header_box["height"] / 2
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(end_x, end_y, steps=8)
            page.mouse.up()
            page.evaluate(
                "new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )

            edge = page.locator('.flow-edges .edge .hit[data-key="runtime>domains"]')
            card_after = card.bounding_box()
            warning = edge.get_attribute("data-route-warning")
            aria_label = edge.get_attribute("aria-label") or ""
            edge_d = edge.get_attribute("d")
            labels_after = set(
                page.locator(".flow-nodes .node[data-label]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.label)"
                )
            )
            edges_after = set(
                page.locator(".flow-edges .edge .hit[data-key]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.key)"
                )
            )
            flow_data_after = page.locator("#flow-data").text_content()
            case_problems: list[str] = []
            if not card_after or (
                abs(card_after["x"] - card_box["x"]) < 8
                and abs(card_after["y"] - card_box["y"]) < 8
            ):
                case_problems.append("native drag did not move the owner card")
            if not edge.is_visible() or not edge_d:
                case_problems.append("edge disappeared after drag")
            if labels_after != labels_before or not expected_edges.issubset(edges_after):
                case_problems.append("component or edge inventory changed during layout drag")
            if flow_data_after != flow_data_before:
                case_problems.append(
                    "layout interaction changed the embedded architecture evidence"
                )
            if warning != "header-overlap":
                case_problems.append(f"missing renderer route warning marker: {warning!r}")
            if "Renderer layout warning: no clear route around a frame header" not in aria_label:
                case_problems.append("warning is absent from the selected edge's accessible label")
            if "architectural status is unchanged" not in aria_label:
                case_problems.append("warning does not state that architecture status is unchanged")

            # Select the same edge through a distinct real input, then inspect its Details pane.
            if mode == "mouse":
                point = edge.evaluate(
                    "hit => {const line=hit.previousElementSibling;const m=line.getScreenCTM();"
                    "const length=line.getTotalLength();for(let s=1;s<length;s+=2){"
                    "const p=line.getPointAtLength(s),q=new DOMPoint(p.x,p.y).matrixTransform(m);"
                    "if(document.elementFromPoint(q.x,q.y)===hit)return {x:q.x,y:q.y};}"
                    "return null;}"
                )
                if point:
                    page.mouse.click(point["x"], point["y"])
                else:
                    case_problems.append("no unobstructed native mouse point on the edge")
            elif mode == "keyboard":
                edge.focus()
                page.keyboard.press("Enter")
            else:
                point = edge.evaluate(
                    "hit => {const line=hit.previousElementSibling;const m=line.getScreenCTM();"
                    "const length=line.getTotalLength();for(let s=1;s<length;s+=2){"
                    "const p=line.getPointAtLength(s),q=new DOMPoint(p.x,p.y).matrixTransform(m);"
                    "if(document.elementFromPoint(q.x,q.y)===hit)return {x:q.x,y:q.y};}"
                    "return null;}"
                )
                if point:
                    page.touchscreen.tap(point["x"], point["y"])
                else:
                    case_problems.append("no unobstructed native touch point on the edge")
            details_toggle = page.locator("[data-flow-details-toggle]")
            inspector = page.locator(".flow-inspector")
            if details_toggle.count() != 1:
                case_problems.append("Details toggle is missing or ambiguous")
            elif mode == "mouse":
                details_toggle.click()
            elif mode == "keyboard":
                details_toggle.focus()
                page.keyboard.press("Enter")
            else:
                toggle_box = details_toggle.bounding_box()
                if toggle_box:
                    page.touchscreen.tap(
                        toggle_box["x"] + toggle_box["width"] / 2,
                        toggle_box["y"] + toggle_box["height"] / 2,
                    )
                else:
                    case_problems.append("Details toggle has no native touch target")
            if not inspector.is_visible():
                case_problems.append("Details panel did not become visible after native toggle")
            details_visible = inspector.locator(".flow-layout-warning")
            if details_visible.count() != 1 or not details_visible.is_visible():
                case_problems.append(
                    "selected edge Details do not visibly expose the route warning"
                )
            details = inspector.inner_text() if inspector.is_visible() else ""
            heading = (
                inspector.locator("h2").inner_text() if inspector.locator("h2").count() else ""
            )
            if heading != "runtime → domains":
                case_problems.append("selected edge Details do not identify the exact relationship")
            if "Renderer layout warning: no clear route around a frame header" not in details:
                case_problems.append("selected edge Details omit the renderer layout warning")
            if "architectural status is unchanged" not in details:
                case_problems.append(
                    "selected edge Details omit unchanged-architecture-status boundary"
                )
            selected_edge = page.locator('.flow-edges .edge .hit[data-key="runtime>domains"]')
            selected = selected_edge.evaluate(
                "hit => hit.closest('g.edge')?.classList.contains('selected')"
            )
            observed[mode] = {
                "routeWarningBeforeSelection": warning,
                "ariaHasWarningBeforeSelection": "Renderer layout warning" in aria_label,
                "routeWarningAfterSelection": selected_edge.get_attribute("data-route-warning"),
                "ariaLabelAfterSelection": selected_edge.get_attribute("aria-label"),
                "detailsHasWarning": "Renderer layout warning" in details,
                "detailsHasStatusBoundary": "architectural status is unchanged" in details,
                "detailsOpenAfterNativeToggle": details_toggle.get_attribute("aria-expanded")
                == "true",
                "visibleDetailsWarning": details_visible.is_visible()
                if details_visible.count()
                else False,
                "edgeSelected": selected,
                "cardAfter": card_after,
                "header": header_box,
                "inventoryPreserved": labels_after == labels_before
                and expected_edges.issubset(edges_after),
            }
            if case_problems:
                problems[mode] = case_problems
            context.close()
        assert not problems, {"problems": problems, "observed": observed}
    finally:
        browser.close()
        playwright.stop()
