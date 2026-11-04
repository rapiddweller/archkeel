# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the Studio shell loads, navigates by keyboard and asks only its own server.

Run these tests with `-m browser`; they need the `playwright` package and Chromium.
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator
from test_explore import _repository
from test_studio import _SCHEMA, _start, _stop, explore, login, request

from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.studio.api import API_VERSION
from archkeel.studio.server import Studio

_LEGEND = ("Observed = code evidence", "Claim = agent hypothesis", "Target = architect decision")
# Data and blob URLs are page content, not requests to a host.
_LOCAL_SCHEMES = {"data", "blob", "about"}


_ENVIRONMENT = {name: os.environ.get(name) for name in ("XDG_CACHE_HOME", "HOME")}


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Studio]:
    tmp_path = tmp_path_factory.mktemp("studio")
    # The cache folder goes to the server only: Playwright on Linux reads XDG_CACHE_HOME.
    server = _start(_repository(tmp_path / "shop"), tmp_path / "cache")
    assert explore(server, login(server))["explore"] == "done"
    yield server
    _stop(server)


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
    assert page.get_by_text("components: observed package layout", exact=True).is_visible()
    assert page.get_by_text("✓ proven = resolved call", exact=True).first.is_visible()
    assert page.get_by_text("✎ claim = partly resolved call", exact=True).first.is_visible()
    assert page.get_by_text("? unknown = no target found", exact=True).first.is_visible()
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
    page.locator(".map-card", has_text="app").click()
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
    stubs.filter(has_text="store").click()
    page.get_by_role("navigation", name="Location").locator("b", has_text="store").wait_for()
    assert _where(page) == (["Architecture"], "store")
    page.keyboard.press("Escape")
    page.get_by_role("navigation", name="Location").locator("b", has_text="Architecture").wait_for()
    assert _where(page) == ([], "Architecture")
    assert transition() == "out"
    page.locator(".map-card", has_text="app").click()
    page.locator(".level-card", has_text="orders.py").click()
    page.wait_for_url("**/#/module/*")
    page.get_by_role("heading", name="Module", exact=True).wait_for()
    assert _where(page) == (["Architecture", "app"], "orders.py")
    _no_overflow(page)
    assert "Up to app" in page.locator("a.up").text_content()
    page.locator(".level-card", has_text="place").click()
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
    page.locator(".map-card", has_text="app").click()
    page.locator(".level-card", has_text="orders.py").click()
    page.locator(".level-card", has_text="place").click()
    page.locator(".lens-card.center").wait_for()
    page.get_by_role("navigation", name="Location").get_by_role("link", name="orders.py").click()
    page.wait_for_url("**/#/module/*")
    page.locator(".level-card", has_text="place").click()
    page.locator(".lens-card.center").wait_for()


def _check_the_lens(page, width: int, height: int) -> None:
    center = page.locator(".lens-card.center")
    center.wait_for()
    assert center.locator("b").inner_text() == "place"
    # The callee `save` proves its call with a glyph and a word. A module-level call is no edge.
    callee = page.locator("a.lens-card.proven", has_text="save")
    assert callee.inner_text().replace("\n", " ").startswith("save")
    assert "✓ proven" in callee.inner_text()
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
            page.get_by_role("link", name="Overview", exact=True).click()
            page.get_by_role("heading", name="Understand the codebase").wait_for()
            for text in (*_LEGEND, "Contract: NOT CONFIGURED", "As-Is / Observed"):
                assert page.get_by_text(text, exact=True).is_visible(), text
            assert page.get_by_text("Target unavailable", exact=True).is_visible()
            background = "getComputedStyle(document.body).backgroundColor"
            assert page.evaluate(background) == "rgb(10, 18, 24)"
            contract = page.get_by_text("Contract: NOT CONFIGURED", exact=True)
            assert contract.bounding_box()["height"] < 24, "the contract state wraps"
            page.get_by_role("link", name="Open the Map").click()
            _check_the_map(page, width)
            _check_the_levels(page, width, height)
            _check_the_lens(page, width, height)
            page.screenshot(path=tmp_path / f"lens-{width}.png")

            page.get_by_role("link", name="Open the static report").focus()
            page.keyboard.press("Enter")
            assert urlsplit(page.url).fragment == "/report"
            _check_the_embedded_explorer(page, width, height)
            page.screenshot(path=tmp_path / f"report-{width}.png")

            for name, fragment, heading in (
                ("Impact", "/impact", "Change impact"),
                ("Target / Diff", "/target", "Target and diff"),
            ):
                page.get_by_role("link", name=name, exact=True).click()
                assert urlsplit(page.url).fragment == fragment
                page.get_by_role("heading", name=heading).wait_for()
                assert page.get_by_text("Not built in Studio yet.").is_visible(), name
            page.get_by_role("link", name="Overview", exact=True).click()
            page.locator('nav a[aria-current="page"]', has_text="Overview").wait_for()
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


_MIXED = {
    "components_from": "contract",
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
            page.get_by_text("components: declared by the contract", exact=True).wait_for()
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
}


def _lens(page, studio: Studio) -> None:
    page.goto(studio.url)
    page.locator(".map-card", has_text="app").click()
    page.locator(".level-card", has_text="orders.py").click()
    page.locator(".level-card", has_text="place").click()
    page.locator(".lens-card.center").wait_for()


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
            assert chat.get_by_role("button").filter(has_text="?").count() == 4  # quick questions
            chat.get_by_role("textbox", name="Question").fill("What does place do?")
            chat.get_by_role("button", name="Ask", exact=True).click()
            chat.get_by_text("CLAIM", exact=False).first.wait_for()
            assert seen[0]["body"] == {"question": "What does place do?", "context": _PLACE}
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
            assert "1 reference of the agent dropped" in flat(chat)
            assert chat.get_by_text("Agent: claude").is_visible()
            # "Pin to story" shows the draft of the trace and writes nothing.
            proposal.get_by_role("button", name="Pin to story").click()
            proposal.locator("pre.draft").wait_for()
            assert '"schema_version": "1.2.0"' in proposal.locator("pre.draft").inner_text()
            # A ref opens the lens at that function; the conversation stays.
            claim.get_by_role("link", name="save").click()
            page.locator(".lens-card.center", has_text="save").wait_for()
            assert page.get_by_role("region", name="Ask the agent").is_visible() is False
            page.get_by_role("button", name="Ask", exact=True).click()
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


def _checked(**changes) -> dict:
    """The checked `check` flow, plus a claim with 58 candidates and a Redis touchpoint."""
    checked = json.loads(json.dumps(_CHECKED))
    story = checked["story"]
    story["steps"][2]["external"] = [
        {"system": "redis", "touched": True, "direction": "reads", "evidence": []}
    ]
    story["verdict"]["systems"] = ["redis"]
    checked["steps"][5]["evidence"] = [{"file": "src/archkeel/x.py", "line": 7, "candidates": 58}]
    return checked | changes


@pytest.mark.browser
def test_a_story_plays_and_a_claim_never_reads_as_proven(studio: Studio) -> None:
    api = pytest.importorskip("playwright.sync_api")
    requests: list[str] = []
    row = {"id": "check-flow", "title": _CHECKED["story"]["title"], "steps": len(_CHECKED["steps"])}
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("request", lambda item: requests.append(item.url))
            page.route(
                "**/api/v1/stories",
                lambda route: route.fulfill(json={"api_version": API_VERSION, "stories": [row]}),
            )
            page.route(
                "**/api/v1/stories/check-flow",
                lambda route: route.fulfill(
                    json={"api_version": API_VERSION, "id": "check-flow", "checked": _checked()}
                ),
            )
            page.goto(studio.url)
            page.get_by_role("link", name="Stories", exact=True).click()
            page.get_by_role("link", name=_CHECKED["story"]["title"]).click()
            page.get_by_role("heading", name=row["title"]).wait_for()
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
            # The end of the name that fits; the panel and the tooltip have the full name.
            assert card.locator("b").inner_text() == "collect_response"
            assert card.get_attribute("title") == _CHECKED["story"]["steps"][4]["node"]
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
                lambda route: route.fulfill(
                    json={"api_version": API_VERSION, "id": "check-flow", "checked": _checked()}
                ),
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
    folder = studio.workspace.stories.folder  # type: ignore[union-attr]
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


_LONG = "a_component_with_a_very_long_name_that_keeps_going"
_STRESS = {
    "components_from": "contract",
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
    story = {"api_version": API_VERSION, "id": "check-flow", "checked": _checked()}
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
            # The story card shows the whole dotted end of a name that fits, and a cut only if it does not.
            names = page.locator(".story-card b").all_inner_texts()
            assert "check.run.observe_revision" in names  # more than the last part, as it fits
            assert not any(
                "…" in name for name in names
            )  # a cut only when the last part is too long
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
