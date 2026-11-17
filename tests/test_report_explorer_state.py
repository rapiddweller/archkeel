# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Explorer of a written report, driven in a headless Chrome (Wave 2 of #1451, E6).

Each test loads a real page of this repository over a local server, acts as a user (a key, a
click, Back) and reads the state of the Explorer, its URL and the browser history.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

PAGES = {
    "system": (None, "docs/architecture/architecture-system.json"),
}


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The base URL of a local server with the written pages."""
    folder = tmp_path_factory.mktemp("site")
    write_pages(release_core, folder, PAGES)
    with serve(folder) as base:
        yield base


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    with browser(tmp_path_factory.mktemp("profile")) as driven:
        yield driven


def test_the_explorer_starts_at_the_system_level(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    state = page.state()
    assert (state["view"], state["scope"], state["selection"]) == ("diagram", None, None)
    assert page.evaluate("ArchkeelFlow.state().scene.nodes.map((n) => n.id)") == [
        "PART:shell",
        "PART:core",
    ]


def test_back_leaves_each_opened_level_in_turn(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.openComponent('PART:shell')")
    page.settle()
    page.evaluate("ArchkeelFlow.openComponent('LAYER:PART:shell:process')")
    page.settle()
    assert page.state()["scope"] == "LAYER:PART:shell:process"
    page.evaluate("history.back()")
    page.settle()
    assert page.state()["scope"] == "PART:shell"
    page.evaluate("history.back()")
    page.settle()
    assert page.state()["scope"] is None


def test_a_deep_link_opens_its_level_with_its_selection(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=PART%3Ashell&selected=LAYER%3APART%3Ashell%3Aprocess")
    state = page.state()
    assert (state["scope"], state["selection"]) == ("PART:shell", "LAYER:PART:shell:process")


def test_a_click_on_a_box_selects_it_and_opens_its_facts(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate(
        "document.querySelector('#flow [data-uml-id=\"PART:core\"]')"
        ".dispatchEvent(new MouseEvent('click', { bubbles: true }))"
    )
    state = page.state()
    assert (state["selection"], state["details"]) == ("PART:core", True)
    assert "selected=PART%3Acore" in state["search"]


def first_module(page: Browser) -> str:
    return page.evaluate("ArchkeelFlow.state().scene.nodes.find((n) => n.kind === 'module').id")


def test_enter_on_a_module_selects_it_on_this_page(site: str, page: Browser) -> None:
    # #1471: Enter went to architecture.detail.html, which no run writes.
    page.open(f"{site}/system.html?scope=SHELL-ARGUMENTS")
    module = first_module(page)
    page.evaluate(f"document.querySelector('#flow [data-uml-id=\"{module}\"]').focus()")
    page.press("Enter")
    page.settle()
    state = page.state()
    assert page.evaluate("location.pathname") == "/system.html"
    assert (state["scope"], state["selection"], state["details"]) == (
        "SHELL-ARGUMENTS",
        module,
        True,
    )
    assert "Enter opens direct definitions" not in page.evaluate(
        "document.querySelector('#flow .flow-legend').textContent"
    )


def test_a_module_found_by_search_opens_at_its_level(site: str, page: Browser) -> None:
    # #1471: the search result of a module went to architecture.detail.html.
    page.open(f"{site}/system.html?scope=SHELL-ARGUMENTS")
    module = first_module(page)
    page.open(f"{site}/system.html")
    page.evaluate(
        "(() => { document.querySelector('#flow .ak-search-btn').click();"
        " const input = document.querySelector('#flow .ak-palette input');"
        f" input.value = {module!r}; input.dispatchEvent(new Event('input')); }})()"
    )
    page.wait(
        "document.querySelector('#flow .ak-result[aria-selected=\"true\"] .ak-sub')"
        "?.textContent.length > 0"
    )
    page.evaluate(
        "document.querySelector('#flow .ak-palette input')"
        ".dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))"
    )
    page.settle()
    state = page.state()
    assert page.evaluate("location.pathname") == "/system.html"
    assert state["selection"] == module
    assert state["scope"] is not None


def click(page: Browser, selector: str) -> None:
    page.evaluate(f"document.querySelector({selector!r}).click()")
    page.settle()


def test_a_view_button_switches_the_view_and_keeps_the_level(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=PART%3Ashell")
    click(page, '#flow [data-flow-view="target"]')
    state = page.state()
    assert (state["view"], state["scope"]) == ("target", "PART:shell")
    assert "view=target" in state["search"]


def test_the_details_button_opens_and_closes_the_fact_sheet(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    assert page.state()["details"] is False
    click(page, "#flow .flow-details-toggle")
    assert page.state()["details"] is True
    click(page, "#flow .flow-details-toggle")
    assert page.state()["details"] is False


def test_a_crumb_goes_up_to_its_level(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=LAYER%3APART%3Ashell%3Aprocess")
    click(page, '#flow .flow-breadcrumb [data-atlas-depth="1"]')
    assert page.state()["scope"] == "PART:shell"


def test_escape_on_the_diagram_clears_the_selection(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?selected=PART%3Acore")
    assert page.state()["selection"] == "PART:core"
    page.evaluate("document.querySelector('#flow [data-uml-id=\"PART:core\"]').focus()")
    page.press("Escape")
    page.settle()
    assert page.state()["selection"] is None


def test_a_perspective_choice_is_kept_in_the_url(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate(
        "[...document.querySelectorAll('#flow .ak-bottom-center button')]"
        ".find((b) => b.textContent === 'Layer').click()"
    )
    assert "perspective=layer" in page.evaluate("location.search")
    assert (
        page.evaluate(
            "document.querySelector('#flow .ak-bottom-center [aria-pressed=\"true\"]').textContent"
        )
        == "Layer"
    )


def test_a_matrix_cell_selects_its_import_and_names_it_in_the_url(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=PART%3Ashell")
    page.evaluate("document.querySelector('#flow .ak-rail [data-drawer=\"overview\"]').click()")
    page.wait("!!document.querySelector('#flow .matrix-cell')")
    cell = page.evaluate(
        "(() => { const c = document.querySelector('#flow .matrix-cell');"
        " c.dispatchEvent(new MouseEvent('click', { bubbles: true })); return c.dataset.cell; })()"
    )
    assert f"cell={cell}" in page.evaluate("location.search")
    assert "Observed import cell" in page.evaluate(
        "document.querySelector('#flow .flow-inspector-content').textContent"
    )
