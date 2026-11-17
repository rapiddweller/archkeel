# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A keyboard user sees where the focus is in the Explorer, in both themes (#1763).

Consumer: a keyboard user of a written report. Each focus ring of the Explorer uses the design token
`--focus` (dark `#e8805d`, light `#a8431f`), which has at least 3:1 against the surfaces of its
theme (WCAG 1.4.11). Before #1763 a focused menu item only changed its background (about 1.1:1),
and the boxes of the canvas used `--accent` (about 2.4:1 in the light theme).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

ENTER = {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"}
RING = """(() => { const style = getComputedStyle(document.activeElement);
  const probe = document.createElement('i'); probe.style.color = 'var(--focus)';
  document.querySelector('.rp-explorer').append(probe);
  const focus = getComputedStyle(probe).color; probe.remove();
  return [style.outlineStyle, style.outlineWidth, style.outlineColor === focus]; })()"""


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


def _theme(page: Browser, theme: str) -> None:
    """Choose the theme, then press Shift once: the browser then shows focus as for a keyboard."""
    page.evaluate(
        "[...document.querySelectorAll('.ak-seg__btn')]"
        f".find((b) => b.textContent.trim().toLowerCase() === '{theme}').click()"
    )
    shift = {"key": "Shift", "code": "ShiftLeft", "windowsVirtualKeyCode": 16}
    page.send("Input.dispatchKeyEvent", type="rawKeyDown", **shift)
    page.send("Input.dispatchKeyEvent", type="keyUp", **shift)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_a_menu_item_that_the_keyboard_focuses_has_a_ring(
    site: str, page: Browser, theme: str
) -> None:
    page.open(f"{site}/part.html")
    _theme(page, theme)
    page.evaluate("document.querySelector('.ak-icon-only[aria-label=\"Belongs to\"]').focus()")
    page.send("Input.dispatchKeyEvent", type="keyDown", **ENTER)
    page.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter")
    page.wait("!!document.activeElement.closest('.ak-pop')")
    page.press("ArrowDown", code="ArrowDown")

    assert page.evaluate("!!document.activeElement.closest('.ak-pop')")
    assert page.evaluate(RING) == ["solid", "2px", True]


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_a_box_and_the_search_field_have_a_ring_in_the_focus_colour(
    site: str, page: Browser, theme: str
) -> None:
    page.open(f"{site}/part.html")
    _theme(page, theme)
    page.evaluate("document.querySelector('#flow g.node[role=button]').focus()")
    assert page.evaluate(RING) == ["solid", "2px", True]
    page.evaluate("document.querySelector('.ak-search-btn').click()")
    page.wait("document.activeElement.matches('.ak-palette input') || null")
    page.evaluate(
        "document.activeElement.blur(); document.querySelector('.ak-palette input').focus()"
    )
    assert page.evaluate(RING)[0] == "solid"
