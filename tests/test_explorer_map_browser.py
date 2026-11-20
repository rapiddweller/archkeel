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
                page.evaluate("document.getElementById('map-modules').click()")
                page.wait("document.getElementById('notice').textContent.includes('40 indexed')")
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
                for mode, dimension in [("down", "Height"), ("right", "Width")]:
                    control = f'document.querySelector("[data-map-layout={mode}]")'
                    page.evaluate(control + ".click()")
                    page.wait(control + ".getAttribute('aria-pressed') === 'true'")
                    plane = "document.querySelector('.map-plane')"
                    other = "Height" if dimension == "Width" else "Width"
                    assert page.evaluate(f"{plane}.offset{dimension} > {plane}.offset{other}")
                    assert page.evaluate("document.querySelector('#details h2').textContent") == (
                        "Entry imports Data"
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
                modules = "document.querySelectorAll('#structure-tree .type-module').length"
                page.wait(modules + " === 24")
                more = "document.querySelector('#structure-tree .tree-message button')"
                page.evaluate(more + ".click()")
                page.wait(modules + " === 40")
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
