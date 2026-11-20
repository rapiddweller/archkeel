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
            "lane": "archkeel.cli.core_output",
            "function": "first",
            "defined_at": {"path": "src/archkeel/cli/core_delivery.py", "line": 116},
            "note": "Start the flow.",
            "status": "proven",
            "external": [
                {
                    "system": "relational_database",
                    "label": "SQLite",
                    "status": "observed_call",
                    "binding": "unknown",
                    "direction": "writes",
                    "direction_evidence": [{"path": "app.py", "line": 1}],
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
            "transition": "process_request",
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
                    page.wait("document.querySelector('#story:enabled') !== null")
                    page.evaluate("document.getElementById('story').click()")
                    page.wait("document.querySelector('.story-library button') !== null")
                    page.evaluate("document.querySelector('.story-library button').click()")
                    page.wait("document.querySelectorAll('.story-node').length === 2")
                    assert page.evaluate(
                        "[...document.querySelectorAll('.story-lane-headings strong')]"
                        ".map(x=>x.textContent)"
                    ) == ["archkeel.cli.core_output", "store"]
                    assert page.evaluate(
                        """(() => {
                          const chunks = (node) => [...node.childNodes]
                            .filter(part => part.nodeType === Node.TEXT_NODE);
                          const lane = document.querySelector('.story-lane-headings strong.active');
                          const file = document.querySelector('.story-step-title');
                          const laneParts = chunks(lane);
                          const fileParts = chunks(file);
                          const fits = (part) => {
                            const range = new Range();
                            range.selectNodeContents(part);
                            return range.getClientRects().length === 1;
                          };
                          return laneParts.map(part => part.data).join('|') ===
                              'archkeel.|cli.|core_output' &&
                            fileParts.map(part => part.data).join('|') ===
                              'core_delivery.|py:116' &&
                            [laneParts.at(-1), fileParts.at(-1)].every(fits);
                        })()"""
                    )
                    assert page.evaluate(
                        "[...document.querySelectorAll('.story-node strong')].map(x=>x.textContent)"
                    ) == ["first", "save"]
                    assert page.evaluate("document.querySelectorAll('.story-system').length") == 1
                    assert (
                        page.evaluate(
                            "getComputedStyle(document.querySelectorAll('.story-node')[1]).visibility"
                        )
                        == "hidden"
                    )
                    assert (
                        page.evaluate("document.querySelectorAll('.story-routes path').length") == 0
                    )
                    assert "Writes · static" in page.evaluate(
                        "document.querySelector('.story-external-rail').innerText"
                    )
                    assert (
                        page.evaluate(
                            "document.querySelectorAll('.story-external-routes path').length"
                        )
                        == 1
                    )
                    assert "Writes · static" in page.evaluate(
                        "document.querySelector('.story-external-label').textContent"
                    )
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
                    assert page.evaluate(
                        "document.querySelector('.story-node[aria-current]')"
                        ".getBoundingClientRect().bottom <= document.getElementById('details')"
                        ".getBoundingClientRect().top + 1"
                    )
                    assert page.evaluate("document.querySelectorAll('animateMotion').length") == 0
                    assert (
                        page.evaluate("document.querySelectorAll('.story-routes path').length") == 1
                    )
                    assert (
                        page.evaluate(
                            "getComputedStyle(document.querySelectorAll('.story-node')[1]).visibility"
                        )
                        == "visible"
                    )
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


def test_failed_switch_keeps_previous_view_and_retry_succeeds(tmp_path: Path, monkeypatch) -> None:
    attempts = []

    def stories(*args):
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("story storage unavailable")
        return [{"id": "example", "title": "Example"}]

    def query(path, root, operation, args):
        return {
            "coverage": {},
            "items": [{"id": "part", "name": "Part", "kind": "component", "parent": "system"}],
            "groups": [],
            "edges": [],
            "total": 1,
            "next_cursor": None,
            "edge_total": 0,
            "edges_truncated": False,
        }

    monkeypatch.setattr(core_explorer_http, "list_stories", stories)
    monkeypatch.setattr(core_explorer_http, "query", query)
    with core_explorer_http._ExplorerServer(tmp_path / "db", tmp_path, None, 0) as server:
        with ThreadPoolExecutor() as pool:
            running = pool.submit(server.serve_forever)
            try:
                with browser(tmp_path / "profile") as page:
                    page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                    page.wait("document.querySelector('.map-plane') !== null")
                    page.evaluate("document.getElementById('story').click()")
                    page.wait("document.querySelector('#notice button') !== null")
                    assert "story storage unavailable" in page.evaluate(
                        "document.getElementById('notice').innerText"
                    )
                    assert page.evaluate("document.querySelector('.map-plane') !== null")
                    assert (
                        page.evaluate("document.getElementById('map').getAttribute('aria-pressed')")
                        == "true"
                    )
                    page.evaluate("document.querySelector('#notice button').click()")
                    page.wait("document.querySelector('.story-library button') !== null")
                    assert (
                        page.evaluate(
                            "document.getElementById('story').getAttribute('aria-pressed')"
                        )
                        == "true"
                    )
                    assert page.evaluate("document.getElementById('notice').innerText") == ""
            finally:
                server.shutdown()
                running.result(timeout=5)


def test_late_story_response_does_not_replace_newer_architecture(
    tmp_path: Path, monkeypatch
) -> None:
    from threading import Event

    entered, release, finished = Event(), Event(), Event()

    def stories(*args):
        entered.set()
        release.wait(5)
        finished.set()
        return [{"id": "example", "title": "Example"}]

    monkeypatch.setattr(core_explorer_http, "list_stories", stories)
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
                with browser(tmp_path / "profile") as page:
                    page.send("Page.navigate", url=f"http://127.0.0.1:{server.server_port}/")
                    page.wait(
                        "document.getElementById('map').getAttribute('aria-pressed') === 'true'"
                    )
                    page.evaluate("document.getElementById('story').click()")
                    assert entered.wait(3)
                    page.evaluate("document.getElementById('map').click()")
                    release.set()
                    assert finished.wait(3)
                    page.evaluate("new Promise(resolve => setTimeout(resolve, 100))")
                    assert (
                        page.evaluate("document.getElementById('map').getAttribute('aria-pressed')")
                        == "true"
                    )
                    assert page.evaluate("document.querySelector('.story-library') === null")
            finally:
                release.set()
                server.shutdown()
                running.result(timeout=5)
