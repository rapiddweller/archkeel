# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise checked story playback with the Studio browser assets."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from explorer_support import browser

from archkeel.cli import core_explorer_http


def test_story_lanes_evidence_play_and_reduced_motion(tmp_path: Path, monkeypatch) -> None:
    steps = [
        {
            "node": "app.first",
            "lane": "app",
            "function": "first",
            "note": "Start the flow.",
            "status": "proven",
            "external": [
                {
                    "system": "relational_database",
                    "label": "SQLite",
                    "status": "observed_call",
                    "binding": "unknown",
                    "reason": "Static call only.",
                    "evidence": [{"path": "app.py", "line": 1}],
                }
            ],
        },
        {
            "node": "store.save",
            "lane": "store",
            "function": "save",
            "note": "Save the result.",
            "status": "unknown",
            "external": [{"system": "redis", "status": "claim", "evidence": []}],
        },
    ]
    story = {"id": "example", "title": "Example", "steps": steps, "chapters": [], "coverage": {}}
    monkeypatch.setattr(
        core_explorer_http, "list_stories", lambda *args: [{"id": "example", "title": "Example"}]
    )
    monkeypatch.setattr(core_explorer_http, "read_story", lambda *args: story)
    monkeypatch.setattr(
        core_explorer_http,
        "query",
        lambda *args: {
            "coverage": {},
            "items": [],
            "groups": [],
            "edges": [],
            "total": 0,
            "next_cursor": None,
            "edge_total": 0,
            "edges_truncated": False,
        },
    )
    with core_explorer_http._ExplorerServer(tmp_path / "db", tmp_path, None, 0) as server:
        with ThreadPoolExecutor() as pool:
            running = pool.submit(server.serve_forever)
            try:
                with browser(tmp_path / "profile", width=390, height=844) as page:
                    page.send(
                        "Emulation.setEmulatedMedia",
                        features=[{"name": "prefers-reduced-motion", "value": "reduce"}],
                    )
                    page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                    page.wait(
                        "document.getElementById('story') && document.readyState === 'complete'"
                    )
                    page.evaluate("document.getElementById('story').click()")
                    page.wait("document.querySelector('.story-library button') !== null")
                    page.evaluate("document.querySelector('.story-library button').click()")
                    page.wait("document.querySelectorAll('.story-node').length === 2")
                    assert page.evaluate(
                        "[...document.querySelectorAll('.story-lane-headings strong')]"
                        ".map(x=>x.textContent)"
                    ) == ["app", "store"]
                    assert page.evaluate(
                        "[...document.querySelectorAll('.story-node strong')].map(x=>x.textContent)"
                    ) == ["first", "save"]
                    assert page.evaluate("document.querySelectorAll('.story-system').length") == 1
                    assert "SQLite · binding unknown" in page.evaluate(
                        "document.querySelector('.story-system').textContent"
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth === "
                        "document.documentElement.clientWidth"
                    )
                    page.evaluate("document.getElementById('story-play').click()")
                    assert (
                        page.evaluate("document.getElementById('story-play').textContent")
                        == "Pause"
                    )
                    page.evaluate("document.getElementById('story-play').click()")
                    assert (
                        page.evaluate("document.getElementById('story-play').textContent")
                        == "Play story"
                    )
                    page.evaluate("document.getElementById('story-next').click()")
                    page.wait(
                        "document.getElementById('story-position').textContent.includes('2 / 2')"
                    )
                    assert page.evaluate("document.querySelectorAll('animateMotion').length") == 0
                    assert "redis · Claim" in page.evaluate(
                        "document.getElementById('details').innerText"
                    )
                    page.send(
                        "Emulation.setEmulatedMedia",
                        features=[{"name": "prefers-reduced-motion", "value": "no-preference"}],
                    )
                    page.evaluate("document.getElementById('story-play').click()")
                    page.wait(
                        "document.getElementById('story-position').textContent.includes('2 / 2')"
                        " && "
                        "document.getElementById('story-play').textContent === 'Play story'"
                    )
                    assert page.evaluate("document.querySelectorAll('animateMotion').length") == 1
            finally:
                server.shutdown()
                running.result(timeout=5)
