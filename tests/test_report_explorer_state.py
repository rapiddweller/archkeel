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

SYSTEM = "docs/architecture/architecture-system.json"
PAGES: dict[str, tuple[str | None, str, *tuple[str, ...]]] = {
    "system": (None, SYSTEM),
    "part": (
        None,
        "docs/architecture/shell.toml",
        "--part-of",
        SYSTEM,
        "--system-href",
        "system.html",
    ),
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


def select(page: Browser, box: str) -> None:
    page.evaluate(
        f"document.querySelector('#flow [data-uml-id=\"{box}\"]')"
        ".dispatchEvent(new MouseEvent('click', { bubbles: true }))"
    )
    page.settle()


def test_back_after_selections_goes_back_one_level(site: str, page: Browser) -> None:
    # AD-734: a selection replaces the history entry; only a navigation adds one.
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.dispatch({ type: 'openLevel', id: 'PART:shell' })")
    page.settle()
    select(page, "LAYER:PART:shell:process")
    select(page, "LAYER:PART:shell:entry")
    page.evaluate("history.back()")
    page.settle()
    assert page.state()["scope"] is None


def test_back_after_a_view_switch_returns_to_the_view(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=PART%3Ashell")
    click(page, '#flow [data-flow-view="diff"]')
    page.evaluate("history.back()")
    page.settle()
    assert (page.state()["view"], page.state()["scope"]) == ("diagram", "PART:shell")


def test_a_deep_link_restores_details_drawer_and_perspective(site: str, page: Browser) -> None:
    # AD-734: Details stay open at the start when the link selects a box.
    page.open(f"{site}/system.html?selected=PART%3Acore&drawer=objects&perspective=layer")
    state = page.evaluate("JSON.parse(document.getElementById('flow').dataset.state)")
    assert (state["selection"], state["details"], state["drawer"], state["perspective"]) == (
        "PART:core",
        True,
        "objects",
        "layer",
    )
    assert page.evaluate("!!document.querySelector('#flow .ak-drawer[aria-label=\"objects\"]')")
    assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")


def test_the_url_of_a_state_gives_the_same_state_back(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    queries = [
        "view=diagram",
        "scope=PART%3Ashell&view=target",
        "scope=PART%3Ashell&content=modules&view=diagram&selected=archkeel.cli.core_arguments",
        "scope=PART%3Ashell&view=diff&perspective=none&selected=LAYER%3APART%3Ashell%3Aprocess",
        "view=diagram&perspective=layer&drawer=overview",
        "view=diagram&details=open",
        "view=diagram&selected=PART%3Acore&details=closed",
    ]
    for query in queries:
        back = page.evaluate(
            f"ArchkeelFlow.toQuery(ArchkeelFlow.fromQuery(new URLSearchParams({query!r})))"
            ".toString()"
        )
        assert back == query


def test_back_restores_the_drawer_of_the_entry(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    click(page, '#flow .ak-rail [data-drawer="objects"]')
    page.evaluate("ArchkeelFlow.dispatch({ type: 'openLevel', id: 'PART:shell' })")
    page.settle()
    click(page, '#flow .ak-rail [data-drawer="objects"]')
    assert page.state()["drawer"] is None
    page.evaluate("history.back()")
    page.settle()
    state = page.state()
    assert (state["scope"], state["drawer"]) == (None, "objects")
    assert page.evaluate("!!document.querySelector('#flow .ak-drawer[aria-label=\"objects\"]')")


def theme(page: Browser) -> list[object]:
    """The theme of the page, the pressed header button, and the URL."""
    return page.evaluate(
        "[document.documentElement.dataset.theme,"
        " document.querySelector('[data-ak-theme][aria-pressed=\"true\"]')?.dataset.akTheme,"
        " location.search.includes('theme=')]"
    )


def test_back_keeps_the_theme_that_the_user_chose(site: str, page: Browser) -> None:
    # E2: the header owns the theme; Back set the theme of the old URL again.
    page.color_scheme("dark")
    page.open(f"{site}/system.html")
    page.evaluate("localStorage.removeItem('archkeel-theme')")
    page.open(f"{site}/system.html")
    click(page, '[data-ak-theme="light"]')
    page.evaluate("ArchkeelFlow.dispatch({ type: 'openLevel', id: 'PART:shell' })")
    page.settle()
    page.evaluate("history.back()")
    page.settle()
    assert theme(page) == ["light", "light", False]


def test_a_chosen_theme_stays_after_a_reload_and_adds_no_entry(site: str, page: Browser) -> None:
    page.color_scheme("dark")
    page.open(f"{site}/system.html")
    page.evaluate("localStorage.removeItem('archkeel-theme')")
    page.open(f"{site}/system.html")
    entries = page.evaluate("history.length")
    click(page, '[data-ak-theme="light"]')
    assert page.evaluate("history.length") == entries
    page.open(page.evaluate("location.href"))
    assert theme(page) == ["light", "light", False]
    assert page.state()["theme"] == "light"


def test_a_theme_action_goes_through_the_owner_of_the_theme(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.dispatch({ type: 'setTheme', theme: 'dark' })")
    assert theme(page) == ["dark", "dark", False]
    assert page.evaluate("localStorage.getItem('archkeel-theme')") == "dark"


CRUMBS = """(() => {
  const bar = document.querySelector('#flow .flow-breadcrumb'), box = bar.getBoundingClientRect();
  return [...bar.querySelectorAll('button')].map((crumb) => {
    const own = crumb.getBoundingClientRect();
    return { text: crumb.textContent, title: crumb.title,
      current: crumb.getAttribute('aria-current'),
      whole: crumb.scrollWidth <= crumb.clientWidth + 1 && own.left >= box.left - 1
        && own.right <= box.right + 1 };
  });
})()"""


def test_alt_arrow_up_goes_up_one_level_from_the_current_crumb(site: str, page: Browser) -> None:
    # E3: up is derived from the path; the current crumb says so.
    page.open(f"{site}/system.html?scope=LAYER%3APART%3Ashell%3Aprocess")
    crumbs = page.evaluate(CRUMBS)
    assert [crumb["current"] for crumb in crumbs] == [None, None, "page"]
    page.press("ArrowUp", code="ArrowUp", modifiers=1)
    page.settle()
    state = page.state()
    assert (state["scope"], state["selection"]) == ("PART:shell", "LAYER:PART:shell:process")
    page.evaluate("history.back()")
    page.settle()
    assert page.state()["scope"] == "LAYER:PART:shell:process"


def test_the_current_crumb_stays_whole_in_fullscreen(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope=LAYER%3APART%3Acore%3Amodel")
    click(page, "#flow .flow-fullscreen")
    crumbs = page.evaluate(CRUMBS)
    click(page, "#flow .flow-fullscreen")
    assert crumbs[-1]["whole"], crumbs
    assert [crumb["title"] for crumb in crumbs] == ["ArchKeel", "Rust core", "model"]


def test_fullscreen_and_the_current_view_key_keep_the_selection(site: str, page: Browser) -> None:
    # E3: a relayout is not a view change; it kept the box but dropped the selected module.
    page.open(f"{site}/system.html?scope=SHELL-ARGUMENTS")
    module = first_module(page)
    page.evaluate(f"ArchkeelFlow.dispatch({{ type: 'select', id: {module!r} }})")
    entries = page.evaluate("history.length")
    click(page, "#flow .flow-fullscreen")
    page.settle()
    assert page.state()["module"] == module
    page.press("1")
    page.settle()
    click(page, "#flow .flow-fullscreen")
    state = page.state()
    assert (state["module"], state["selection"]) == (module, module)
    assert page.evaluate("history.length") == entries


def test_escape_closes_one_layer_at_a_time(site: str, page: Browser) -> None:
    # E3: overlay > popover > drawer > expanded > selection.
    page.open(f"{site}/system.html?selected=PART%3Acore&drawer=objects")
    click(page, "#flow .flow-fullscreen")
    click(page, '#flow [data-ak-pop][title="Share"]')
    seen = []
    for _ in range(5):
        state = page.state()
        seen.append((state["pop"], state["drawer"], state["expanded"], state["selection"]))
        page.press("Escape")
        page.settle()
    assert seen == [
        ("share", "objects", "fallback", "PART:core"),
        (None, "objects", "fallback", "PART:core"),
        (None, None, "fallback", "PART:core"),
        (None, None, None, "PART:core"),
        (None, None, None, None),
    ]


def test_a_route_notice_opens_details_through_the_state(site: str, page: Browser) -> None:
    page.send("Page.navigate", url=f"{site}/system.html?scope=NOPE")
    page.wait("document.getElementById('flow')?.dataset.layoutState === 'ready'")
    state = page.state()
    assert state["notice"] and state["details"] is True
    assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")


def test_the_root_of_a_part_names_its_system_and_links_up(site: str, page: Browser) -> None:
    # E4: the page of a part reads "<part> of <system>"; the system is a link to its page.
    page.open(f"{site}/part.html")
    crumb = page.evaluate("document.querySelector('#flow .flow-breadcrumb').textContent")
    assert crumb == "Python shell of ArchKeel"
    page.evaluate("document.querySelector('#flow .flow-breadcrumb a').click()")
    page.wait("location.pathname === '/system.html'")
    page.settle()
    assert (
        page.evaluate("document.querySelector('#flow .flow-breadcrumb').textContent") == "ArchKeel"
    )


def test_the_explorer_names_the_result_and_no_observation(site: str, page: Browser) -> None:
    # "Observation" was a 4.0.1 word: next to PASS it read like a contradiction.
    page.open(f"{site}/part.html")
    status = page.evaluate("document.querySelector('#flow .ak-run-status').textContent")
    assert status == "Result: PASS assuming 1 stated external user"
    click(page, '#flow .ak-rail [data-drawer="overview"]')
    drawer = page.evaluate("document.querySelector('#flow .ak-drawer').textContent")
    assert "Result: PASS assuming 1 stated external user" in drawer
    assert "bservation" not in page.evaluate("document.getElementById('flow').innerText")
