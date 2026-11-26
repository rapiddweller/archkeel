# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check that Studio modes keep their canvas inside the window when resized."""

import json
import os
import re
import select
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from core_support import ROOT
from corpus_support import commit_tree
from explorer_support import browser

from archkeel.cli import core_explorer_http
from archkeel.explorer_queries import populate
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


def test_contract_free_first_view_on_pinned_project(tmp_path: Path, release_core: Path) -> None:
    assert release_core.is_file()
    fixture = ROOT / "fixtures/K-python-realworld"
    assert json.loads((fixture / "SNAPSHOT.json").read_text())["commit"] == (
        "029eb7781c60d5f563ee8990a0cbfb79b244538c"
    )
    project = tmp_path / "project"
    shutil.copytree(
        fixture,
        project,
        ignore=shutil.ignore_patterns("archkeel.toml", "architecture-contract.json"),
    )
    commit_tree(project)
    env = {**os.environ, "XDG_CACHE_HOME": str(tmp_path / "cache")}
    command = [
        sys.executable,
        "-m",
        "archkeel.cli",
        "studio",
        "--root",
        str(project),
        "--no-open",
        "--json",
    ]
    with browser(tmp_path / "chrome", width=800, height=600) as page:
        process = subprocess.Popen(
            command, cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            assert process.stdout is not None
            assert select.select([process.stdout], [], [], 120)[0], "Studio did not start"
            result = json.loads(process.stdout.readline())
            assert "url" in result, result
            page.send("Page.navigate", url=result["url"])
            page.wait("document.querySelectorAll('.map-plane .uml-card').length === 7")
            assert page.evaluate(
                "[innerWidth, innerHeight, document.documentElement.scrollWidth]"
            ) == [800, 600, 800]
            assert page.evaluate(
                "[...document.querySelectorAll('.map-plane .uml-name')]"
                ".every(n => n.textContent.trim() && n.getBoundingClientRect().width > 0)"
            )
            assert not re.search(r"\b(?:PASS|FAIL)\b", page.evaluate("document.body.innerText"))
            page.press("Tab")
            assert page.evaluate("document.activeElement.id") == "map"
            page.evaluate("document.getElementById('search').focus()")
            page.send("Input.insertText", text="app.main")
            page.press("Tab")
            assert page.evaluate("document.activeElement.textContent") == "Search"
            page.send(
                "Input.dispatchKeyEvent",
                type="rawKeyDown",
                key="Enter",
                code="Enter",
                windowsVirtualKeyCode=13,
            )
            page.send(
                "Input.dispatchKeyEvent",
                type="char",
                key="Enter",
                code="Enter",
                text="\r",
                windowsVirtualKeyCode=13,
            )
            page.send(
                "Input.dispatchKeyEvent",
                type="keyUp",
                key="Enter",
                code="Enter",
                windowsVirtualKeyCode=13,
            )
            page.wait("document.querySelector('[data-element=\"module:app.main\"]') !== null")
            page.evaluate("document.querySelector('[data-element=\"module:app.main\"]').click()")
            page.wait("!document.getElementById('details').hidden")
            point = page.evaluate("""(() => {
              const button = [...document.querySelectorAll('#details button')]
                .find(item => item.textContent === 'Open source');
              button.scrollIntoView();
              const r = button.getBoundingClientRect();
              return [r.x + r.width / 2, r.y + r.height / 2];
            })()""")
            for action in ("mousePressed", "mouseReleased"):
                page.send(
                    "Input.dispatchMouseEvent",
                    type=action,
                    x=point[0],
                    y=point[1],
                    button="left",
                    clickCount=1,
                )
            page.wait(
                "document.querySelector('.source pre')?.textContent.includes('get_application')"
            )
            assert (
                page.evaluate("document.querySelector('.source h2').textContent") == "app/main.py"
            )
            assert not (project / "archkeel.toml").exists()
            assert not (project / "architecture-contract.json").exists()
            assert (
                subprocess.run(
                    ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
                ).stdout
                == ""
            )
        finally:
            process.terminate()
            process.wait(timeout=10)


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
    real_query = core_explorer_http.query

    def counted_query(path, root, operation, args):
        response = real_query(path, root, operation, args)
        if operation == "map" and response["items"]:
            response.update(module_overview=True, module_total=42)
            response["items"][0].update(recorded_calls=3_456_789, unresolved_calls=1_234_567)
        return response

    monkeypatch.setattr(core_explorer_http, "query", counted_query)
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
                    assert page.evaluate(_BADGE_FITS)
                    assert page.evaluate("document.getElementById('notice').textContent")
                    page.evaluate("document.querySelector('.map-plane .uml-card').click()")
                    page.wait("!document.getElementById('details').hidden")
                    assert page.evaluate(_MEASURE)["workspace"] == [0, 1440, 900]
                    page.evaluate("document.getElementById('inspector-toggle').click()")
                    page.send(
                        "Emulation.setDeviceMetricsOverride",
                        width=390,
                        height=844,
                        deviceScaleFactor=1,
                        mobile=False,
                    )
                    page.wait("document.getElementById('structure-pane').hidden")
                    page.send("Page.reload")
                    page.wait(
                        f"document.querySelectorAll('.map-plane .uml-card').length === {components}"
                    )
                    assert page.evaluate(_MOBILE_DEFAULTS)
                    page.send(
                        "Emulation.setDeviceMetricsOverride",
                        width=1440,
                        height=900,
                        deviceScaleFactor=1,
                        mobile=False,
                    )
                    page.wait("!document.getElementById('structure-pane').hidden")
                    page.evaluate("document.getElementById('structure-toggle').click()")
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
                    assert page.evaluate("!document.getElementById('structure-pane').hidden")
                    assert page.evaluate("!document.getElementById('details').hidden")
                    page.evaluate("document.getElementById('inspector-toggle').click()")
                    page.evaluate("document.getElementById('story').click()")
                    page.wait("document.querySelector('.story-library button') !== null")
                    page.evaluate("document.getElementById('notice').textContent = 'Status'")
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
                    assert page.evaluate("document.getElementById('details').hidden")
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


_MOBILE_DEFAULTS = """(() => {
  if (!document.getElementById('structure-pane').hidden ||
      !document.getElementById('details').hidden) return false;
  return ['structure-toggle', 'inspector-toggle'].every((id) => {
    const rect = document.getElementById(id).getBoundingClientRect();
    return rect.width > 0 && rect.left >= 0 && rect.right <= innerWidth &&
      document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)?.id === id;
  });
})()"""

_BADGE_FITS = """(() => {
  const badge = document.querySelector('.uml-head .map-call-count');
  const text = new Range();
  text.selectNodeContents(badge);
  const card = badge.closest('.uml-card').getBoundingClientRect();
  const {right, bottom} = text.getBoundingClientRect();
  return right <= card.right && bottom <= card.bottom &&
    text.getBoundingClientRect().height > parseFloat(getComputedStyle(badge).lineHeight);
})()"""
