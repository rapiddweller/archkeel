# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-287: the Explorer draws a checked view; a claim never looks like proof (#786)."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from browser_report_support import _browser_page
from test_cli_view import EXAMPLE, _snapshot
from test_uml_rendering import _wait_for_layout

from archkeel.cli import main

_URL = "http://report.test/"
_REPORT = "architecture.report.html"
# The example plus an unmarked made-up edge, an edge the snapshot cannot decide and a made-up node.
_EXTRA_NODES = ["shop.render.text", "shop.app.payments"]
_EXTRA_EDGES = [
    {"source": "shop.render.text", "target": "shop.app.orders", "kind": "imports"},
    {"source": "shop.cli.main", "target": "shop.store.repository", "kind": "calls"},
    {"source": "shop.cli.main", "target": "shop.app.payments", "kind": "imports"},
]


@pytest.fixture(scope="module")
def pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    tmp_path = tmp_path_factory.mktemp("flow")
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(_snapshot(tmp_path / "repo"))
    spec = json.loads(EXAMPLE.read_text())
    spec["nodes"] += _EXTRA_NODES
    spec["edges"] += _EXTRA_EDGES
    view = tmp_path / "view.json"
    view.write_text(json.dumps(spec))
    output = tmp_path / "out"
    # A made-up node is missing: exit 1, and the page still draws it.
    assert (
        main(["view", "show", str(view), "--snapshot", str(snapshot), "--output", str(output)]) == 1
    )
    return {path.name: path.read_text() for path in output.glob("*.html")}


def _open(pages, query="", width=800, height=600, requests=None):
    api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    playwright, browser, page = _browser_page(api, "", width=width, height=height, errors=errors)

    def serve(route):
        url = route.request.url
        if requests is not None:
            requests.append(url)
        if not url.startswith(_URL):
            route.abort()
            return
        name = url.split("?")[0].rsplit("/", 1)[1]
        route.fulfill(body=pages[name], content_type="text/html")

    page.route("**/*", serve)
    page.goto(_URL + _REPORT + query)
    _wait_for_layout(page)
    page.errors = errors
    return playwright, browser, page


def _close(playwright, browser):
    browser.close()
    playwright.stop()


def _route(page):
    return {key: values[0] for key, values in parse_qs(urlparse(page.url).query).items()}


def _step(page, number):
    return page.get_by_role("button", name=re.compile(rf"^Step {number}: "))


def _status(page, layer, status):
    return page.locator(f".{layer} [data-view-status='{status}']")


@pytest.mark.browser
def test_a_view_opens_with_each_step_edge_and_mark(pages):
    playwright, browser, page = _open(pages)
    try:
        assert page.locator(".flow[data-view='checked']").count() == 1
        for number, node in enumerate(
            ["shop.cli.main", "shop.app.orders", "shop.store.repository", "shop.store.codec"], 1
        ):
            assert node in _step(page, number).get_attribute("aria-label")
        summary = page.locator(".atlas-summary").inner_text()
        assert "structure, not runtime order" in summary
        # Each status shows as text with its icon, never by colour alone.
        labels = page.locator(".flow-edges .view-edge-label").all_text_contents()
        assert any("✓ proven" in text and "calls" in text for text in labels)
        assert any("✎ author claim" in text for text in labels)
        assert any("? unknown" in text for text in labels)
        assert any("✕ not in the code" in text for text in labels)
        payments = page.get_by_role("button", name=re.compile(r"^shop\.app\.payments, "))
        assert "not in the code" in payments.text_content()
        # Author notes carry an Author mark on the card.
        assert "Author" in _step(page, 1).text_content()
        assert "PASS" not in page.locator(".flow-layout").inner_text()
        assert page.errors == []
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_a_made_up_edge_is_a_claim_or_not_in_the_code_never_proven(pages):
    playwright, browser, page = _open(pages)
    try:
        claims = _status(page, "flow-edges", "claim")
        assert claims.count() == 2  # the claimed edge and the claimed step 3
        for index in range(claims.count()):
            claim = claims.nth(index)
            assert "view-proven" not in claim.get_attribute("class")
            dash = claim.locator(".line").evaluate(
                "(line) => getComputedStyle(line).strokeDasharray"
            )
            assert dash not in ("none", "")
        made_up = page.locator(
            ".flow-edges [data-view-status='missing'][data-view-source='shop.render.text']"
        )
        assert made_up.count() == 1 and "not in the code" in made_up.text_content()
        proven = _status(page, "flow-edges", "proven")
        assert all(
            "claim" not in text and "author" not in text for text in proven.all_text_contents()
        )
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_inspector_shows_kind_location_ids_and_snapshot(pages):
    playwright, browser, page = _open(pages)
    try:
        _step(page, 2).click()
        inspector = page.locator(".flow-inspector")
        assert inspector.is_visible()
        text = inspector.inner_text()
        assert "calls" in text and "proven" in text
        assert re.search(r"shop/cli/main\.py:\d+", text)
        assert re.search(r"\bCALL-[0-9a-f]+", text) and re.search(r"\bEVD-[0-9a-f]+", text)
        assert "Source digest" in text and "Contract digest" in text
        assert "structure, not runtime order" in text
        assert "PASS" not in text
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_keyboard_reaches_each_step_enter_opens_and_escape_closes(pages):
    playwright, browser, page = _open(pages)
    try:
        _step(page, 1).focus()
        for number in (2, 3, 4):
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.getAttribute('aria-label')").startswith(
                f"Step {number}: "
            )
        page.keyboard.press("Enter")
        inspector = page.locator(".flow-inspector")
        assert inspector.is_visible() and "step 4 of 4" in inspector.inner_text().lower()
        assert page.evaluate(
            "document.querySelector('.flow-inspector').contains(document.activeElement)"
        )
        page.keyboard.press("Escape")
        assert not inspector.is_visible()
        assert page.evaluate("document.activeElement.getAttribute('aria-label')").startswith(
            "Step 4: "
        )
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_url_opens_the_same_picture(pages):
    playwright, browser, page = _open(pages)
    try:
        _step(page, 3).click()
        route = _route(page)
        assert (route["flow"], route["step"]) == ("1", "3")
        query = "?" + urlparse(page.url).query
    finally:
        _close(playwright, browser)
    playwright, browser, page = _open(pages, query)
    try:
        assert page.locator(".flow[data-view='checked']").count() == 1
        assert "step 3 of 4" in page.locator(".flow-inspector").inner_text().lower()
        assert _step(page, 3).get_attribute("aria-pressed") == "true"
        page.get_by_role("button", name="As-Is", exact=True).click()
        _wait_for_layout(page)
        assert page.locator(".flow[data-view='diagram']").count() == 1 and "flow" not in _route(
            page
        )
        page.get_by_role("button", name="Checked flow", exact=True).click()
        assert page.locator(".flow[data-view='checked']").count() == 1
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_text_is_readable_and_unclipped_at_800x600(pages):
    playwright, browser, page = _open(pages)
    try:
        sizes = page.evaluate(
            """() => [...document.querySelectorAll('.flow-nodes text, .flow-edges text')]
            .filter((text) => text.getBoundingClientRect().width > 0)
            .map((text) => parseFloat(getComputedStyle(text).fontSize) * text.getScreenCTM().a)"""
        )
        assert sizes and min(sizes) >= 11
        clipped = page.evaluate(
            """() => [...document.querySelectorAll('.flow-nodes .node')].flatMap((card) => {
              const box = card.querySelector('.card').getBoundingClientRect();
              return [...card.querySelectorAll('text')].filter((text) => {
                const r = text.getBoundingClientRect();
                return r.width && (r.left < box.left - 1 || r.right > box.right + 1);
              }).map((text) => text.textContent);
            })"""
        )
        assert clipped == []
        summary = page.locator(".atlas-summary")
        assert summary.evaluate("(element) => element.scrollWidth <= element.clientWidth + 1")
    finally:
        _close(playwright, browser)


@pytest.mark.browser
def test_the_page_works_offline(pages):
    requests: list[str] = []
    playwright, browser, page = _open(pages, requests=requests)
    try:
        assert [url for url in requests if not url.startswith(_URL)] == []
        assert page.errors == []
        assert _step(page, 1).count() == 1
    finally:
        _close(playwright, browser)
