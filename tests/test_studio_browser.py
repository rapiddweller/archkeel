# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the Studio shell loads, navigates by keyboard and asks only its own server.

Run these tests with `-m browser`; they need the `playwright` package and Chromium.
"""

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator
from test_explore import _repository
from test_studio import _SCHEMA, _start, _stop, login, request, running

from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.studio.api import API_VERSION
from archkeel.studio.server import Studio

_LEGEND = ("Observed = code evidence", "Claim = agent hypothesis", "Target = architect decision")
# Data and blob URLs are page content, not requests to a host.
_LOCAL_SCHEMES = {"data", "blob", "about"}


_ENVIRONMENT = {name: os.environ.get(name) for name in ("XDG_CACHE_HOME", "HOME")}
_VIEW_CHECK_SCHEMA = json.loads(
    (Path(__file__).parents[1] / "schema/view-check.schema.json").read_bytes()
)


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Studio]:
    tmp_path = tmp_path_factory.mktemp("studio")
    # The cache folder goes to the server only: Playwright on Linux reads XDG_CACHE_HOME.
    with running(_repository(tmp_path / "shop"), tmp_path / "cache", explored=True) as server:
        yield server


def _camera(page) -> str:
    """The transform of the pan and zoom surface; pan and zoom change it, Fit sets it."""
    return page.locator(".stage").evaluate("(element) => element.style.transform")


def _pan_and_fit(page) -> None:
    """A drag of the empty surface pans, the zoom buttons zoom and Fit goes back to the fit."""
    page.get_by_role("button", name="Fit").click()
    fitted = _camera(page)
    frame = page.locator(".viewport").bounding_box()
    # The corner of the surface holds no card, plate or line.
    start = (frame["x"] + frame["width"] - 40, frame["y"] + 60)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(start[0] - 120, start[1] + 40, steps=5)
    page.mouse.up()
    panned = _camera(page)
    assert panned != fitted
    page.get_by_role("button", name="Zoom in").click()
    assert _camera(page) != panned
    page.get_by_role("button", name="Fit").click()
    assert _camera(page) == fitted


def _check_the_map(page, width: int) -> None:
    page.get_by_role("heading", name="Map", exact=True).wait_for()
    # No contract: the top-level packages of the explore layout, and the root module apart.
    cards = page.locator(".map-card")
    cards.first.wait_for()
    assert cards.count() == 4
    for name in ("app", "cli", "store", "(unowned)"):
        assert cards.filter(has_text=name).count() == 1, name
    # Status is a glyph and a word, never a colour alone.
    count = page.get_by_role("button", name="1 call from app to store: 1 proven")
    assert count.inner_text().strip() == "1 ✓ proven"
    assert page.get_by_text("Base groups: observed package layout", exact=True).is_visible()
    # The legend of the marks is in the side panel; a narrow screen opens it on demand.
    for mark in (
        "✓ proven = resolved call",
        "✎ claim = partly resolved call",
        "? unknown = no target found",
    ):
        assert page.get_by_text(mark, exact=True).count() >= 1
    # A line shows the calls behind it in the side panel.
    count.click()
    details = page.get_by_role("complementary", name="Details")
    details.get_by_text("Dependency · app to store").wait_for()
    assert details.get_by_text("place", exact=True).is_visible()
    assert details.get_by_text("✓ proven").first.is_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= width


def _where(page) -> tuple[list[str], str]:
    """The location bar: the links that go up, and the current place."""
    bar = page.get_by_role("navigation", name="Location")
    return bar.locator("a").all_inner_texts(), bar.locator("b").inner_text()


def _no_overflow(page) -> None:
    """No text crosses the border of a card, a stub or a tile."""
    broken = page.evaluate(
        "[...document.querySelectorAll('.lens-card, .map-card, .story-card')]"
        ".filter((card) => card.scrollWidth > card.clientWidth + 1"
        " || card.scrollHeight > card.clientHeight + 1)"
        ".map((card) => card.className + ': ' + card.textContent.slice(0, 40))"
    )
    assert broken == []


def _check_the_levels(page, width: int, height: int) -> None:
    """Map, component, module and function: each click drills one level, Esc goes up."""
    transition = lambda: page.locator("section.canvas").get_attribute("data-transition")  # noqa: E731
    assert _where(page) == ([], "Architecture")
    _no_overflow(page)
    page.locator(".map-card", has_text="app").dblclick()
    page.wait_for_url("**/#/component/*")
    page.get_by_role("heading", name="Component", exact=True).wait_for()
    assert _where(page) == (["Architecture"], "app")
    assert transition() == "in"
    assert page.get_by_text("You are here").count() == 1
    page.get_by_role("button", name="Details").click() if width < 1300 else None
    assert page.get_by_text("You are here").is_visible()
    page.get_by_role("button", name="Details").click() if width < 1300 else None
    # The module card, and the other components as stubs: here only store, which `place` calls.
    page.locator(".level-card", has_text="orders.py").wait_for()
    assert page.locator(".lens-card.stub").all_inner_texts()
    stubs = page.locator(".lens-card.stub")
    assert {stub.split("\n")[0] for stub in stubs.all_inner_texts()} == {"store"}
    _no_overflow(page)
    # A stub opens that component; Esc goes back up to the Map.
    stubs.filter(has_text="store").dblclick()
    page.get_by_role("navigation", name="Location").locator("b", has_text="store").wait_for()
    assert _where(page) == (["Architecture"], "store")
    page.keyboard.press("Escape")
    page.get_by_role("navigation", name="Location").locator("b", has_text="Architecture").wait_for()
    assert _where(page) == ([], "Architecture")
    assert transition() == "out"
    page.locator(".map-card", has_text="app").dblclick()
    page.locator(".level-card", has_text="orders.py").dblclick()
    page.wait_for_url("**/#/module/*")
    page.get_by_role("heading", name="Module", exact=True).wait_for()
    assert _where(page) == (["Architecture", "app"], "orders.py")
    _no_overflow(page)
    assert "Up to app" in page.locator("a.up").text_content()
    page.locator(".level-card", has_text="place").dblclick()
    page.wait_for_url("**/#/explore/*")
    page.get_by_role("heading", name="Explore", exact=True).wait_for()
    assert _where(page) == (["Architecture", "app", "orders.py"], "place")
    # Esc goes one level up; a part of the location bar goes up to its level.
    bar = page.get_by_role("navigation", name="Location")
    page.keyboard.press("Escape")
    bar.locator("b", has_text="orders.py").wait_for()
    page.keyboard.press("Escape")
    bar.locator("b", has_text="app").wait_for()
    page.get_by_role("navigation", name="Location").get_by_role("link", name="Architecture").click()
    page.wait_for_url("**/#/map")
    page.locator(".map-card", has_text="app").dblclick()
    page.locator(".level-card", has_text="orders.py").dblclick()
    page.locator(".level-card", has_text="place").dblclick()
    page.locator(".lens-card.center").wait_for()
    page.get_by_role("navigation", name="Location").get_by_role("link", name="orders.py").click()
    page.wait_for_url("**/#/module/*")
    page.locator(".level-card", has_text="place").dblclick()
    page.locator(".lens-card.center").wait_for()


def _check_the_lens(page, width: int, height: int) -> None:
    center = page.locator(".lens-card.center")
    center.wait_for()
    assert center.locator("b").inner_text() == "place"
    # The callee `save` proves its call with a glyph and a word. A module-level call is no edge.
    callee = page.locator("a.lens-card.proven", has_text="save")
    assert callee.inner_text().replace("\n", " ").startswith("save")
    assert "✓" in callee.inner_text()  # glyph and line, no word
    assert page.locator(".plate").count() == 2
    assert _where(page) == (["Architecture", "app", "orders.py"], "place")
    _no_overflow(page)
    page.get_by_role("heading", name="Explore", exact=True).wait_for()
    tree = page.get_by_role("navigation", name="Structure")
    if width >= 1500:
        # Only the current branch is open.
        assert tree.is_visible()
        assert tree.locator("a.tn.fn[aria-current='location']").inner_text() == "place"
        assert tree.locator("a.tn.fn").count() == 1
    else:
        assert not tree.is_visible()
        # On a narrow screen the tree is a panel above the canvas; close it to reach the controls.
        page.get_by_role("button", name="Structure").click()
        assert tree.is_visible()
        # The tree opens to the current place only.
        assert tree.locator("a.tn.fn[aria-current='location']").inner_text() == "place"
        assert tree.locator("a.tn.fn").count() == 1
        page.get_by_role("button", name="Structure").click()
        assert not tree.is_visible()
    _pan_and_fit(page)
    # Cmd/Ctrl+K searches by function or module and opens the lens at the pick.
    page.keyboard.press("Control+k")
    page.get_by_role("combobox").fill("sav")
    page.get_by_role("option").filter(has_text="repository.py").click()
    page.locator(".lens-card.center", has_text="save").wait_for()
    assert _where(page)[1] == "save"
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.evaluate("document.documentElement.scrollHeight") <= height


def _check_the_embedded_explorer(page, width: int, height: int) -> None:
    """Only the Explorer canvas, dark from the start, filling the main area; selection shows."""
    element = page.locator("iframe[title='Explorer']")
    element.wait_for()
    page.frame_locator("iframe[title='Explorer']").locator(
        "#flow[data-layout-state='ready']"
    ).wait_for()
    page.locator("iframe[title='Explorer'].ready").wait_for()
    inner = element.element_handle().content_frame()
    # No light flash: an Explorer frame stays hidden until it has loaded and taken the tokens.
    unloaded = (
        "(() => { const frame = document.createElement('iframe'); document.body.append(frame);"
        " const visibility = getComputedStyle(frame).visibility; frame.remove();"
        " return visibility; })()"
    )
    assert page.evaluate(unloaded) == "hidden"
    assert inner.get_by_role("banner").count() == 0
    assert inner.evaluate(
        "[...document.querySelectorAll('.report-shell > :not(.flow-section)')]"
        ".every((item) => getComputedStyle(item).display === 'none')"
    )
    assert (
        inner.locator(".ak-brand, .flow-fullscreen, .flow-open-selected, .theme-toggle").count()
        == 4
    )
    assert inner.evaluate(
        "[...document.querySelectorAll('.ak-brand, .flow-fullscreen, .flow-open-selected,"
        " .theme-toggle')].every((item) => !item.checkVisibility())"
    )
    assert inner.get_by_role("button", name="Search").is_visible()
    # The frame is sandboxed (opaque origin): the shell cannot write into its document, so the
    # tokens arrive by postMessage and the page applies them.
    assert inner.evaluate("document.documentElement.style.getPropertyValue('--ak-canvas')") == (
        "#0a1218"
    )
    assert inner.evaluate("getComputedStyle(flow).backgroundColor") == "rgb(10, 18, 24)"
    assert inner.evaluate("document.documentElement.scrollHeight <= innerHeight")
    box = element.bounding_box()
    assert box["y"] + box["height"] >= height - 32, box
    assert box["width"] >= (width - 260) / 2, box
    assert page.evaluate("document.documentElement.scrollHeight") <= height

    card = inner.locator("g.node[data-uml-id]").first
    component = card.get_attribute("data-uml-id")
    card.click()
    panel = page.get_by_role("complementary", name="Selected component")
    panel.get_by_text(component, exact=True).wait_for()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(1440, 900), (800, 600)])
def test_the_shell_navigates_and_stays_on_its_server(
    studio: Studio, width: int, height: int, tmp_path: Path
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    requests: list[str] = []
    errors: list[str] = []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        # Slice 1 is always dark, also when the system prefers light.
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme="light")
        page.set_default_timeout(20000)
        page.on("request", lambda item: requests.append(item.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        # A request that the CSP header blocks shows as a console error.
        page.on("console", lambda item: item.type == "error" and errors.append(item.text))
        try:
            page.goto(studio.url)
            assert urlsplit(page.url).path == "/"
            # The snapshot is done before the page opens: the Map is the first view.
            _check_the_map(page, width)
            page.get_by_role("link", name="Briefing", exact=True).click()
            page.get_by_role("heading", name="Briefing", exact=True).wait_for()
            for text in (*_LEGEND, "No contract · no policy verdict"):
                assert page.get_by_text(text, exact=False).first.is_visible(), text
            background = "getComputedStyle(document.body).backgroundColor"
            assert page.evaluate(background) == "rgb(10, 18, 24)"
            contract = page.get_by_text("Contract: NOT CONFIGURED", exact=True)
            assert contract.bounding_box()["height"] < 24, "the contract state wraps"
            page.get_by_role("link", name="Architecture", exact=True).click()
            _check_the_map(page, width)
            _check_the_levels(page, width, height)
            _check_the_lens(page, width, height)
            page.screenshot(path=tmp_path / f"lens-{width}.png")

            page.get_by_role("link", name="Open the static report").focus()
            page.keyboard.press("Enter")
            assert urlsplit(page.url).fragment == "/report"
            _check_the_embedded_explorer(page, width, height)
            page.screenshot(path=tmp_path / f"report-{width}.png")

            # One nav item for the architecture; Impact and Target are planned, muted, no link.
            nav = page.get_by_role("navigation", name="Workspace")
            assert nav.locator("a").all_inner_texts() == ["Briefing", "Architecture", "Stories"]
            planned = nav.locator(".planned")
            assert [" ".join(text.split()) for text in planned.all_text_contents()] == [
                "Impact Planned",
                "Target / Diff Planned",
            ]
            assert planned.first.get_attribute("title") == "not built yet"
            # The old links keep working: the pages of the planned items and the lens of a function.
            for fragment, heading in (
                ("#/impact", "Change impact"),
                ("#/target", "Target and diff"),
            ):
                page.goto(studio.url + fragment)
                page.get_by_role("heading", name=heading).wait_for()
                assert page.get_by_text("Not built in Studio yet.").is_visible(), fragment
            page.goto(studio.url + "#/explore/0")
            page.locator(".lens-card.center").wait_for()
            assert nav.locator('a[aria-current="page"]').inner_text() == "Architecture"
            page.get_by_role("link", name="Briefing", exact=True).click()
            page.locator('nav a[aria-current="page"]', has_text="Briefing").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()
    assert errors == []
    outside = [
        url
        for url in requests
        if urlsplit(url).scheme not in _LOCAL_SCHEMES
        and urlsplit(url).netloc != f"127.0.0.1:{studio.port}"
    ]
    assert outside == []
    assert any(urlsplit(url).path == "/api/v1/state" for url in requests)
    assert any(urlsplit(url).path == "/api/v1/graph" for url in requests)
    assert any(urlsplit(url).path == "/files/architecture.report.html" for url in requests)


_TOTALS = {"analyzed": 100, "resolved": 80, "partial": 15, "unresolved": 5}
_REVISION = {"git_head": "1" * 40, "source_digest": "2" * 64, "dirty": False}
_MIXED = {
    "components_from": "contract",
    "totals": _TOTALS,
    "snapshot": _REVISION,
    "components": [["alpha", "Calls beta."], ["beta", "Is called."]],
    "modules": [["m.a", "m/a.py", 0, "a"], ["m.b", "m/b.py", 1, "b"]],
    "symbols": [
        [0, "caller", 1, "function", "def caller():", 0, 0],
        [1, "callee", 1, "function", "def callee():", 0, 0],
    ],
    # Three resolved call sites and two partial ones, one with two candidate edges.
    "edges": [
        [0, 1, False, 3, 0],
        [0, 1, False, 4, 1],
        [0, 1, False, 5, 2],
        [0, 1, True, 6, 3],
        [0, 0, True, 7, 4],
        [0, 1, True, 7, 4],
    ],
    "unknown": [],
}


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(800, 600), (1440, 900)])
def test_an_incomplete_snapshot_remains_visible_with_its_notes_and_unknowns(
    studio: Studio, width: int, height: int
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    state_answer = {
        "api_version": API_VERSION,
        "agent": "codex",
        "root_name": "shop",
        "contract": "not_configured",
        "explore": "incomplete",
        "seconds": 8,
        "exit_code": 2,
        "notes": [
            "The TypeScript alias is unresolved.",
            "The TypeScript alias is unresolved.",
            "The TypeScript alias is unresolved.",
        ],
    }
    graph_body = {
        **_MIXED,
        "symbols": [[0, "caller", 1, "function", "function caller()", 1, 0], _MIXED["symbols"][1]],
        "unknown": [[0, "aliasCall()", "unresolved alias", 2]],
    }
    graph_answer = {"api_version": API_VERSION, "explore": "incomplete", "graph": graph_body}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            detail_payload = _answer(_checked(snapshot_completeness="incomplete"), id="partial")
            page.route("**/api/v1/state", lambda route: route.fulfill(json=state_answer))
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=graph_answer))
            page.route(
                "**/api/v1/stories",
                lambda route: route.fulfill(
                    json={
                        "api_version": API_VERSION,
                        "stories": [
                            {
                                "id": "partial",
                                "title": "Partial source flow",
                                "steps": 2,
                                "source": "repository",
                                "created": None,
                                "checked_counts": {
                                    "proven": 1,
                                    "declared": 0,
                                    "claim": 0,
                                    "unknown": 1,
                                    "missing": 0,
                                },
                            }
                        ],
                    }
                ),
            )
            page.route(
                "**/api/v1/stories/partial", lambda route: route.fulfill(json=detail_payload)
            )
            Draft202012Validator(_VIEW_CHECK_SCHEMA).validate(detail_payload["checked"])
            page.goto(studio.url)
            page.get_by_text("Snapshot is incomplete", exact=False).wait_for()
            assert page.get_by_text("3 diagnostic notes", exact=False).is_visible()
            assert page.get_by_text("Next: inspect notes.", exact=True).is_visible()
            assert not page.get_by_text(
                "The TypeScript alias is unresolved.", exact=False
            ).is_visible()
            page.get_by_text("Show diagnostic details", exact=False).click()
            assert page.get_by_text("The TypeScript alias is unresolved.", exact=False).is_visible()
            page.locator(".briefing-signals > summary").click()
            assert page.get_by_text("Most unknown calls: alpha (1).", exact=False).is_visible()
            page.get_by_role("link", name="Architecture", exact=True).click()
            page.get_by_role("group", name="Component map").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            incomplete_answer = {
                "api_version": API_VERSION,
                "agent": "codex",
                "snapshot_completeness": "incomplete",
                "blocks": [
                    {"kind": "claim", "text": "Snapshot-local claim.", "refs": [], "label": None}
                ],
                "facts": [],
                "dropped_refs": ["shop.missing"],
                "applied": False,
            }
            page.route("**/api/v1/chat", lambda route: route.fulfill(json=incomplete_answer))
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            assert chat.get_by_text("Selected agent: codex").is_visible()
            assert chat.get_by_text("Snapshot: incomplete").is_visible()
            chat.get_by_role("textbox", name="Question").fill("What is missing?")
            chat.get_by_role("button", name="Ask", exact=True).click()
            chat.get_by_text("Missing refs or calls do not establish absence.").wait_for()
            assert chat.get_by_text("Agent: codex · snapshot: incomplete", exact=False).is_visible()
            assert chat.get_by_text(
                "not found by exact name in this snapshot", exact=False
            ).is_visible()
            page.get_by_role("link", name="Stories", exact=True).click()
            page.get_by_text("Counts use an incomplete snapshot.", exact=False).wait_for()
            assert page.get_by_text("1 unknown", exact=False).is_visible()
            page.get_by_role("link", name="Partial source flow", exact=False).click()
            page.get_by_role("heading", name=detail_payload["checked"]["story"]["title"]).wait_for()
            assert page.get_by_text(
                "The source snapshot is incomplete; UNKNOWN means evidence is missing."
            ).is_visible()
            page.get_by_role("link", name="Open the static report").click()
            page.get_by_text(
                "The source snapshot is incomplete; UNKNOWN means evidence is missing."
            ).wait_for()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(800, 600), (1440, 900)])
@pytest.mark.parametrize(
    ("explore", "expected", "role"),
    [
        ("failed", "Explore failed · exit code 1", "alert"),
        ("done", "Explore finished, but no graph is available", "alert"),
        ("running", "Explore is running · 8 s", "status"),
    ],
)
def test_briefing_shows_the_current_explore_status_and_next_step(
    studio: Studio, width: int, height: int, explore: str, expected: str, role: str
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    state_answer = {
        "api_version": API_VERSION,
        "root_name": "shop",
        "contract": "not_configured",
        "explore": explore,
        "seconds": 8,
        "exit_code": 1 if explore == "failed" else None,
        "notes": ["TypeScript diagnostics are unavailable for this fixture."] * 128,
    }
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/v1/state", lambda route: route.fulfill(json=state_answer))
            if explore == "done":
                page.route(
                    "**/api/v1/graph",
                    lambda route: route.fulfill(
                        json={"api_version": API_VERSION, "explore": "done", "graph": None}
                    ),
                )
            page.goto(studio.url + "#/overview")
            status = page.get_by_role(role)
            status.get_by_text(expected, exact=True).wait_for()
            assert status.get_by_text("Next:", exact=False).is_visible()
            if explore == "failed":
                assert status.get_by_text("128 diagnostic notes", exact=False).is_visible()
                assert status.locator("details").count() == 1
                assert not status.get_by_text(
                    "TypeScript diagnostics are unavailable for this fixture.", exact=True
                ).is_visible()
                assert status.get_by_text(
                    "Next: fix the cause, then restart Studio to run Explore again.", exact=True
                ).is_visible()
                page.get_by_role("link", name="Open the static report").click()
                report_status = page.get_by_role("alert")
                assert report_status.get_by_text("128 diagnostic notes", exact=False).is_visible()
                assert not report_status.get_by_text(
                    "TypeScript diagnostics are unavailable for this fixture.", exact=True
                ).is_visible()
                page.get_by_role("link", name="Stories", exact=True).click()
                stories_status = page.get_by_role("alert")
                assert stories_status.get_by_text("128 diagnostic notes", exact=False).is_visible()
                assert not stories_status.get_by_text(
                    "TypeScript diagnostics are unavailable for this fixture.", exact=True
                ).is_visible()
            if explore == "done":
                assert status.get_by_text(
                    "Next: restart Studio to run Explore again.", exact=True
                ).is_visible()
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()


@pytest.mark.browser
def test_a_line_with_claims_is_a_claim_and_shows_both_counts(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _MIXED}
    Draft202012Validator({"$ref": "#/$defs/graph", "$defs": _SCHEMA["$defs"]}).validate(answer)
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url)
            page.get_by_text("Declared groups: contract", exact=True).wait_for()
            label = page.locator("button.count")
            # 3 proven and 2 claim call sites: a line with a claim is never read as proven.
            assert label.inner_text().strip() == "3 ✓ proven · 2 ✎ claim"
            assert "claim" in label.get_attribute("class").split()
            assert (
                label.get_attribute("aria-label") == "5 calls from alpha to beta: 3 proven, 2 claim"
            )
            assert page.locator("path.link.claim").count() == 1
            assert page.locator("path.link.proven").count() == 0
            # The toolbar counts sites too: the claim with two edges is one claim.
            assert "3 ✓ proven · 2 ✎ claim calls between components" in page.locator(
                ".summary"
            ).inner_text().replace("\n", " ")
            label.click()
            details = page.get_by_role("complementary", name="Details")
            details.get_by_text("3 ✓ proven · 2 ✎ claim · 1 distinct pair").wait_for()
        finally:
            browser.close()


@pytest.mark.browser
def test_the_shell_shows_an_invalid_contract_and_refuses_another_api_version(
    studio: Studio, tmp_path: Path
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    broken = _repository(tmp_path / "broken")
    assert main(["init", "--root", str(broken), "--json"]) == 0
    (broken / load_config(broken).contract).write_text("{not json")
    server = _start(broken, tmp_path / "cache")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(server.url)
            page.get_by_text("Contract: INVALID", exact=True).wait_for()

            other = browser.new_page()
            other.route(
                "**/api/v1/state",
                lambda route: route.fulfill(json={"api_version": "2.0.0"}),
            )
            other.goto(studio.url)
            alert = other.get_by_role("alert")
            alert.wait_for()
            assert "2.0.0" in alert.inner_text() and API_VERSION in alert.inner_text()
        finally:
            browser.close()
            _stop(server)


@pytest.mark.browser
def test_the_fixture_leaves_the_environment_of_the_test_process_unchanged(studio: Studio) -> None:
    assert {name: os.environ.get(name) for name in _ENVIRONMENT} == _ENVIRONMENT


_CHECKED = json.loads((Path(__file__).parent / "studio_check_flow.checked.json").read_bytes())
_PLACE = "shop.app.orders.place"
_SAVE = "shop.store.repository.save"
_FACT = {
    "qualified_name": _PLACE,
    "file": "shop/app/orders.py",
    "line": 4,
    "resolved_callers": 0,
    "resolved_callees": 1,
    "unknown_calls": 0,
}
_ANSWER = {
    "api_version": API_VERSION,
    "agent": "claude",
    "snapshot_completeness": "complete",
    "applied": False,
    "blocks": [
        {"kind": "claim", "text": "place saves the order.", "refs": [_PLACE, _SAVE], "label": None},
        {
            "kind": "proposal",
            "text": "Name the use case in the story.",
            "refs": [_PLACE],
            "label": "PROPOSED - NOT APPLIED",
        },
    ],
    "facts": [_FACT],
    "dropped_refs": ["shop.nothing"],
    "story": None,
}


def _lens(page, studio: Studio) -> None:
    page.goto(studio.url)
    page.locator(".map-card", has_text="app").dblclick()
    page.locator(".level-card", has_text="orders.py").dblclick()
    page.locator(".level-card", has_text="place").dblclick()
    page.locator(".lens-card.center").wait_for()


@pytest.mark.browser
def test_story_draft_action_requires_a_function_or_method_selection(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    graph = {
        **_MIXED,
        "symbols": [
            *_MIXED["symbols"],
            [0, "Widget", 8, "class", "class Widget:", 0, 0],
            [0, "Widget.run", 9, "method", "def run(self):", 0, 0],
        ],
    }
    graph_answer = {"api_version": API_VERSION, "explore": "done", "graph": graph}
    asks: list[dict] = []

    def reply(route) -> None:
        asks.append(route.request.post_data_json)
        route.fulfill(json=_ANSWER)

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=graph_answer))
            page.route("**/api/v1/chat", reply)

            page.goto(studio.url + "#/explore/0")
            page.locator(".lens-card.center").wait_for()
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            draft = chat.get_by_role("button", name="Draft story")
            assert not draft.is_disabled()

            page.goto(studio.url + "#/explore/3")
            page.locator(".lens-card.center").wait_for()
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            assert not chat.get_by_role("button", name="Draft story").is_disabled()

            page.goto(studio.url + "#/explore/2")
            page.locator(".lens-card.center").wait_for()
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            draft = chat.get_by_role("button", name="Draft story")
            assert draft.is_disabled()
            chat.get_by_text(
                "Story drafts start from a function or method. Select one to enable Draft story."
            ).wait_for()
            chat.get_by_role("textbox", name="Question").fill("What does this class do?")
            chat.get_by_role("button", name="Ask", exact=True).click()
            chat.get_by_role("region", name="Claim").wait_for()
            assert asks == [
                {"question": "What does this class do?", "context": "m.a.Widget", "mode": "answer"}
            ]
        finally:
            browser.close()


@pytest.mark.browser
def test_class_proposal_does_not_offer_story_actions(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    graph = {
        **_MIXED,
        "symbols": [
            *_MIXED["symbols"],
            [0, "Widget", 8, "class", "class Widget:", 0, 0],
            [0, "Widget.run", 9, "method", "def run(self):", 0, 0],
        ],
    }
    graph_answer = {"api_version": API_VERSION, "explore": "done", "graph": graph}
    class_answer = {
        **_ANSWER,
        "blocks": [
            _ANSWER["blocks"][0],
            {
                "kind": "proposal",
                "text": "Inspect this class.",
                "refs": ["m.a.Widget"],
                "label": "PROPOSED - NOT APPLIED",
            },
        ],
    }

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=graph_answer))
            page.route("**/api/v1/chat", lambda route: route.fulfill(json=class_answer))
            page.goto(studio.url + "#/explore/2")
            page.locator(".lens-card.center").wait_for()
            page.get_by_role("button", name="Ask", exact=True).click()

            chat = page.get_by_role("region", name="Ask the agent")
            chat.get_by_role("textbox", name="Question").fill("What does this class do?")
            chat.get_by_role("button", name="Ask", exact=True).click()
            proposal = chat.get_by_role("region", name="Proposed")
            proposal.get_by_text("Inspect this class.").wait_for()
            assert chat.get_by_role("button", name="Draft story").is_disabled()
            assert proposal.get_by_role("button", name="Draft a story").is_disabled()
            assert proposal.get_by_role("button", name="Pin to story").is_disabled()
        finally:
            browser.close()


@pytest.mark.browser
def test_the_chat_marks_claim_proposal_and_observed_apart(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    seen: list[dict] = []
    requests: list[str] = []

    def answer(route) -> None:
        seen.append({"headers": route.request.headers, "body": route.request.post_data_json})
        route.fulfill(json=_ANSWER)

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("request", lambda item: requests.append(item.url))
            page.route("**/api/v1/chat", answer)
            _lens(page, studio)
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            assert chat.get_by_text("Context: place").is_visible()
            assert chat.get_by_text("Selected agent: claude").is_visible()
            assert chat.get_by_role("button").filter(has_text="?").count() == 4  # quick questions
            chat.get_by_role("textbox", name="Question").fill("What does place do?")
            chat.get_by_role("button", name="Ask", exact=True).click()
            chat.get_by_text("CLAIM", exact=False).first.wait_for()
            assert seen[0]["body"] == {
                "question": "What does place do?",
                "context": _PLACE,
                "mode": "answer",
            }
            assert seen[0]["headers"]["x-archkeel-studio"]
            assert seen[0]["headers"]["content-type"] == "application/json"
            # Three kinds, three marks: agent text never reads OBSERVED.
            claim = chat.get_by_role("region", name="Claim")
            proposal = chat.get_by_role("region", name="Proposed")
            observed = chat.get_by_role("region", name="Observed")
            flat = lambda item: " ".join(item.inner_text().split())  # noqa: E731
            assert "✎ CLAIM" in flat(claim)
            assert "◌ PROPOSED - NOT APPLIED" in flat(proposal)
            assert "✓ OBSERVED" in flat(observed)
            assert "OBSERVED" not in flat(claim) + flat(proposal)
            assert "orders.py:4" in flat(observed)
            assert "1 reference not found by exact name" in flat(chat)
            assert chat.get_by_text("Selected agent: claude", exact=True).is_visible()
            assert chat.get_by_text("Agent: claude · snapshot: complete", exact=False).is_visible()
            # "Pin to story" shows the draft of the trace and writes nothing.
            proposal.get_by_role("button", name="Pin to story").click()
            proposal.locator("pre.draft").wait_for()
            assert '"schema_version": "1.2.0"' in proposal.locator("pre.draft").inner_text()
            # A ref opens the lens at that function; the conversation stays.
            claim.get_by_role("link", name="save").click()
            page.locator(".lens-card.center", has_text="save").wait_for()
            # The chat panel stays open on the next page, and the conversation with it.
            assert page.get_by_role("region", name="Ask the agent").is_visible()
            page.get_by_text("What does place do?").wait_for()
        finally:
            browser.close()
    assert [url for url in requests if urlsplit(url).netloc != f"127.0.0.1:{studio.port}"] == [
        url for url in requests if urlsplit(url).scheme in _LOCAL_SCHEMES
    ]


@pytest.mark.browser
@pytest.mark.parametrize(
    ("status", "body", "shown"),
    [
        (409, {"api_version": API_VERSION, "error": "busy", "detail": "busy"}, "still answers"),
        (
            503,
            {"api_version": API_VERSION, "error": "agent_not_installed", "detail": "x"},
            "No agent found",
        ),
        (
            502,
            {"api_version": API_VERSION, "error": "repository_changed", "detail": "x"},
            "discarded the answer",
        ),
        (405, "method not allowed", "chat is not available"),
    ],
)
def test_the_chat_says_why_it_has_no_answer(studio: Studio, status: int, body, shown: str) -> None:
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            reply = {"json": body} if isinstance(body, dict) else {"body": body}
            page.route("**/api/v1/chat", lambda route: route.fulfill(status=status, **reply))
            _lens(page, studio)
            page.get_by_role("button", name="Ask", exact=True).click()
            page.get_by_role("button", name="What does this function do?").click()
            page.get_by_role("alert").filter(has_text=shown).wait_for()
            # The panel works again after an error.
            assert page.get_by_role("textbox", name="Question").is_enabled()
        finally:
            browser.close()


def _answer(checked: dict, **changes: object) -> dict:
    """The body of `GET /api/v1/stories/<id>` for a checked story from the repository."""
    return {
        "api_version": API_VERSION,
        "id": "check-flow",
        "source": "repository",
        "checked": checked,
        "rebound": True,
        "created": {
            "created": "2026-11-04T10:00:00Z",
            "git_head": "a" * 40,
            "author_kind": "agent",
            "agent": "claude",
        },
        "head": "b" * 40,
    } | changes


def _checked(**changes) -> dict:
    """API 1.3 checked flow, plus a claim with 58 candidates and a Redis touchpoint."""
    checked = json.loads(json.dumps(_CHECKED))
    # The stored fixture predates API 1.3's result version, completeness and step label fields.
    checked["result_schema_version"] = "1.3.0"
    checked["snapshot_completeness"] = "complete"
    story = checked["story"]
    for step in story["steps"]:
        step.setdefault("label", step["node"])
    story["steps"][2]["external"] = [
        {"system": "redis", "touched": True, "direction": "reads", "evidence": []}
    ]
    story["verdict"]["systems"] = ["redis"]
    link = checked["steps"][5]
    link["evidence"] = [
        {
            "record_id": "CALL-TEST",
            "kind": link["kind"],
            "source": link["source"],
            "target": link["target"],
            "evidence_id": None,
            "file": "src/archkeel/x.py",
            "line": 7,
            "type_only": False,
            "candidates": 58,
        }
    ]
    return checked | changes


@pytest.mark.browser
def test_chat_downloads_the_unchanged_checked_story_and_shows_incomplete_unknown(
    studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    checked = _checked(snapshot_completeness="incomplete")
    checked["steps"][1]["status"] = "declared"
    checked["steps"][2]["status"] = "missing"
    checked["steps"][0]["note"] = "This call encrypts every request."
    checked["title"] = "Every request is encrypted"
    checked["story"]["title"] = checked["title"]
    checked["story"]["verdict"].update(proven=3, declared=1, missing=1)
    nodes = [step["node"] for step in checked["story"]["steps"]]
    candidate = {
        "schema_version": "1.2.0",
        "title": checked["title"],
        "snapshot": checked["snapshot"],
        "nodes": nodes,
        "story": {"id": "check-flow", "title": checked["title"], "chapters": []},
        "steps": [
            {
                "node": node,
                "note": checked["steps"][index]["note"] or "Agent-authored text.",
            }
            for index, node in enumerate(nodes)
        ],
        "author_kind": "agent",
        "agent": "codex",
    }
    for index, link in enumerate(checked["steps"]):
        if index != 0:
            link["note"] = "Agent-authored text."
    answer = {
        "api_version": API_VERSION,
        "agent": "codex",
        "snapshot_completeness": "incomplete",
        "blocks": [],
        "facts": [],
        "dropped_refs": [],
        "story": {"candidate": candidate, "checked": checked},
        "applied": False,
    }
    seen: list[dict] = []

    def reply(route) -> None:
        seen.append(route.request.post_data_json)
        route.fulfill(json=answer)

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/chat", reply)
            _lens(page, studio)
            page.get_by_role("button", name="Ask", exact=True).click()
            chat = page.get_by_role("region", name="Ask the agent")
            chat.get_by_role("textbox", name="Question").fill("Explain this flow")
            chat.get_by_role("button", name="Draft story").click()
            draft = page.get_by_role("region", name="Checked story draft")
            draft.get_by_text(
                "At least one completeness check is incomplete; UNKNOWN does not establish absence."
            ).wait_for()
            title_claim = draft.locator("h5 .badge.claim")
            assert "claim: every request is encrypted" in title_claim.inner_text().lower()
            first_status = draft.locator("ol li").nth(0)
            assert first_status.locator(".mark.proven").count() == 1
            note_claim = first_status.locator(".badge.claim")
            assert "claim: this call encrypts every request." in note_claim.inner_text().lower()
            assert first_status.get_by_text("declared", exact=True).count() == 0
            declared_status = draft.locator("ol li").nth(1)
            assert declared_status.locator(".mark.claim").count() == 1
            assert declared_status.get_by_text("declared", exact=True).count() == 0
            second_status = draft.locator("ol li").nth(2)
            unknown_mark = second_status.locator(".mark.unknown")
            unknown_mark.wait_for()
            assert "unknown" in unknown_mark.inner_text()
            assert second_status.get_by_text("missing", exact=True).count() == 0
            draft.get_by_text("1 declared", exact=False).wait_for()
            draft.get_by_text("Agent-authored text.", exact=False).first.wait_for()
            draft.get_by_text("View candidate JSON").click()
            draft.get_by_text("Agent-authored text.", exact=False).first.wait_for()
            with page.expect_download() as pending:
                draft.get_by_role("button", name="Download checked story JSON").click()
            download = pending.value
            assert download.suggested_filename == "check-flow.story.json"
            assert json.loads(Path(download.path()).read_text()) == candidate
            assert seen == [{"question": "Explain this flow", "context": _PLACE, "mode": "story"}]
        finally:
            browser.close()


@pytest.mark.browser
def test_a_story_plays_and_a_claim_never_reads_as_proven(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    requests: list[str] = []
    row = {
        "id": "check-flow",
        "title": _CHECKED["story"]["title"],
        "steps": len(_CHECKED["steps"]),
        "source": "repository",
        "created": None,
        "checked_counts": None,
    }
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("request", lambda item: requests.append(item.url))
            # This fixture starts the server without launching Explore; provide the ready state.
            page.route(
                "**/api/v1/state",
                lambda route: route.fulfill(
                    json={
                        "api_version": API_VERSION,
                        "root_name": "shop",
                        "contract": "not_configured",
                        "explore": "done",
                        "seconds": 8,
                        "exit_code": 0,
                        "notes": [],
                    }
                ),
            )
            page.route(
                "**/api/v1/graph",
                lambda route: route.fulfill(
                    json={"api_version": API_VERSION, "explore": "done", "graph": _MIXED}
                ),
            )
            page.route(
                "**/api/v1/stories",
                lambda route: route.fulfill(json={"api_version": API_VERSION, "stories": [row]}),
            )
            page.route(
                "**/api/v1/stories/check-flow",
                lambda route: route.fulfill(
                    json=_answer(_checked(snapshot_completeness="incomplete"))
                ),
            )
            page.goto(studio.url)
            page.get_by_role("link", name="Stories", exact=True).click()
            page.get_by_role("link", name=_CHECKED["story"]["title"]).wait_for()
            page.get_by_role("link", name=_CHECKED["story"]["title"]).click()
            page.get_by_role("heading", name=row["title"]).wait_for()
            page.get_by_text(
                "The source snapshot is incomplete; UNKNOWN means evidence is missing."
            ).wait_for()
            verdict = page.get_by_label("Verdict").inner_text().replace("\n", " ")
            assert "5 ✓ proven · 1 ✎ claim · 2 ? unknown" in verdict
            assert "systems: redis" in verdict
            step = page.get_by_role("complementary", name="Step")
            assert "STEP 1 / 8" in step.inner_text()
            assert step.get_by_text("Author text is a claim").is_visible()
            # Play moves to the next step by itself; the keys and the dots move too.
            page.get_by_role("button", name="Play story").click()
            page.get_by_text("STEP 2 / 8").wait_for(timeout=8000)
            page.get_by_role("button", name="Pause").click()
            page.keyboard.press("ArrowRight")
            assert "STEP 3 / 8" in step.inner_text()
            assert step.get_by_text("redis").is_visible()  # the touchpoint of step 3
            assert step.get_by_text("reads · claim").is_visible()
            # Every dot names its status; walk the whole story.
            statuses = [
                ("proven", "✓ proven"),
                ("proven", "✓ proven"),
                ("proven", "✓ proven"),
                ("unknown", "? unknown"),
                ("proven", "✓ proven"),
                ("claim", "✎ claim"),
                ("proven", "✓ proven"),
                ("unknown", "? unknown"),
            ]
            for index, (word, mark) in enumerate(statuses):
                page.get_by_role("button", name=f"Step {index + 1}: {word}").click()
                head = step.locator(".step-no").inner_text()
                assert mark in head, (index, head)
                if word != "proven":
                    assert "proven" not in head
            page.get_by_role("button", name="Step 6: claim").click()
            assert page.get_by_text("58 candidates").count() >= 1
            page.get_by_role("button", name="Step 4: unknown").click()
            assert step.get_by_text("Question for the architect").is_visible()
            # The card cuts a long name in the middle; the panel has the full name.
            card = page.locator(".story-card").nth(4)
            # The whole qualified name shows, over as many lines as it needs; nothing is cut.
            assert card.locator("b").inner_text() == _CHECKED["story"]["steps"][4]["node"]
            assert card.get_attribute("title") is None
            assert page.evaluate("document.documentElement.scrollWidth") <= 1440
            # No arrow encodes a flow: the route has no marker.
            assert page.locator("svg.routes [marker-end], svg.routes marker").count() == 0
        finally:
            browser.close()
    assert [
        url for url in requests if urlsplit(url).netloc not in {f"127.0.0.1:{studio.port}", ""}
    ] == [url for url in requests if urlsplit(url).scheme in _LOCAL_SCHEMES]


@pytest.mark.browser
def test_reduced_motion_plays_to_the_final_state(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 800, "height": 600}, reduced_motion="reduce")
            page.route(
                "**/api/v1/stories/check-flow",
                lambda route: route.fulfill(json=_answer(_checked())),
            )
            page.goto(studio.url + "#/stories/check-flow")
            page.get_by_role("button", name="Play story").click()
            page.get_by_text("STEP 8 / 8").wait_for(timeout=2000)
            assert page.evaluate("document.documentElement.scrollWidth") <= 800
        finally:
            browser.close()


@pytest.mark.browser
def test_a_story_of_the_root_is_checked_by_the_server(studio: Studio) -> None:
    """The real route: a draft spec of the trace is listed, checked and played."""
    api = pytest.importorskip("playwright.sync_api")

    cookie = login(studio)
    response, body = request(studio, f"/api/v1/draft?from={_PLACE}", cookie=cookie)
    assert response.status == 200
    spec = json.loads(body)["spec"]
    folder = studio.workspace.stories.folders[-1][1]  # type: ignore[union-attr]
    folder.mkdir(parents=True, exist_ok=True)
    spec["steps"][0] |= {"title": "The use case", "note": "place builds the order and saves it."}
    (folder / "place-draft.story.json").write_text(json.dumps(spec))
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(studio.url + "#/stories")
            page.get_by_role("link", name=f"Story from {_PLACE}").click()
            step = page.get_by_role("complementary", name="Step")
            step.get_by_text("place builds the order and saves it.").wait_for()
            assert "✓ proven" in step.locator(".step-no").inner_text()
        finally:
            browser.close()


_WITH_SYMBOLS = re.compile(r"[1-9]\d* symbol")
_LONG = "a_component_with_a_very_long_name_that_keeps_going"
_STRESS = {
    "components_from": "contract",
    "totals": _TOTALS,
    "snapshot": _REVISION,
    "components": [
        [_LONG, "Own a long sentence about what this component does, " * 4],
        ["second_component_with_a_long_label", "Calls the first one. " * 6],
        ["c", "short"],
    ],
    "modules": [
        [
            "pkg.sub.module_with_a_very_long_name_here",
            "pkg/sub/module_with_a_very_long_name_here.py",
            0,
            "sub.module_with_a_very_long_name_here",
        ],
        [
            "pkg.other_long_module_name_number_two",
            "pkg/other_long_module_name_number_two.py",
            1,
            "other_long_module_name_number_two",
        ],
        ["c.m", "c/m.py", 2, "m"],
    ],
    "symbols": [
        [
            0,
            "VeryLongClassName.a_method_with_a_really_long_name_for_testing",
            1,
            "method",
            "def a_method_with_a_really_long_name_for_testing(self, argument_one) -> Some:",
            3,
            2,
        ],
        [
            1,
            "another_function_with_a_long_name_for_the_test",
            1,
            "function",
            "def another():",
            0,
            0,
        ],
        [2, "f", 1, "function", "def f():", 0, 0],
    ],
    "edges": [[0, 1, False, 3, 0], [0, 1, True, 4, 1], [1, 2, False, 5, 2], [2, 0, False, 6, 3]],
    "unknown": [[0, "some.expression.that.is.long.enough.to.matter()", "dynamic attribute", 9]],
}


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(1440, 900), (1000, 700)])
def test_no_text_crosses_the_border_of_a_card_on_any_level(
    studio: Studio, width: int, height: int
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _STRESS}
    Draft202012Validator({"$ref": "#/$defs/graph", "$defs": _SCHEMA["$defs"]}).validate(answer)
    story = _answer(_checked())
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.route("**/api/v1/stories/check-flow", lambda route: route.fulfill(json=story))
            for fragment, selector in (
                ("#/map", ".map-card"),
                ("#/component/0", ".level-card"),
                ("#/module/0", ".level-card"),
                ("#/explore/0", ".lens-card.center"),
                ("#/stories/check-flow", ".story-card"),
            ):
                page.goto(studio.url + fragment)
                page.locator(selector).first.wait_for()
                page.wait_for_timeout(700)  # the cards fade in
                _no_overflow(page)
                assert page.evaluate("document.documentElement.scrollWidth") <= width, fragment
            # A story card shows the whole qualified name; nothing is cut.
            names = page.locator(".story-card b").all_inner_texts()
            assert names == [step["node"] for step in _CHECKED["story"]["steps"]]
            assert not any("…" in name for name in names)
        finally:
            browser.close()


@pytest.mark.browser
def test_enter_drills_in_reduced_motion_does_not_zoom_and_the_report_left_the_nav(
    studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
            )
            page.goto(studio.url)
            page.locator(".map-card").first.wait_for()
            # The static report is a secondary link, not a page of the workspace.
            nav = page.get_by_role("navigation", name="Workspace")
            assert "Report" not in nav.inner_text()
            note = page.locator(".secondary")
            assert "Open the static report" in note.inner_text()
            assert "CI and Pages" in note.inner_text()
            page.locator(".map-card", has_text="app").focus()
            page.keyboard.press("Enter")
            page.locator(".level-card", has_text="orders.py").wait_for()
            assert page.locator("section.canvas").get_attribute("data-transition") == "none"
        finally:
            browser.close()


def _grid_graph() -> dict:
    """Component alpha: 30 modules in 5 packages (module 0 has 20 functions); beta calls in."""
    modules = [
        [f"alpha.p{p}.m{j}", f"alpha/p{p}/m{j}.py", 0, f"p{p}.m{j}"]
        for p in range(5)
        for j in range(6)
    ] + [["beta.b", "beta/b.py", 1, "b"]]
    symbols = []
    first = []
    for module in range(31):
        first.append(len(symbols))
        for k in range(20 if module == 0 else 3):
            symbols.append([module, f"fn{k}", k + 1, "function", f"def fn{k}():", 0, 0])
    edges = []
    for module in range(30):
        target = (module * 7 + 3) % 30
        edges.append([first[module], first[target] + 1, False, 2, len(edges)])
        edges.append([first[module] + 2, first[(module + 1) % 30], True, 3, len(edges)])
    # Inside module 0: a chain of calls; and beta calls into it and into module 9.
    edges += [[first[0] + k, first[0] + k + 1, False, 5, len(edges)] for k in range(10)]
    edges += [
        [first[30], first[0] + 3, False, 4, len(edges)],
        [first[30], first[9], False, 4, len(edges)],
    ]
    return {
        "components_from": "contract",
        "totals": _TOTALS,
        "snapshot": _REVISION,
        "components": [["alpha", "Alpha does the work."], ["beta", "Beta calls alpha."]],
        "modules": modules,
        "symbols": symbols,
        "edges": edges,
        "unknown": [],
    }


def _crossings(page) -> list[str]:
    """The segments of every drawn line that cross the inside of a card, a stub or a tile."""
    return page.evaluate(
        """() => {
        const boxes = [...document.querySelectorAll('.lens-card')].map((card) => ({
          name: card.textContent.slice(0, 30),
          x: parseFloat(card.style.left), y: parseFloat(card.style.top),
          w: parseFloat(card.style.width), h: parseFloat(card.style.height)}));
        const bad = [];
        for (const path of document.querySelectorAll('.focus-line .stroke')) {
          const points = path.dataset.points.split(' ').map((pair) => pair.split(',').map(Number));
          for (let i = 1; i < points.length; i += 1) {
            const [x1, y1] = points[i - 1]; const [x2, y2] = points[i];
            const [x0, x3] = [Math.min(x1, x2), Math.max(x1, x2)];
            const [y0, y3] = [Math.min(y1, y2), Math.max(y1, y2)];
            for (const b of boxes) {
              const across = x3 > b.x + 0.5 && x0 < b.x + b.w - 0.5;
              if (across && y3 > b.y + 0.5 && y0 < b.y + b.h - 0.5) {
                bad.push(b.name);
              }
            }
          }
        }
        return bad;
      }"""
    )


def _smallest_text(page) -> float:
    """The smallest font size of the canvas as drawn: the font size times the scale of the fit."""
    return page.evaluate(
        """() => {
        const k = parseFloat(document.querySelector('.stage').dataset.camera.split(',')[2]);
        const sizes = [...document.querySelectorAll(
          '.stage .lens-card b, .stage .lens-card .meta, .stage .head, .stage .plate span')]
          .filter((item) => item.textContent.trim() !== '')
          .map((item) => parseFloat(getComputedStyle(item).fontSize) * k);
        return Math.min(...sizes);
      }"""
    )


@pytest.mark.browser
def test_a_level_is_calm_until_a_card_has_the_focus(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    Draft202012Validator({"$ref": "#/$defs/graph", "$defs": _SCHEMA["$defs"]}).validate(answer)
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + "#/component/0")
            page.locator(".level-card").first.wait_for()
            page.wait_for_timeout(700)
            # Calm at rest: no line, a tile for the folded packages, no text under 10 px.
            assert page.locator(".focus-line").count() == 0
            assert page.locator(".lens-card.tile").count() >= 1
            assert page.locator(".level-card").count() <= 12
            assert _smallest_text(page) >= 9.95
            # Hover lights the lines of one card and dims the cards that are not connected.
            card = page.locator(".level-card", has_text="m0.py").first
            card.hover()
            page.locator(".focus-line").first.wait_for(state="attached")
            assert page.locator(".level-card.dim").count() >= 1
            assert page.locator(".level-card:not(.dim)").count() >= 2
            assert _crossings(page) == []
            # A click pins the focus: the lines stay when the pointer leaves; Esc clears them.
            card.click()
            page.locator(".level-card.pinned").wait_for()
            page.mouse.move(5, 5)
            assert page.locator(".focus-line").count() >= 1
            focus = page.get_by_text("Selected ·").first
            assert focus.is_visible()
            page.keyboard.press("Escape")
            page.locator(".level-card.pinned").wait_for(state="detached")
            assert page.locator(".focus-line").count() == 0
            assert "#/component/0" in page.url  # the first Esc cleared the focus, it did not go up
            # A stub names the functions on the other side while a card has the focus.
            page.locator(".level-card", has_text="m0.py").first.hover()
            assert "fn0" in page.locator(".lens-card.stub").first.inner_text()
            # The module level: 16 functions and a tile; the lines stay in the gutters.
            page.goto(studio.url + "#/module/0")
            page.locator(".level-card").first.wait_for()
            page.wait_for_timeout(700)
            assert page.locator(".level-card").count() == 16
            assert page.locator(".lens-card.tile").count() == 1
            assert _smallest_text(page) >= 9.95
            for name in ("fn1", "fn3", "fn9"):
                page.locator(".level-card", has_text=name).first.hover()
                page.locator(".focus-line").first.wait_for(state="attached")
                assert _crossings(page) == []
            # A pinned card keeps its list; a row of the side panel lights one line.
            page.locator(".level-card", has_text="fn1").first.click()
            page.locator(".focus-rows li").first.hover()
            assert page.locator(".focus-line.on").count() == 1
        finally:
            browser.close()


def _boxes_overlap(page) -> list[str]:
    """Pairs of cards, column labels and plate labels whose boxes overlap, as drawn."""
    return page.evaluate(
        """() => {
        const items = [...document.querySelectorAll(
          '.stage .lens-card, .stage .map-card, .stage .head, .stage .plate span, .stage .band')]
          .filter((item) => item.getBoundingClientRect().width > 0)
          .map((item) => ({ name: item.textContent.trim().slice(0, 24),
            box: item.getBoundingClientRect() }));
        const bad = [];
        for (let i = 0; i < items.length; i += 1) {
          for (let j = i + 1; j < items.length; j += 1) {
            const a = items[i].box; const b = items[j].box;
            const across = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const down = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (across > 1 && down > 1) bad.push(items[i].name + ' | ' + items[j].name);
          }
        }
        return bad;
      }"""
    )


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(1440, 900), (1000, 700)])
def test_no_card_header_or_label_overlaps_another_on_any_level(
    studio: Studio, width: int, height: int
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            for fragment in (
                "#/map",
                "#/component/0",
                "#/component/0/p1",
                "#/module/0",
                "#/explore/2",
            ):
                page.goto(studio.url + fragment)
                page.locator(".stage .lens-card, .stage .map-card").first.wait_for()
                page.wait_for_timeout(700)
                assert _boxes_overlap(page) == [], fragment
            # With a focus: the stubs name the functions on the other side and still do not overlap.
            page.goto(studio.url + "#/module/0")
            page.locator(".level-card").first.wait_for()
            page.locator(".level-card", has_text="fn3").first.hover()
            page.wait_for_timeout(300)
            assert _boxes_overlap(page) == []
        finally:
            browser.close()


@pytest.mark.browser
def test_a_line_ends_on_the_card_it_belongs_to_and_the_dots_show_the_direction(
    studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    ends = """() => {
        const boxes = [...document.querySelectorAll('.lens-card')].map((card) => ({
          x: parseFloat(card.style.left), y: parseFloat(card.style.top),
          w: parseFloat(card.style.width), h: parseFloat(card.style.height)}));
        const onEdge = (px, py) => boxes.some((b) => {
          const inX = px >= b.x - 0.6 && px <= b.x + b.w + 0.6;
          const inY = py >= b.y - 0.6 && py <= b.y + b.h + 0.6;
          const edgeX = Math.abs(px - b.x) <= 0.6 || Math.abs(px - b.x - b.w) <= 0.6;
          const edgeY = Math.abs(py - b.y) <= 0.6 || Math.abs(py - b.y - b.h) <= 0.6;
          return inX && inY && (edgeX || edgeY);
        });
        return [...document.querySelectorAll('.focus-line .stroke')].map((path) => {
          const points = path.dataset.points.split(' ').map((pair) => pair.split(',').map(Number));
          const first = points[0]; const last = points[points.length - 1];
          return onEdge(first[0], first[1]) && onEdge(last[0], last[1]);
        });
      }"""
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + "#/module/0")
            page.locator(".level-card").first.wait_for()
            page.wait_for_timeout(500)
            # At rest every stub has one faint line to a port; there is no exact line.
            assert (
                page.locator(".aggregate").count() == page.locator(".lens-card.stub").count() >= 1
            )
            assert page.locator(".focus-line").count() == 0
            page.locator(".level-card", has_text="fn3").first.hover()
            page.locator(".focus-line").first.wait_for(state="attached")
            assert page.locator(".aggregate").count() == 0
            results = page.evaluate(ends)
            assert results and all(results)  # each end is on the edge of a card, stub or tile
            # One dot for each line, in the direction of the call; the panel says so.
            assert page.locator(".focus-line .flow").count() == page.locator(".focus-line").count()
            assert "direction of the call" in page.locator(".workbench .details").inner_text()
            quiet = browser.new_page(
                viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
            )
            quiet.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            quiet.goto(studio.url + "#/module/0")
            quiet.locator(".level-card").first.wait_for()
            quiet.locator(".level-card", has_text="fn3").first.hover()
            quiet.locator(".focus-line").first.wait_for(state="attached")
            assert quiet.locator(".focus-line .flow").count() == 0
            assert quiet.locator(".focus-line .chevron").count() >= 1
        finally:
            browser.close()


@pytest.mark.browser
def test_the_links_of_a_function_card_are_the_neighbors_in_the_panel(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + "#/module/0")
            page.locator(".level-card").first.wait_for()
            for name in ("fn0", "fn1", "fn3", "fn5", "fn9"):
                card = page.locator(".level-card", has_text=name).first
                shown = int(card.locator(".meta").inner_text().split()[0])
                card.click()
                page.locator(".level-card.pinned").wait_for()
                assert page.locator(".focus-rows [data-neighbor]").count() == shown, name
                page.keyboard.press("Escape")
        finally:
            browser.close()


@pytest.fixture(scope="module")
def archkeel_studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Studio]:
    """A Studio on this repository: the real snapshot of ArchKeel itself."""
    tmp_path = tmp_path_factory.mktemp("archkeel")
    with running(Path(__file__).parents[1], tmp_path / "cache", explored=True) as server:
        yield server


@pytest.mark.browser
def test_check_evaluation_has_callers_and_no_overlap_on_the_real_snapshot(
    archkeel_studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width, height in ((1440, 900), (1000, 700)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_default_timeout(60000)
                page.goto(archkeel_studio.url)
                page.locator(".map-card").first.wait_for()
                page.wait_for_timeout(700)
                assert _boxes_overlap(page) == []
                page.locator(".map-card", has_text="check").first.dblclick()
                page.locator(".stage .lens-card").first.wait_for()
                page.wait_for_timeout(700)
                assert _boxes_overlap(page) == []
                # The package check.evaluation: its callers are other packages of check, as stubs.
                page.goto(page.url + "/evaluation")
                page.locator(".stage .level-card").first.wait_for()
                page.wait_for_timeout(700)
                assert page.locator(".level-card").count() >= 6  # never only a "+N more" tile
                callers = page.locator(".lens-card.stub[data-side='in']")
                assert callers.count() >= 1
                assert "evaluation" not in " ".join(callers.all_inner_texts()).split("\\n")[0]
                assert _boxes_overlap(page) == []
                page.locator(".level-card", has_text=_WITH_SYMBOLS).first.dblclick()
                page.locator(".stage .level-card").first.wait_for()
                page.wait_for_timeout(700)
                assert _boxes_overlap(page) == []
                page.locator(".level-card").first.dblclick()
                page.locator(".lens-card.center").wait_for()
                page.wait_for_timeout(700)
                assert _boxes_overlap(page) == []
                page.close()
        finally:
            browser.close()


@pytest.mark.browser
def test_a_dimmed_stub_keeps_its_name_and_there_is_no_tooltip(
    studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + "#/module/0")
            page.locator(".level-card").first.wait_for()
            # fn1 has no call to the module of the stub: the stub dims, name and count stay.
            card = page.locator(".level-card", has_text="fn1").first
            card.hover()
            page.locator(".lens-card.stub.dim").first.wait_for()
            stub = page.locator(".lens-card.stub.dim").first
            assert stub.locator("b").is_visible()
            assert stub.locator("b").inner_text().strip() != ""
            assert stub.locator("b").evaluate("(b) => getComputedStyle(b).visibility") == "visible"
            # There is no tooltip: the panel replaces it.
            page.wait_for_timeout(600)
            assert page.locator(".tip").count() == 0
            # The side panel keeps a function name first and wraps at the separators.
            card.click()
            row = page.locator(".focus-rows li").first
            assert row.locator("a").first.inner_text().startswith("fn")
        finally:
            browser.close()


@pytest.mark.browser
def test_the_lens_shows_the_direction_of_the_line_under_the_pointer(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(studio.url)
            page.locator(".map-card", has_text="app").dblclick()
            page.locator(".level-card", has_text="orders.py").dblclick()
            page.locator(".level-card", has_text="place").dblclick()
            page.locator(".lens-card.center").wait_for()
            assert page.locator(".focus-line").count() == 0
            page.locator("a.lens-card.proven", has_text="save").hover()
            page.locator(".focus-line .flow").wait_for(state="attached")
            assert page.locator(".focus-line .port").count() == 2
        finally:
            browser.close()


def _fragment(page) -> str:
    return page.evaluate("location.hash")


@pytest.mark.browser
def test_a_click_selects_a_double_click_opens_on_every_card_type(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _grid_graph()}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            panel = page.locator(".workbench .details")

            def selected(kind: str, name: str) -> None:
                assert f"Selected · {kind}" in panel.text_content()
                assert name in panel.text_content()

            # L1: a component card; the panel has the declared responsibility in full.
            page.goto(studio.url + "#/map")
            card = page.locator(".map-card", has_text="alpha")
            card.wait_for()
            card.click()
            page.locator(".map-card.pinned").wait_for()
            assert _fragment(page) == "#/map"
            selected("Component", "alpha")
            assert "Alpha does the work." in panel.inner_text()
            page.keyboard.press("Escape")  # clears the selection first
            page.locator(".map-card.pinned").wait_for(state="detached")
            assert _fragment(page) == "#/map"
            card.click()
            # The arrows move the selection to the next card, in any direction that has one.
            for arrow, back in (("ArrowLeft", "ArrowRight"), ("ArrowRight", "ArrowLeft")):
                page.keyboard.press(arrow)
                page.wait_for_timeout(150)
                if page.locator(".map-card.pinned", has_text="beta").count() == 1:
                    page.keyboard.press(back)
                    break
            page.locator(".map-card.pinned", has_text="alpha").wait_for()
            page.keyboard.press("Enter")  # Enter opens
            page.wait_for_url("**/#/component/0")
            # L2: a module card and a stub.
            module = page.locator(".level-card", has_text="m0.py").first
            module.wait_for()
            module.click()
            page.locator(".level-card.pinned").wait_for()
            assert _fragment(page) == "#/component/0"
            selected("Module", "alpha.p0.m0")
            stub = page.locator(".lens-card.stub").first
            stub.click()
            page.locator(".lens-card.stub.pinned").wait_for()
            assert _fragment(page) == "#/component/0"
            selected("Component", "beta")
            stub.dblclick()
            page.wait_for_url("**/#/component/1")
            page.goto(studio.url + "#/component/0")
            page.locator(".level-card", has_text="m0.py").first.dblclick()
            page.wait_for_url("**/#/module/0")
            # L3: a function card and a module stub.
            fn = page.locator(".level-card", has_text="fn3").first
            fn.click()
            page.locator(".level-card.pinned").wait_for()
            assert _fragment(page) == "#/module/0"
            selected("Function", "fn3")
            page.locator(".lens-card.stub").first.click()
            page.locator(".lens-card.stub.pinned").wait_for()
            assert _fragment(page) == "#/module/0"
            assert "Selected · Module" in panel.text_content()
            page.keyboard.press("Escape")
            page.locator(".lens-card.pinned").wait_for(state="detached")
            fn.dblclick()
            page.wait_for_url("**/#/explore/*")
            # L4: a neighbor of the lens.
            page.locator(".lens-card.center").wait_for()
            lens = _fragment(page)
            neighbor = page.locator("a.lens-card").first
            neighbor.click()
            page.locator("a.lens-card.pinned").wait_for()
            assert _fragment(page) == lens
            selected("Function", "fn")
            neighbor.dblclick()
            page.wait_for_function("(old) => location.hash !== old", arg=lens)
        finally:
            browser.close()


@pytest.mark.browser
def test_no_card_has_a_title_or_an_ellipsis(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    answer = {"api_version": API_VERSION, "explore": "done", "graph": _STRESS}
    story = _answer(_checked())
    check = """() => {
        const titled = document.querySelectorAll('.stage [title], .stage .lens-card[title]').length;
        const cut = [...document.querySelectorAll(
          '.stage .lens-card, .stage .map-card, .stage .story-card, .stage .plate span, .details')]
          .flatMap((card) => [card, ...card.querySelectorAll('*')])
          .filter((item) => getComputedStyle(item).textOverflow === 'ellipsis'
            || (item.children.length === 0 && /…$|\\.\\.\\.$/.test(item.textContent.trim())))
          .map((item) => item.className + ': ' + item.textContent.slice(0, 30));
        return { titled, cut };
      }"""
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.route("**/api/v1/stories/check-flow", lambda route: route.fulfill(json=story))
            for fragment, selector in (
                ("#/map", ".map-card"),
                ("#/component/0", ".level-card"),
                ("#/module/0", ".level-card"),
                ("#/explore/0", ".lens-card.center"),
                ("#/stories/check-flow", ".story-card"),
            ):
                page.goto(studio.url + fragment)
                page.locator(selector).first.wait_for()
                page.wait_for_timeout(500)
                found = page.evaluate(check)
                assert found == {"titled": 0, "cut": []}, (fragment, found)
        finally:
            browser.close()


def _top_callers(graph_body: dict, count: int = 3) -> list[int]:
    """The functions with the most distinct callers, as the Briefing ranks them (ties by index)."""
    callers: dict[int, set[int]] = {}
    for source, target, *_ in graph_body["edges"]:
        if source != target:
            callers.setdefault(target, set()).add(source)
    return sorted(callers, key=lambda symbol: (-len(callers[symbol]), symbol))[:count]


def _briefing_facts(page, graph_body: dict) -> None:
    """The numbers of the Briefing are the values of the graph route; Show opens the right place."""
    page.get_by_role("heading", name="Briefing", exact=True).wait_for()
    signals = page.locator(".briefing-signals")
    if not signals.evaluate("element => element.open"):
        signals.locator("summary").click()
    figures = [" ".join(text.split()) for text in page.locator(".figure").all_inner_texts()]
    totals = graph_body["totals"]
    assert any(
        text.startswith(str(len(graph_body["modules"]))) and "MODULES" in text.upper()
        for text in figures
    )
    resolved = f"{100 * totals['resolved'] / totals['analyzed']:.1f} %"
    assert any(text.startswith(resolved) for text in figures), figures
    assert any(
        text.upper().startswith(f"{totals['unresolved']:,}".replace(",", ""))
        or "UNKNOWN CALLS" in text.upper()
        for text in figures
    )
    hubs = _top_callers(graph_body)
    shows = page.locator(".stand", has_text="Most called").locator("a")
    assert [link.get_attribute("href") for link in shows.all()] == [
        f"#/explore/{symbol}" for symbol in hubs
    ]
    # The marks, the text and the links have no title attribute and no cut text.
    assert page.locator(".page [title]").count() == 0
    assert (
        page.evaluate(
            "[...document.querySelectorAll('.page *')].filter((item) => item.children.length === 0"
            " && /…$|[.][.][.]$/.test(item.textContent.trim())).length"
        )
        == 0
    )


@pytest.mark.browser
def test_the_briefing_shows_the_numbers_of_the_graph_and_each_show_link_opens_its_place(
    studio: Studio,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    graph_body = _grid_graph()
    answer = {"api_version": API_VERSION, "explore": "done", "graph": graph_body}
    rows = [
        {"id": "old", "title": "Old story", "steps": 3, "source": "local", "created": None},
        {
            "id": "new",
            "title": "New story",
            "steps": 8,
            "source": "repository",
            "created": "2026-11-04T10:00:00Z",
        },
    ]
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.route(
                "**/api/v1/stories",
                lambda route: route.fulfill(json={"api_version": API_VERSION, "stories": rows}),
            )
            page.route("**/api/v1/stories/*", lambda route: route.fulfill(json=_answer(_checked())))
            page.goto(studio.url + "#/overview")
            _briefing_facts(page, graph_body)
            stories = page.locator(".box", has_text="Stories")
            stories.get_by_text("New story").wait_for()
            text = " ".join(stories.inner_text().split())
            assert text.index("New story") < text.index("Old story")  # the newest first
            assert "repository" in text and "created 2026-11-04" in text and "✓ 5" in text
            # How does it start: a heuristic, the function that nobody calls and that calls most.
            start = stories.get_by_role("link", name="How does it start?")
            start.click()
            page.locator(".lens-card.center").wait_for()
            # Each Show link opens the lens or the component it names.
            page.goto(studio.url + "#/overview")
            page.locator(".briefing-signals > summary").click()
            first = page.locator(".stand", has_text="Most called").locator("a").first
            href = first.get_attribute("href")
            first.click()
            page.wait_for_url(f"**/{href}")
            page.locator(".lens-card.center").wait_for()
            # A question asked on the Briefing opens the chat panel of the Architecture.
            page.route("**/api/v1/chat", lambda route: route.fulfill(json=_ANSWER))
            page.goto(studio.url + "#/overview")
            page.get_by_role("textbox", name="Question").fill("Where does it start?")
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_url("**/#/map")
            page.get_by_role("region", name="Ask the agent").get_by_text(
                "Where does it start?"
            ).wait_for()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(800, 600), (1440, 900)])
def test_briefing_shows_six_measured_component_cards(
    studio: Studio, width: int, height: int
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    components = [[f"component-{index}", ""] for index in range(8)] + [
        ["(unowned)", "Modules without a single owning component."]
    ]
    modules = (
        [
            [f"component-0.module-{part}", f"component_0_{part}.py", 0, f"module_{part}"]
            for part in range(2)
        ]
        + [
            [f"component-{index}.module", f"component_{index}.py", index, ""]
            for index in range(1, 8)
        ]
        + [["unowned.module", "unowned.py", 8, ""]]
    )
    symbols = [_function(0, "function_0"), _function(1, "function_1")]
    symbols.extend(
        [
            [2, "Class1", 1, "class", "class Class1:", 1, 0],
            [2, "function_1", 2, "function", "def function_1():", 2, 0],
        ]
    )
    symbols.extend(_function(module, f"function_{module}") for module in range(3, 9))
    symbols.append([9, "UnownedClass", 1, "class", "class UnownedClass:", 0, 0])
    graph = {
        "components_from": "contract",
        "totals": {"analyzed": 3, "resolved": 0, "partial": 0, "unresolved": 3},
        "snapshot": _REVISION,
        "components": components,
        "modules": modules,
        "symbols": symbols,
        "edges": [],
        "unknown": [
            [2, "Class1.call()", "unresolved", 1],
            [3, "function_1()", "unresolved", 2],
            [3, "function_1()", "unresolved", 3],
        ],
    }
    answer = {"api_version": API_VERSION, "explore": "done", "graph": graph}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + "#/overview")
            cards = page.locator(".component-card")
            cards.first.wait_for()
            assert cards.count() == 6
            first_card = cards.first.bounding_box()
            assert (
                first_card is not None
                and first_card["y"] >= 0
                and first_card["y"] + first_card["height"] <= height
            )
            assert [card.locator("h3").inner_text() for card in cards.all()] == [
                "component-0",
                "component-1",
                "(unowned)",
                "component-2",
                "component-3",
                "component-4",
            ]
            assert [card.get_attribute("href") for card in cards.all()] == [
                "#/component/0",
                "#/component/1",
                "#/component/8",
                "#/component/2",
                "#/component/3",
                "#/component/4",
            ]
            assert page.get_by_text("Declared groups: contract", exact=True).is_visible()
            assert page.get_by_text("Declared by contract", exact=True).count() == 0
            assert all(
                "observed" in card.locator(".badge").get_attribute("class") for card in cards.all()
            )
            assert "2 symbols with unknown calls" in _words(cards.nth(1))
            figures = [_words(figure).upper() for figure in page.locator(".figure").all()]
            assert any(text.startswith("11 SYMBOLS") for text in figures)
            assert any(text.startswith("3 UNKNOWN CALLS") for text in figures)
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            page.get_by_role("link", name="See all in Architecture").click()
            page.get_by_role("heading", name="Map", exact=True).wait_for()
            assert page.get_by_text("Declared groups: contract", exact=True).is_visible()
            map_card = page.locator(".map-card", has_text="component-1")
            assert "1 module · 2 symbols" in _words(map_card)
            map_card.dblclick()
            page.get_by_role("heading", name="Component", exact=True).wait_for()
            if width < 1300:
                page.get_by_role("button", name="Details").click()
            page.locator(".details").get_by_text("1 module · 2 symbols", exact=True).wait_for()
            page.locator(".level-card", has_text="component_1.py").dblclick()
            page.get_by_role("heading", name="Module", exact=True).wait_for()
            if width < 1300:
                page.get_by_role("button", name="Details").click()
            page.locator(".details").get_by_text("2 symbols", exact=False).wait_for()
        finally:
            browser.close()


@pytest.mark.browser
def test_briefing_names_an_empty_graph_without_inventing_components(studio: Studio) -> None:
    graph = {
        "components_from": "layout",
        "totals": {"analyzed": 0, "resolved": 0, "partial": 0, "unresolved": 0},
        "snapshot": _REVISION,
        "components": [],
        "modules": [],
        "symbols": [],
        "edges": [],
        "unknown": [],
    }
    answer = {"api_version": API_VERSION, "explore": "done", "graph": graph}
    with _page_on(studio, answer, "#/overview") as page:
        page.get_by_role("heading", name="Briefing", exact=True).wait_for()
        assert page.get_by_text("0 of 0 · See all in Architecture").is_visible()
        assert page.get_by_text("No components found in this snapshot.", exact=True).is_visible()
        assert page.locator(".component-card").count() == 0
        figures = [_words(figure).upper() for figure in page.locator(".figure").all()]
        assert any(text.startswith("0 MODULES") for text in figures)
        assert any(text.startswith("0 SYMBOLS") for text in figures)
        assert (
            _words(page.locator(".briefing-signals > summary"))
            == "What stands out · 0 measured facts"
        )
        assert page.get_by_text(
            "No contract · no policy verdict. archkeel init drafts one.", exact=True
        ).is_visible()
        assert page.locator(".briefing-signals .box").count() == 0


@pytest.mark.browser
def test_the_briefing_of_archkeel_itself_matches_the_graph_route(archkeel_studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    cookie = login(archkeel_studio)
    response, body = request(archkeel_studio, "/api/v1/graph", cookie=cookie)
    assert response.status == 200
    graph_body = json.loads(body)["graph"]
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(60000)
            page.goto(archkeel_studio.url + "#/overview")
            _briefing_facts(page, graph_body)
            if shot := os.environ.get("BRIEFING_SHOT"):
                page.screenshot(path=shot)
        finally:
            browser.close()


def _small_graph(modules, symbols, edges) -> dict:
    """A valid graph body with components alpha and beta."""
    body = {
        "components_from": "contract",
        "totals": _TOTALS,
        "snapshot": _REVISION,
        "components": [["alpha", "Alpha."], ["beta", "Beta."]],
        "modules": modules,
        "symbols": symbols,
        "edges": edges,
        "unknown": [],
    }
    answer = {"api_version": API_VERSION, "explore": "done", "graph": body}
    Draft202012Validator({"$ref": "#/$defs/graph", "$defs": _SCHEMA["$defs"]}).validate(answer)
    return answer


def _function(module: int, name: str, line: int = 1) -> list:
    return [module, name, line, "function", f"def {name}():", 0, 0]


def _words(element) -> str:
    return " ".join(element.inner_text().split())


@contextmanager
def _page_on(studio: Studio, answer: dict, fragment: str) -> Iterator:
    """A page that shows a given graph; a crash of the page fails the test when it closes."""
    api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(10000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/v1/graph", lambda route: route.fulfill(json=answer))
            page.goto(studio.url + fragment)
            yield page
        finally:
            browser.close()
    assert errors == []


_TWO_MODULES = [["m.a", "m/a.py", 0, "a"], ["m.b", "m/b.py", 1, "b"]]


@pytest.mark.browser
def test_the_module_level_counts_every_call_site_and_keeps_the_claim(studio: Studio) -> None:
    # f calls g at two resolved sites and one partial site, and f calls its sibling h the same way.
    modules = [["m.a", "m/a.py", 0, "a"], ["m.b", "m/b.py", 1, "b"]]
    symbols = [_function(0, "f"), _function(0, "h"), _function(1, "g")]
    edges = [
        [0, target, partial, 5 + site, 3 * order + site]
        for order, target in enumerate((2, 1))
        for site, partial in enumerate((False, False, True))
    ]
    answer = _small_graph(modules, symbols, edges)
    with _page_on(studio, answer, "#/module/0") as page:
        stub = page.locator("a.lens-card.stub")
        stub.wait_for()
        assert _words(stub.locator(".meta").first) == "2 ✓ proven · 1 ✎ claim"
        page.locator(".level-card", has_text="f").first.click()
        page.locator(".level-card.pinned").wait_for()
        # A line with a claim is a claim, to the sibling and to the stub alike.
        assert page.locator("g.focus-line.claim").count() == 2
        assert page.locator("g.focus-line.proven").count() == 0


@pytest.mark.browser
def test_a_call_with_candidates_in_two_folded_modules_is_one_claim(studio: Studio) -> None:
    # 12 modules in one package: 8 show, 4 fold into a tile. One partial call names two folded ones.
    modules = [[f"alpha.p.m{k:02}", f"alpha/p/m{k:02}.py", 0, f"p.m{k:02}"] for k in range(12)]
    symbols = [_function(k, f"fn{k}") for k in range(12)]
    edges = [[0, 8, True, 3, 0], [0, 9, True, 3, 0]]
    answer = _small_graph(modules, symbols, edges)
    with _page_on(studio, answer, "#/component/0") as page:
        page.locator(".lens-card.tile").wait_for()
        page.locator(".level-card", has_text="m00").click()
        page.locator(".level-card.pinned").wait_for()
        rows = _words(page.locator(".focus-rows"))
        assert "1 ✎ claim" in rows and "2 ✎ claim" not in rows


@pytest.mark.browser
@pytest.mark.parametrize(("closing_partial", "cycle"), [(True, False), (False, True)])
def test_only_proven_calls_make_an_observed_cycle(
    studio: Studio, closing_partial: bool, cycle: bool
) -> None:
    symbols = [_function(0, "a"), _function(1, "b")]
    edges = [[0, 1, False, 3, 0], [1, 0, closing_partial, 4, 1]]
    answer = _small_graph(_TWO_MODULES, symbols, edges)
    with _page_on(studio, answer, "#/overview") as page:
        page.get_by_role("heading", name="Briefing").wait_for()
        page.locator(".briefing-signals > summary").click()
        page.locator(".stand").first.wait_for()
        text = _words(page.locator(".page"))
        assert ("Components call each other in a cycle" in text) is cycle


@pytest.mark.browser
def test_a_lens_neighbor_names_its_proof_in_words(studio: Studio) -> None:
    symbols = [_function(0, "f"), _function(1, "g", 2), _function(1, "h", 3)]
    edges = [[0, 1, False, 5, 0], [0, 2, True, 6, 1]]
    answer = _small_graph(_TWO_MODULES, symbols, edges)
    with _page_on(studio, answer, "#/explore/0") as page:
        page.locator(".lens-card.center").wait_for()
        assert _words(page.locator("a.lens-card", has_text="g")) == "g ✓ proven line 5"
        assert _words(page.locator("a.lens-card", has_text="h")) == "h ✎ claim line 6"


@pytest.mark.browser
def test_a_snapshot_without_symbols_opens_a_module(studio: Studio) -> None:
    answer = _small_graph([["m.a", "m/a.py", 0, "a"]], [], [])
    with _page_on(studio, answer, "#/module/0") as page:
        page.get_by_role("heading", name="m.a").or_(page.locator(".titlebar")).first.wait_for()
        page.get_by_text("0 symbols").first.wait_for()


@pytest.mark.browser
def test_a_function_that_the_snapshot_lacks_falls_back_to_the_start_in_title_and_page(
    studio: Studio,
) -> None:
    symbols = [_function(0, "f"), _function(1, "g")]
    answer = _small_graph(_TWO_MODULES, symbols, [[0, 1, False, 5, 0]])
    with _page_on(studio, answer, "#/explore/999") as page:
        center = page.locator(".lens-card.center b")
        center.wait_for()
        assert _words(page.locator(".titlebar")).endswith(_words(center))


@pytest.mark.browser
def test_the_map_cards_and_their_call_lists_name_the_proof_in_words(studio: Studio) -> None:
    # f calls g at one resolved and one partial site: alpha calls beta, one proven and one claim.
    symbols = [_function(0, "f"), _function(1, "g")]
    answer = _small_graph(_TWO_MODULES, symbols, [[0, 1, False, 5, 0], [0, 1, True, 6, 1]])
    with _page_on(studio, answer, "#/map") as page:
        card = page.locator("a.map-card", has_text="alpha")
        card.wait_for()
        assert "out 1 ✓ proven · 1 ✎ claim" in _words(card)
        assert "in 0 ✓ proven" in _words(card)
        card.click()
        details = page.get_by_role("complementary", name="Details")
        calls = details.locator(".box", has=page.get_by_role("heading", name="Calls", exact=True))
        assert "beta 1 ✓ proven · 1 ✎ claim" in _words(calls)
        page.locator("a.map-card", has_text="beta").click()
        called_by = details.locator(".box", has=page.get_by_role("heading", name="Called by"))
        assert "alpha 1 ✓ proven · 1 ✎ claim" in _words(called_by)


@pytest.mark.browser
def test_a_question_from_the_briefing_shows_its_answer_on_a_narrow_screen(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    reply = {**_ANSWER, "blocks": [_ANSWER["blocks"][0] | {"refs": []}], "facts": []}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 700})
            page.set_default_timeout(10000)
            page.route("**/api/v1/chat", lambda route: route.fulfill(json=reply))
            page.goto(studio.url + "#/overview")
            page.get_by_role("textbox", name="Question").fill("What does place do?")
            page.get_by_role("button", name="Ask", exact=True).click()
            page.get_by_role("heading", name="Map", exact=True).wait_for()
            # Below 1300 px the side panel starts closed; the chat the question opened must be seen.
            chat = page.get_by_role("complementary", name="Ask the agent")
            chat.get_by_text("place saves the order.").wait_for()
            assert chat.get_by_text("place saves the order.").is_visible()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("late", ["story", "failure", "list-failure"])
def test_a_late_answer_of_another_route_never_replaces_the_story_on_screen(
    studio: Studio, late: str
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    held: list = []
    other = _checked()
    other["story"]["title"] = "Story A"
    mine = _checked()
    mine["story"]["title"] = "Story B"
    start = "#/stories" if late == "list-failure" else "#/stories/story-a"
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(10000)
            # The first route waits: the test answers it after the reader has moved on.
            page.route("**/api/v1/stories", lambda route: held.append(route))
            page.route("**/api/v1/stories/story-a", lambda route: held.append(route))
            page.route(
                "**/api/v1/stories/story-b",
                lambda route: route.fulfill(json=_answer(mine, id="story-b")),
            )
            page.goto(studio.url + start)
            while not held:
                page.wait_for_timeout(50)
            page.evaluate("location.hash = '#/stories/story-b'")
            page.get_by_role("heading", name="Story B").wait_for()
            if late == "story":
                held[0].fulfill(json=_answer(other, id="story-a"))
            else:
                held[0].fulfill(status=500, body="the check of this story failed")
            page.wait_for_timeout(500)
            assert page.get_by_role("heading", name="Story B").is_visible()
            assert page.get_by_role("heading", name="Story A").count() == 0
            assert page.get_by_role("alert").count() == 0
        finally:
            browser.close()
