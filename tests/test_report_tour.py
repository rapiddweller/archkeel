# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-289: the Explorer plays a tour; author text and measured facts stay apart."""

import json
import re
from urllib.parse import urlparse

import pytest
from test_cli_view import TOUR, _snapshot
from test_report_checked_flow import _URL, _close, _open, _route
from test_uml_rendering import _wait_for_layout

from archkeel.cli import main

# The example tour plus a stop on a package: the snapshot cannot decide that node.
_UNKNOWN = "shop.render"


@pytest.fixture(scope="module")
def pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    tmp_path = tmp_path_factory.mktemp("tour")
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(_snapshot(tmp_path / "repo"))
    spec = json.loads(TOUR.read_text())
    spec["nodes"].append(_UNKNOWN)
    spec["stops"].append({"node": _UNKNOWN, "title": "The text output", "note": "Author guess."})
    view = tmp_path / "view.json"
    view.write_text(json.dumps(spec))
    output = tmp_path / "out"
    arguments = ["view", "show", str(view), "--snapshot", str(snapshot), "--output", str(output)]
    assert main(arguments) == 0
    return {path.name: path.read_text() for path in output.glob("*.html")}


def _panel(page):
    return page.locator(".flow-inspector")


def _counter(page):
    return page.locator(".tour-count").inner_text()


@pytest.mark.browser
def test_a_page_with_stops_opens_at_the_first_stop(pages):
    playwright, browser, page = _open(pages)
    try:
        assert page.locator(".flow[data-view='checked'][data-tour='true']").count() == 1
        assert _route(page)["tour"] == "1"
        assert _counter(page) == "Stop 1 of 5"
        assert _panel(page).locator("h2").inner_text() == "Start here"
        assert page.get_by_role("button", name="Tour", exact=True).get_attribute(
            "aria-pressed"
        ) == ("true")
        current = page.locator(".flow-nodes .tour-current")
        assert current.count() == 1 and "shop.cli.main" in current.get_attribute("aria-label")
        assert page.errors == []
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_author_block_and_the_measured_block_are_apart(pages):
    playwright, browser, page = _open(pages)
    try:
        author = _panel(page).locator(".tour-author")
        measured = _panel(page).locator(".tour-measured")
        assert author.count() == 1 and measured.count() == 1
        note = "main reads the arguments"
        assert note in author.inner_text() and "✎" in author.inner_text()
        assert note not in measured.inner_text()
        assert not author.evaluate("(a) => a.contains(document.querySelector('.tour-measured'))")
        text = measured.inner_text()
        assert "observed" in text and re.search(r"\bIMP-[0-9a-f]+", text)
        assert "Imports out" in text and "Imports in" in text
        assert "PASS" not in _panel(page).inner_text()
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_next_and_previous_move_and_stop_at_the_ends(pages):
    playwright, browser, page = _open(pages)
    try:
        previous = page.get_by_role("button", name="Previous stop")
        following = page.get_by_role("button", name="Next stop")
        assert previous.is_disabled()
        following.click()
        assert _counter(page) == "Stop 2 of 5" and _route(page)["tour"] == "2"
        assert "modules" in _panel(page).locator(".tour-measured").inner_text().lower()
        page.get_by_role("button", name="Previous stop").click()
        assert _counter(page) == "Stop 1 of 5"
        for _ in range(4):
            page.get_by_role("button", name="Next stop").click()
        assert _counter(page) == "Stop 5 of 5"
        assert page.get_by_role("button", name="Next stop").is_disabled()
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_arrow_keys_move_and_escape_leaves_the_tour(pages):
    playwright, browser, page = _open(pages)
    try:
        page.get_by_role("button", name="Next stop").focus()
        page.keyboard.press("Enter")
        assert _counter(page) == "Stop 2 of 5"
        # Focus stays on the control, so the next key press moves again.
        assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Next stop"
        page.keyboard.press("ArrowRight")
        assert _counter(page) == "Stop 3 of 5"
        page.keyboard.press("ArrowLeft")
        assert _counter(page) == "Stop 2 of 5"
        page.keyboard.press("Escape")
        assert page.locator(".flow[data-tour='true']").count() == 0
        assert page.locator(".flow[data-view='checked']").count() == 1
        route = _route(page)
        assert route["flow"] == "1" and "tour" not in route
        assert page.evaluate("document.activeElement.textContent") == "Tour"
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_url_round_trips_a_stop_and_the_flow_stays_reachable(pages):
    playwright, browser, page = _open(pages, "?tour=3")
    try:
        assert _counter(page) == "Stop 3 of 5"
        assert "shop.app.orders" in page.locator(".flow-nodes .tour-current").get_attribute(
            "aria-label"
        )
        query = "?" + urlparse(page.url).query
    finally:
        _close(playwright, browser)
    playwright, browser, page = _open(pages, query)
    try:
        assert _counter(page) == "Stop 3 of 5"
        page.get_by_role("button", name="Checked flow", exact=True).click()
        assert page.locator(".flow[data-tour='true']").count() == 0 and "tour" not in _route(page)
        page.go_back()
        _wait_for_layout(page)
        assert _counter(page) == "Stop 3 of 5"
    finally:
        _close(playwright, browser)
    playwright, browser, page = _open(pages, "?flow=1")
    try:
        assert page.locator(".flow[data-tour='true']").count() == 0
        assert page.locator(".flow[data-view='checked']").count() == 1
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_a_stop_on_an_unknown_node_shows_unknown_and_no_fact(pages):
    playwright, browser, page = _open(pages, "?tour=5")
    try:
        measured = _panel(page).locator(".tour-measured").inner_text()
        assert "? unknown" in measured and "a package" in measured
        assert "Imports out" not in measured and "IMP-" not in measured
        assert "Author guess." in _panel(page).locator(".tour-author").inner_text()
    finally:
        _close(playwright, browser)


@pytest.mark.browser
@pytest.mark.parametrize("size", [(800, 600), (1440, 900)], ids=["800x600", "1440x900"])
def test_the_stop_is_centred_and_the_panel_reads_unclipped(pages, size):
    playwright, browser, page = _open(pages, "?tour=4", width=size[0], height=size[1])
    try:
        card = page.locator(".flow-nodes .tour-current .card").bounding_box()
        canvas = page.locator(".flow-canvas").bounding_box()
        assert card and canvas
        middle = card["y"] + card["height"] / 2
        assert canvas["y"] <= middle <= canvas["y"] + canvas["height"]
        assert canvas["x"] <= card["x"] + card["width"] / 2 <= canvas["x"] + canvas["width"]
        panel = _panel(page)
        assert panel.is_visible() and page.locator(".tour-count").is_visible()
        assert panel.evaluate("(p) => p.scrollWidth <= p.clientWidth + 1")
        nav = page.locator(".tour-nav").bounding_box()
        box = panel.bounding_box()
        assert (
            nav
            and box
            and nav["x"] >= box["x"]
            and nav["x"] + nav["width"] <= box["x"] + box["width"] + 1
        )
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_tour_works_offline(pages):
    requests: list[str] = []
    playwright, browser, page = _open(pages, requests=requests)
    try:
        page.get_by_role("button", name="Next stop").click()
        assert [url for url in requests if not url.startswith(_URL)] == []
        assert page.errors == []
    finally:
        _close(playwright, browser)
