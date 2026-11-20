# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check that Studio modes keep their canvas inside the window when resized."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from explorer_support import browser

from archkeel.cli import core_explorer_http
from archkeel.explorer_queries import populate
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


@pytest.mark.parametrize(("components", "steps"), [(1, 1), (16, 12)])
def test_studio_canvas_fills_the_workspace_in_both_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, components: int, steps: int
) -> None:
    story = {
        "id": "example",
        "title": "Resize story",
        "steps": [
            {"node": f"package{i}.start", "lane": f"Package {i}", "status": "proven"}
            for i in range(steps)
        ],
        "chapters": [],
        "coverage": {},
    }
    monkeypatch.setattr(core_explorer_http, "list_stories", lambda *args: [story])
    monkeypatch.setattr(core_explorer_http, "read_story", lambda *args: story)
    topology = {
        "version": 1,
        "components": [
            {"id": f"group{i}", "name": f"Group {i}", "parent": None} for i in range(components)
        ],
        "modules": [
            {"name": f"package{i}.start", "component": f"group{i}", "path": f"package{i}.py"}
            for i in range(components)
        ],
        "edges": [],
        "component_edges": [],
    }
    snapshot = tmp_path / "snapshot.sqlite"
    publish_snapshot(
        snapshot,
        SnapshotIdentity("revision", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    with core_explorer_http._ExplorerServer(snapshot, tmp_path, None, 0) as server:
        with ThreadPoolExecutor() as pool:
            running = pool.submit(server.serve_forever)
            try:
                with browser(tmp_path / "profile", width=1440, height=900) as page:
                    page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                    page.wait(
                        f"document.querySelectorAll('.map-plane .uml-card').length === {components}"
                    )
                    for pane, toggle in (
                        ("structure-pane", "structure-toggle"),
                        ("details", "inspector-toggle"),
                    ):
                        page.evaluate(
                            f"if (document.getElementById('{pane}').hidden) "
                            f"document.getElementById('{toggle}').click()"
                        )
                        assert not page.evaluate(f"document.getElementById('{pane}').hidden")
                    measurements = []
                    for size in [(1440, 900), (3440, 1440), (390, 844)]:
                        page.send(
                            "Emulation.setDeviceMetricsOverride",
                            width=size[0],
                            height=size[1],
                            deviceScaleFactor=1,
                            mobile=False,
                        )
                        page.wait(f"innerWidth === {size[0]} && innerHeight === {size[1]}")
                        measurements.append(("map", size, page.evaluate(_MEASURE)))
                    page.evaluate("document.getElementById('story').click()")
                    page.wait("document.querySelector('.story-library button') !== null")
                    measurements.append(("library", (390, 844), page.evaluate(_MEASURE)))
                    page.evaluate("document.querySelector('.story-library button').click()")
                    page.wait(f"document.querySelectorAll('.story-node').length === {steps}")
                    for size in [(390, 844), (1440, 900), (3440, 1440)]:
                        page.send(
                            "Emulation.setDeviceMetricsOverride",
                            width=size[0],
                            height=size[1],
                            deviceScaleFactor=1,
                            mobile=False,
                        )
                        page.wait(f"innerWidth === {size[0]} && innerHeight === {size[1]}")
                        measurements.append(("story", size, page.evaluate(_MEASURE)))
                    page.evaluate("document.getElementById('map').click()")
                    page.wait(
                        f"document.querySelectorAll('.map-plane .uml-card').length === {components}"
                    )
                    measurements.append(("returned", (3440, 1440), page.evaluate(_MEASURE)))
                    for mode, (width, height), geometry in measurements:
                        assert geometry["workspace"] == [0, width, height], (mode, geometry)
                        assert geometry["pageWidth"] == width, (mode, geometry)
                        assert geometry["viewport"] == geometry["workArea"], (mode, geometry)
                        left, top, right, bottom = geometry["viewport"]
                        body_left, body_top, body_right, body_bottom = geometry["body"]
                        assert [top, bottom] == [body_top, body_bottom], (mode, geometry)
                        left_pane = geometry["structure"]
                        right_pane = geometry["details"]
                        if left_pane and width > 860:
                            body_left = left_pane[2]
                        if mode == "story" and right_pane and width > 740:
                            assert right_pane[2] - right_pane[0] <= 360, geometry
                            body_right = right_pane[0]
                        assert [left, right] == [body_left, body_right], (mode, geometry)
                        assert all(
                            actual >= available - 1
                            for actual, available in zip(
                                geometry["canvas"], geometry["viewportSize"], strict=True
                            )
                        ), (mode, geometry)
                        if mode == "story":
                            assert geometry["controls"][1] == bottom, geometry
                        if mode == "map":
                            assert 0 <= geometry["arrowKey"][0] < geometry["arrowKey"][2] <= width
            finally:
                server.shutdown()
                running.result()


_MEASURE = """(() => {
  const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
  const bounds = (selector) => {
    const {left, top, right, bottom} = rect(selector);
    return [left, top, right, bottom];
  };
  const visible = (selector) => document.querySelector(selector).hidden ? null : bounds(selector);
  const viewport = document.getElementById('viewport');
  const legend = document.createRange();
  legend.selectNodeContents(document.querySelector('.arrow-key'));
  const {left, right} = legend.getBoundingClientRect();
  return {
    pageWidth: document.documentElement.scrollWidth,
    body: bounds('.body-grid'),
    workspace: [rect('.workspace').left, rect('.workspace').right, rect('.workspace').bottom],
    workArea: bounds('.work-area'),
    viewport: bounds('#viewport'),
    viewportSize: [viewport.clientWidth, viewport.clientHeight],
    canvas: [rect('#canvas').width, rect('#canvas').height],
    details: visible('#details'),
    structure: visible('#structure-pane'),
    controls: visible('#story-controls'),
    arrowKey: [left, 0, right],
  };
})()"""
