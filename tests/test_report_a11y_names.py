# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A keyboard and screen-reader user can skip the page parts and hears whole names (#1765, #1766).

Consumer: a keyboard or screen-reader user of a written report. The first Tab stop is a link that
skips to the result; a link before the Explorer skips its controls; a language chip and an item of
the Belongs to menu have a name with a separator ("python, 1", "Python shell, 7 inside") and not
the joined text ("python1").
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

TAB = {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9}
ENTER = {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"}
SYSTEM = "docs/architecture/architecture-system.json"


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("site")
    write_pages(release_core, folder, {"part": (None, "docs/architecture/shell.toml")})
    with serve(folder) as base:
        yield base


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    with browser(tmp_path_factory.mktemp("profile")) as driven:
        yield driven


def _key(page: Browser, key: dict) -> None:
    page.send("Input.dispatchKeyEvent", type="rawKeyDown", **key)
    if "text" in key:
        page.send("Input.dispatchKeyEvent", type="char", **key)
    page.send(
        "Input.dispatchKeyEvent", type="keyUp", **{k: v for k, v in key.items() if k != "text"}
    )


def test_the_first_tab_stop_skips_to_the_result(site: str, page: Browser) -> None:
    page.open(f"{site}/part.html")
    page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
    _key(page, TAB)
    link = page.evaluate(
        "(() => { const e = document.activeElement; const r = e.getBoundingClientRect();"
        " return [e.textContent, r.width > 1 && r.height > 1]; })()"
    )
    assert link == ["Skip to the result", True]
    _key(page, ENTER)
    assert page.evaluate("document.activeElement.id") == "result"


def test_a_link_before_the_explorer_skips_its_controls(site: str, page: Browser) -> None:
    page.open(f"{site}/part.html")
    page.evaluate("document.querySelector('a.ak-skip[href=\"#after-explorer\"]').focus()")
    assert page.evaluate("document.activeElement.textContent") == "Skip the Explorer"
    _key(page, ENTER)
    assert page.evaluate("document.activeElement.id") == "after-explorer"
    assert page.evaluate(
        "!!(document.querySelector('.rp-explorer').compareDocumentPosition("
        "document.activeElement) & Node.DOCUMENT_POSITION_FOLLOWING)"
    )


def test_a_chip_and_a_menu_item_have_names_with_a_separator(site: str, page: Browser) -> None:
    page.open(f"{site}/part.html")
    page.evaluate(
        "[...document.querySelectorAll('.ak-bottom-center button')]"
        ".find((b) => b.textContent.trim() === 'Language').click()"
    )
    page.wait("document.querySelectorAll('.ak-chip').length > 0 || null")
    chips = page.evaluate(
        "[...document.querySelectorAll('.ak-chip')].map((c) => c.getAttribute('aria-label'))"
    )
    assert chips and all(", " in name for name in chips), chips
    page.evaluate("document.querySelector('.ak-icon-only[aria-label=\"Belongs to\"]').click()")
    page.wait("document.querySelectorAll('.ak-pop button small').length > 0 || null")
    items = page.evaluate(
        "[...document.querySelectorAll('.ak-pop button')].filter((b) => b.querySelector('small'))"
        ".map((b) => [b.getAttribute('aria-label'), b.firstChild.textContent,"
        " b.querySelector('small').textContent])"
    )
    assert items and all(name == f"{label}, {note}" for name, label, note in items), items
