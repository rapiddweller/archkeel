# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the progressive map through the localhost browser entry point."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from explorer_support import browser

from archkeel.cli.core_explorer_http import _ExplorerServer
from archkeel.explorer_queries import populate
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (3440, 1440)])
def test_map_opens_owner_overview_and_animates_one_directed_edge(
    tmp_path: Path, width: int, height: int
) -> None:
    snapshot = tmp_path / "cache" / "sample.sqlite"
    topology = {
        "version": 1,
        "components": [
            {"id": "entry", "name": "Entry", "parent": None, "public": ["app.entry.start"]},
            {"id": "data", "name": "Data", "parent": None},
        ],
        "modules": [
            {"name": f"app.entry.{i}", "component": "entry", "path": f"entry{i}.py"}
            for i in range(40)
        ],
        "edges": [],
        "component_edges": [
            {"id": "entry:import", "source": "entry", "target": "data", "resolution": "resolved"}
        ],
        "explorer": [
            {
                "language": "python",
                "symbols": [
                    {
                        "id": "run",
                        "module": "app.entry.0",
                        "kind": "function",
                        "qualified_name": "app.entry.0.run",
                        "evidence_ids": [],
                    }
                ],
            }
        ],
    }
    publish_snapshot(
        snapshot,
        SnapshotIdentity("revision", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    with _ExplorerServer(snapshot, tmp_path, None, 0) as server, ThreadPoolExecutor() as pool:
        running = pool.submit(server.serve_forever)
        try:
            with browser(tmp_path / "profile", width=width, height=height) as page:
                page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                page.wait("document.querySelector('.map-plane [data-element]') !== null")
                assert page.evaluate("document.getElementById('map-modes').hidden")
                assert page.evaluate(
                    "document.querySelector('.map-plane .map-public-entry').title"
                ) == ("app.entry.start")
                assert (
                    page.evaluate("document.querySelectorAll('.map-plane .uml-card').length") == 2
                )
                assert page.evaluate(
                    "document.querySelector('.map-plane').offsetWidth > "
                    "document.querySelector('.map-plane').offsetHeight"
                )
                assert (
                    page.evaluate("parseInt(document.getElementById('zoom-level').textContent, 10)")
                    >= 78
                )
                assert page.evaluate(
                    """(() => {
                      const path = document.querySelector('.map-edges path[marker-end]');
                      const point = path.getPointAtLength(path.getTotalLength() / 2)
                        .matrixTransform(path.getScreenCTM());
                      const button = document.querySelector('.map-edge-label');
                      const label = button.getBoundingClientRect();
                      return Math.hypot(label.x + label.width/2 - point.x,
                                        label.y + label.height/2 - point.y) < 2;
                    })()"""
                )
                page.evaluate("document.querySelector('.map-edge-label').click()")
                page.wait(
                    "document.querySelector('#details h2')?.textContent === 'Entry imports Data'"
                )
                page.evaluate("document.querySelector('[data-element=entry]').click()")
                page.wait("document.querySelector('#details h2')?.textContent === 'Entry'")
                for mode, dimension in [("down", "Height"), ("right", "Width")]:
                    control = f'document.querySelector("[data-map-layout={mode}]")'
                    page.evaluate(control + ".click()")
                    page.wait(control + ".getAttribute('aria-pressed') === 'true'")
                    plane = "document.querySelector('.map-plane')"
                    other = "Height" if dimension == "Width" else "Width"
                    assert page.evaluate(f"{plane}.offset{dimension} > {plane}.offset{other}")
                    assert page.evaluate("document.querySelector('#details h2').textContent") == (
                        "Entry"
                    )
                    assert (
                        page.evaluate(
                            "document.querySelector('[data-element=entry]').getAttribute('aria-pressed')"
                        )
                        == "true"
                    )
                pulse = "getComputedStyle(document.querySelector('.map-active-edge .map-pulse'))"
                assert page.evaluate(pulse + ".animationName") == "map-direction"
                page.send(
                    "Emulation.setEmulatedMedia",
                    features=[{"name": "prefers-reduced-motion", "value": "reduce"}],
                )
                assert page.evaluate(pulse + ".display") == "none"
                entry = "document.querySelector('#structure-tree [data-tree-node=entry]')"
                direction = ".dispatchEvent(new KeyboardEvent('keydown',{key:%r,bubbles:true}))"
                page.evaluate(entry + direction % "ArrowRight")
                groups = "document.querySelectorAll('#structure-tree .type-file_group').length"
                page.wait(groups + " === 2")
                page.evaluate(
                    "document.querySelector('#structure-tree .type-file_group')"
                    ".closest('.tree-row').querySelector('.tree-disclosure').click()"
                )
                modules = "document.querySelectorAll('#structure-tree .type-module').length"
                page.wait(modules + " === 36")
                module = 'document.querySelector(`#structure-tree [data-tree-node="app.entry.0"]`)'
                assert page.evaluate(module + ".title") == "entry0.py"
                hint = page.evaluate(module + ".getAttribute('aria-describedby')")
                assert page.evaluate(f"document.getElementById({hint!r}).textContent") == (
                    "Module · Source entry0.py"
                )
                page.evaluate(module + ".closest('li').querySelector('.tree-disclosure').click()")
                page.wait("document.querySelector('#structure-tree .type-function') !== null")
                assert page.evaluate(
                    "document.querySelector('#structure-tree .type-function').closest('.tree-row')"
                    ".querySelector('.tree-leaf-dot') !== null"
                )
                page.evaluate(module + ".click()")
                page.wait("document.querySelector('#details h2')?.textContent === 'app.entry.0'")
                assert page.evaluate(module + ".getAttribute('aria-pressed')") == "true"
                context = "document.querySelector('.map-plane [data-element=entry].map-context')"
                assert page.evaluate(context + " !== null")
                assert (
                    page.evaluate("document.getElementById('breadcrumbs').textContent.trim()")
                    == "System"
                )
                page.evaluate(entry + direction % "ArrowLeft")
                assert page.evaluate(module + ".getClientRects().length") == 0
        finally:
            server.shutdown()
            running.result(timeout=5)


def test_group_connections_open_all_relations_and_evidence(tmp_path: Path) -> None:
    snapshot = tmp_path / "cache" / "relations.sqlite"
    topology = {
        "version": 1,
        "components": [
            {"id": "a", "name": "A", "parent": None},
            {"id": "b", "name": "B", "parent": None},
        ],
        "modules": [
            {"name": "a.one", "path": "a/one.py", "component": "a"},
            {"name": "a.two", "path": "a/two.py", "component": "a"},
            {"name": "b.one", "path": "b/one.py", "component": "b"},
        ],
        "edges": [
            {
                "id": "first",
                "source": "a.one",
                "target": "b.one",
                "resolution": "resolved",
                "count": 1,
            },
            {
                "id": "second",
                "source": "a.two",
                "target": "b.one",
                "resolution": "resolved",
                "count": 1,
            },
        ],
    }
    publish_snapshot(
        snapshot,
        SnapshotIdentity("rev", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    with _ExplorerServer(snapshot, tmp_path, None, 0) as server, ThreadPoolExecutor() as pool:
        running = pool.submit(server.serve_forever)
        try:
            with browser(tmp_path / "profile") as page:
                page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                page.wait("document.querySelector('[data-element=a]') !== null")
                page.evaluate("document.querySelector('[data-element=a]').click()")
                page.wait(
                    "document.querySelector('#details')?.textContent"
                    ".includes('Outgoing Import × 2')"
                )
                assert page.evaluate("document.querySelector('.map-edge-label').textContent") == (
                    "A imports B × 2"
                )
                page.evaluate(
                    "[...document.querySelectorAll('#details button')]"
                    ".find(b => b.textContent.includes('Outgoing Import × 2')).click()"
                )
                page.wait("document.querySelectorAll('#details .detail-btn').length === 2")
                assert page.evaluate("document.querySelector('#details .detail-btn wbr') !== null")
                assert "a.one" in page.evaluate("document.getElementById('details').textContent")
                assert "a.two" in page.evaluate("document.getElementById('details').textContent")
                page.evaluate("document.querySelector('#details .detail-btn').click()")
                page.wait(
                    "document.getElementById('details').textContent.includes('Dependency evidence')"
                )
                assert "no indexed source location" in page.evaluate(
                    "document.getElementById('details').textContent"
                )
        finally:
            server.shutdown()
            running.result(timeout=5)


def test_expanded_group_highlights_relations(tmp_path: Path) -> None:
    snapshot = tmp_path / "cache" / "groups.sqlite"
    topology = {
        "version": 1,
        "observed_only": True,
        "components": [{"id": "a", "name": "A", "parent": None}],
        "modules": [
            {"name": "a.first.one", "path": "a/first/one.py", "component": "a"},
            {"name": "a.first.two", "path": "a/first/two.py", "component": "a"},
            {"name": "a.second.one", "path": "a/second/one.py", "component": "a"},
            *[
                {"name": f"a.second.extra{i}", "path": f"a/second/extra{i}.py", "component": "a"}
                for i in range(12)
            ],
        ],
        "edges": [
            {
                "id": "one",
                "source": "a.first.one",
                "target": "a.second.one",
                "resolution": "resolved",
            },
            {
                "id": "two",
                "source": "a.first.two",
                "target": "a.second.one",
                "resolution": "resolved",
            },
        ],
    }
    publish_snapshot(
        snapshot,
        SnapshotIdentity("rev", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    with _ExplorerServer(snapshot, tmp_path, None, 0) as server, ThreadPoolExecutor() as pool:
        running = pool.submit(server.serve_forever)
        try:
            with browser(tmp_path / "profile") as page:
                page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                page.wait("document.querySelector('[data-element=a]') !== null")
                assert (
                    page.evaluate(
                        "document.querySelector('[data-element=a] .uml-stereotype').textContent"
                    )
                    == "Package group"
                )
                assert "Package group" in page.evaluate(
                    "document.querySelector('#structure-tree').textContent"
                )
                box = page.evaluate(
                    "(() => { const r = document.querySelector('[data-element=a]')"
                    ".getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2}; })()"
                )
                for count in (1, 2):
                    for kind in ("mousePressed", "mouseReleased"):
                        page.send(
                            "Input.dispatchMouseEvent",
                            type=kind,
                            button="left",
                            clickCount=count,
                            **box,
                        )
                page.wait("document.querySelector('.map-group-title') !== null")
                assert "Package group · includes descendants" in page.evaluate(
                    "document.getElementById('details').textContent"
                )
                page.evaluate(
                    "[...document.querySelectorAll('.map-group-title')]"
                    ".find(b => b.textContent.includes('first')).click()"
                )
                page.wait(
                    "document.querySelector('#details')?.textContent"
                    ".includes('Outgoing Import × 2')"
                )
                assert (
                    page.evaluate("document.querySelectorAll('.map-edges [data-map-edge]').length")
                    > 0
                )
                page.evaluate("document.querySelector('[data-element=\"a.first.one\"]').click()")
                page.wait("document.querySelector('#details h2')?.textContent === 'a.first.one'")
                for mode in ("right", "down", "groups"):
                    control = f'document.querySelector("[data-map-layout={mode}]")'
                    page.evaluate(control + ".click()")
                    page.wait(
                        control + ".getAttribute('aria-pressed') === 'true' || "
                        "document.getElementById('notice').textContent.includes('Exception')"
                    )
                    assert page.evaluate(control + ".getAttribute('aria-pressed')") == "true"
                    assert (
                        page.evaluate(
                            "document.querySelector('[data-element=\"a.first.one\"]')"
                            ".getAttribute('aria-pressed')"
                        )
                        == "true"
                    )
                    assert (
                        page.evaluate(
                            "document.querySelectorAll('.map-edges [data-map-edge]').length"
                        )
                        > 0
                    )
                    assert page.evaluate("""(() => {
                      const source = document.querySelector('[data-element="a.first.one"]');
                      const target = [...document.querySelectorAll('.map-plane .uml-card')]
                        .find(node => node.textContent.includes('second'));
                      const path = document.querySelector(
                        '.map-edges [data-map-edge] path[marker-end]');
                      if (!source || !target || !path) return false;
                      const point = at => path.getPointAtLength(at)
                        .matrixTransform(path.getScreenCTM());
                      const near = (p, rect) => Math.hypot(
                        Math.max(rect.left - p.x, 0, p.x - rect.right),
                        Math.max(rect.top - p.y, 0, p.y - rect.bottom)) < 5;
                      return near(point(0), source.getBoundingClientRect()) &&
                        near(point(path.getTotalLength()), target.getBoundingClientRect());
                    })()""")

        finally:
            server.shutdown()
            running.result(timeout=5)
