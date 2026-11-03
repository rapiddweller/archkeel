# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A reader reaches a deep component in one step and reads its diagram at 800x600 (#782, AD-286)."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from browser_report_support import _browser_page
from test_architecture_demo import _prepare_repo
from test_uml_rendering import _wait_for_layout

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.render.html import render_architecture_details, render_architecture_html

# io / data_sources / loaders / rdbms: four levels, each mounted with `inside`.
_PATH = ("io", "data_sources", "loaders", "rdbms")
_SIBLINGS = 10
_RDBMS = "io:data_sources:loaders:io-data_sources-loaders-rdbms"
_DATA_SOURCES = "io:io-data_sources"
_URL = "http://report.test/"
_REPORT = "architecture.report.html"
_DETAIL = "architecture.detail.html"


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


def _deep_pages(tmp_path):
    files = {"sample/__init__.py": "", "sample/io/__init__.py": "", "docs/target.md": "target\n"}
    files["architecture-contract.json"] = json.dumps(
        _contract(
            [
                _component(_PATH[:1], "contracts/io.json"),
                _component(("render",), "contracts/render.json"),
            ]
        )
    )
    # A child on the package of its parent shares its source path; the parent must rank first.
    files["contracts/render.json"] = json.dumps(
        _contract([{**_component(("render",)), "id": "render-atlas", "label": "atlas"}])
    )
    files["sample/render/__init__.py"] = ""
    files["sample/render/m0.py"] = "VALUE = 1\n"
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
    # One import between two siblings gives the loaders level an edge and a matrix cell.
    files["sample/io/data_sources/loaders/sib02/m0.py"] = (
        "import sample.io.data_sources.loaders.sib03.m0\n"
    )
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    page = render_architecture_html(
        result, encoded, repository="Sample", architecture_href="architecture.json"
    ).decode()
    details = render_architecture_details(
        result, encoded, repository="Sample", architecture_href="architecture.json"
    )[_DETAIL].decode()
    return {_REPORT: page, _DETAIL: details}


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    return _deep_pages(tmp_path_factory.mktemp("deep"))


def _payload(pages):
    match = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', pages[_REPORT], re.S
    )
    return json.loads(match.group(1))["atlas"]


def _open(pages, query="", name=_REPORT):
    """Serve the pages from an http origin: only file and http pages write the route to the URL."""
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, pages[_REPORT], width=800, height=600)
    page.route(
        "http://report.test/**",
        lambda route: route.fulfill(
            body=pages[route.request.url.split("?")[0].rsplit("/", 1)[1]],
            content_type="text/html",
        ),
    )
    page.goto(_URL + name + query)
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


def _font_sizes(page):
    """Effective font size in screen px: computed font size times the SVG scale."""
    return page.evaluate(
        """() => [...document.querySelectorAll('.flow-nodes text')]
        .filter((text) => text.getBoundingClientRect().width > 0)
        .map((text) => parseFloat(getComputedStyle(text).fontSize) * text.getScreenCTM().a)"""
    )


@pytest.mark.browser
@pytest.mark.parametrize(
    "button,view", [("As-Is", "diagram"), ("Target", "target"), ("Diff", "diff")]
)
def test_search_opens_a_deep_component_with_the_current_view_in_one_action(pages, button, view):
    playwright, browser, page = _open(pages)
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
def test_search_moves_keyboard_focus_into_the_opened_diagram(pages):
    playwright, browser, page = _open(pages)
    try:
        _search(page, "loaders")
        assert page.evaluate("document.activeElement.closest('.flow-nodes') !== null")
        assert page.evaluate("document.activeElement.getAttribute('tabindex')") == "0"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_drilling_in_by_enter_moves_keyboard_focus_into_the_new_level(pages):
    playwright, browser, page = _open(pages, "?scope=io")
    try:
        card = page.locator(f'.flow-nodes [data-uml-id="{_DATA_SOURCES}"]')
        card.focus()
        card.press("Enter")
        _wait_for_layout(page)
        assert _route(page)["scope"] == _DATA_SOURCES
        assert page.evaluate("document.activeElement.closest('.flow-nodes') !== null")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_search_accepts_the_source_path_and_ranks_the_component_before_its_children(pages):
    component = next(
        item for item in _payload(pages)["components"] if item["id"] == "io:io-data_sources"
    )
    playwright, browser, page = _open(pages)
    try:
        _search(page, component["path"])
        assert _route(page)["scope"] == "io:io-data_sources"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_search_by_a_source_path_shared_with_a_child_opens_the_parent(pages):
    components = {item["label"]: item for item in _payload(pages)["components"]}
    assert components["render"]["path"] == components["atlas"]["path"]
    playwright, browser, page = _open(pages)
    try:
        _search(page, components["render"]["path"])
        assert _route(page)["scope"] == "render"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_search_accepts_the_full_component_path(pages):
    playwright, browser, page = _open(pages)
    try:
        _search(page, "io/data_sources/loaders/rdbms")
        assert _route(page)["scope"] == _RDBMS
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
@pytest.mark.parametrize("view", ["diagram", "target"])
def test_reset_zoom_keeps_card_font_at_11px_and_scrolls_a_large_level_at_800x600(pages, view):
    playwright, browser, page = _open(pages, f"?scope={_DATA_SOURCES}&view={view}")
    try:
        assert page.locator(".flow-nodes [data-uml-kind='component']").count() == _SIBLINGS + 1
        canvas = page.locator(".flow-canvas")
        # Three entries: first draw, Reset zoom, and Shift+C (its button hides under 900 px).
        for step in (
            lambda: None,
            lambda: page.get_by_role("button", name="Reset zoom", exact=True).click(),
            lambda: page.keyboard.press("Shift+C"),
        ):
            step()
            sizes = _font_sizes(page)
            assert sizes and min(sizes) >= 11, min(sizes)
            assert canvas.evaluate("(node) => node.scrollHeight > node.clientHeight")
            assert canvas.evaluate("(node) => node.scrollTop") == 0
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_show_whole_map_still_shows_a_whole_module_map(pages):
    playwright, browser, page = _open(pages, "?scope=io&content=modules")
    try:
        page.get_by_role("button", name="Show whole map", exact=True).click()
        assert min(_font_sizes(page)) < 11
        canvas = page.locator(".flow-canvas")
        assert canvas.evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_details_start_closed_and_a_selection_opens_them(pages):
    playwright, browser, page = _open(pages)
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
def test_a_selection_in_the_url_opens_details(pages):
    playwright, browser, page = _open(pages, f"?scope=io&selected={_DATA_SOURCES}")
    try:
        assert page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") == "true"
        assert page.locator(".flow-inspector").is_visible()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_breadcrumbs_jump_to_any_level_by_pointer_and_keyboard(pages):
    playwright, browser, page = _open(pages, f"?scope={_RDBMS}")
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


@pytest.mark.browser
def test_a_module_in_the_url_opens_details_on_the_main_page(pages):
    module = next(m for m in _payload(pages)["modules"] if m["path"].endswith("rdbms/m0.py"))
    playwright, browser, page = _open(pages, f"?scope={_RDBMS}&module={module['id']}")
    try:
        assert page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") == "true"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_a_cell_in_the_url_opens_details_on_the_main_page(pages):
    level = next(
        item
        for item in _payload(pages)["levels"]
        if item["parent_id"] == "io:data_sources:io-data_sources-loaders" and item["cells"]
    )
    playwright, browser, page = _open(
        pages, f"?scope=io:data_sources:io-data_sources-loaders&cell={level['cells'][0]}"
    )
    try:
        assert page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") == "true"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_the_detail_page_opens_details_only_for_a_requested_module(pages):
    module = next(m for m in _payload(pages)["modules"] if m["path"].endswith("rdbms/m0.py"))
    for query, expanded in (
        (f"?component={_RDBMS}&module={module['id']}", "true"),
        (f"?component={_RDBMS}", "false"),
    ):
        playwright, browser, page = _open(pages, query, _DETAIL)
        try:
            toggle = page.locator("[data-flow-details-toggle]")
            assert toggle.get_attribute("aria-expanded") == expanded, query
        finally:
            browser.close()
            playwright.stop()
