# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A reader reaches a deep component in one step and reads its diagram at 800x600 (#782, AD-286)."""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from browser_report_support import _browser_page
from test_architecture_demo import _prepare_repo
from test_uml_rendering import _wait_for_layout

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.render.html import render_architecture_html

# io / data_sources / loaders / rdbms: four levels, each mounted with `inside`.
_PATH = ("io", "data_sources", "loaders", "rdbms")
_SIBLINGS = 10
_RDBMS = "io:data_sources:loaders:io-data_sources-loaders-rdbms"
_DATA_SOURCES = "io:io-data_sources"
_URL = "http://report.test/architecture.report.html"


def _component(parts, inside=None):
    dotted = ".".join(parts)
    item = {
        "id": "-".join(parts),
        "label": parts[-1],
        "role": "component",
        "packages": [f"sample.{dotted}"],
        "namespace": f"sample.{dotted}",
        "responsibilities": [f"Own {parts[-1]}."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
    }
    if inside:
        item["inside"] = inside
    return item


def _contract(components):
    return {"schema_version": "2.2.0", "components": components, "rules": []}


def _deep_report_html(tmp_path):
    files = {"sample/__init__.py": "", "sample/io/__init__.py": "", "docs/target.md": "target\n"}
    files["architecture-contract.json"] = json.dumps(
        _contract([_component(_PATH[:1], "contracts/io.json")])
    )
    for depth in range(1, len(_PATH)):
        parent = _PATH[:depth]
        mounted = depth + 1 < len(_PATH)
        children = [
            _component(
                _PATH[: depth + 1],
                f"contracts/{'-'.join(_PATH[: depth + 1])}.json" if mounted else None,
            ),
            *(_component((*parent, f"sib{index:02d}")) for index in range(_SIBLINGS)),
        ]
        files[f"contracts/{'-'.join(parent)}.json"] = json.dumps(_contract(children))
        for child in children:
            package = child["packages"][0].replace(".", "/")
            files[f"{package}/__init__.py"] = ""
            files[f"{package}/m0.py"] = "VALUE = 1\n"
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    return render_architecture_html(
        result, encoded, repository="Sample", architecture_href="architecture.json"
    ).decode()


@pytest.fixture(scope="module")
def deep_html(tmp_path_factory):
    return _deep_report_html(tmp_path_factory.mktemp("deep"))


def _open(deep_html, query=""):
    """Serve the report from an http origin: only file and http pages write the route to the URL."""
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, deep_html, width=800, height=600)
    page.route(
        "http://report.test/**",
        lambda route: route.fulfill(body=deep_html, content_type="text/html"),
    )
    page.goto(_URL + query)
    _wait_for_layout(page)
    return playwright, browser, page


def _route(page):
    query = parse_qs(urlparse(page.url).query)
    return {key: values[0] for key, values in query.items()}


def _search(page, text):
    page.get_by_role("button", name="Search", exact=True).click()
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    _wait_for_layout(page)


def _text_heights(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('.flow-nodes text')]
        .filter((text) => text.getBoundingClientRect().width > 0)
        .map((text) => text.getBoundingClientRect().height)"""
    )


@pytest.mark.browser
@pytest.mark.parametrize(
    "button,view", [("As-Is", "diagram"), ("Target", "target"), ("Diff", "diff")]
)
def test_search_opens_a_deep_component_with_the_current_view_in_one_action(deep_html, button, view):
    playwright, browser, page = _open(deep_html)
    try:
        page.get_by_role("button", name=button, exact=True).click()
        _search(page, "rdbms")
        route = _route(page)
        assert (route["scope"], route["view"]) == (_RDBMS, view)
        assert page.locator("#flow-heading").inner_text().endswith("rdbms")
        assert page.locator(f'.flow[data-view="{view}"]').count() == 1
        crumb = page.locator(".flow-breadcrumb button").last
        assert crumb.inner_text() == "rdbms"
        bar, last = page.locator(".flow-breadcrumb").bounding_box(), crumb.bounding_box()
        assert last["x"] + last["width"] <= bar["x"] + bar["width"] + 1
        # Focus lands on a card, or on the current crumb when the level draws no card.
        assert page.evaluate(
            "document.activeElement.closest('.flow-nodes') !== null"
            " || document.activeElement.matches('.flow-breadcrumb > button:last-child')"
        )
        assert abs(page.locator(".flow").bounding_box()["y"]) <= 1
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_search_moves_keyboard_focus_into_the_opened_diagram(deep_html):
    playwright, browser, page = _open(deep_html)
    try:
        _search(page, "loaders")
        assert page.evaluate("document.activeElement.closest('.flow-nodes') !== null")
        assert page.evaluate("document.activeElement.getAttribute('tabindex')") == "0"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_search_accepts_the_full_component_path(deep_html):
    playwright, browser, page = _open(deep_html)
    try:
        _search(page, "io/data_sources/loaders/rdbms")
        assert _route(page)["scope"] == _RDBMS
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
@pytest.mark.parametrize("view", ["diagram", "target"])
def test_fit_keeps_card_text_readable_and_scrolls_a_large_level_at_800x600(deep_html, view):
    playwright, browser, page = _open(deep_html, f"?scope={_DATA_SOURCES}&view={view}")
    try:
        assert page.locator(".flow-nodes [data-uml-kind='component']").count() == _SIBLINGS + 1
        # Fit has two entries; the Shift+C button hides under 900 px.
        for fit in (
            lambda: page.get_by_role("button", name="Fit to window").click(),
            lambda: page.keyboard.press("Shift+C"),
        ):
            fit()
            heights = _text_heights(page)
            assert heights and min(heights) >= 11, min(heights)
        canvas = page.locator(".flow-canvas")
        assert canvas.evaluate("(node) => node.scrollHeight > node.clientHeight")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_details_start_closed_and_a_selection_opens_them(deep_html):
    playwright, browser, page = _open(deep_html)
    try:
        toggle = page.locator("[data-flow-details-toggle]")
        assert page.locator(".flow").get_attribute("data-details-open") == "false"
        assert toggle.get_attribute("aria-expanded") == "false"
        assert not page.locator(".flow-inspector").is_visible()
        assert page.locator(".flow-canvas").bounding_box()["width"] > 600
        page.locator('.flow-nodes [data-uml-kind="component"]').first.click()
        assert toggle.get_attribute("aria-expanded") == "true"
        assert page.locator(".flow-inspector").is_visible()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_a_selection_in_the_url_opens_details(deep_html):
    playwright, browser, page = _open(deep_html, f"?scope=io&selected={_DATA_SOURCES}")
    try:
        assert page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") == "true"
        assert page.locator(".flow-inspector").is_visible()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_breadcrumbs_jump_to_any_level_by_pointer_and_keyboard(deep_html):
    playwright, browser, page = _open(deep_html, f"?scope={_RDBMS}")
    try:
        crumbs = page.locator(".flow-breadcrumb button")
        assert crumbs.all_inner_texts() == ["Sample", "io", "data_sources", "loaders", "rdbms"]
        crumbs.nth(1).click()
        _wait_for_layout(page)
        assert _route(page)["scope"] == "io"
        assert crumbs.all_inner_texts() == ["Sample", "io"]
        page.locator(".flow-breadcrumb button").first.focus()
        page.keyboard.press("Enter")
        _wait_for_layout(page)
        assert "scope" not in _route(page)
        assert crumbs.all_inner_texts() == ["Sample"]
    finally:
        browser.close()
        playwright.stop()
