# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The perspective key and the share menu of the Explorer, in a headless Chrome (#1725).

They live in report-presentation.js since the split of report-canvas.js.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

PAGES: dict[str, tuple[str | None, str, *tuple[str, ...]]] = {
    "system": (None, "docs/architecture/architecture-system.json"),
}


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("site")
    write_pages(release_core, folder, PAGES)
    with serve(folder) as base:
        yield base


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    with browser(tmp_path_factory.mktemp("profile")) as driven:
        yield driven


def test_the_key_p_cycles_the_perspective(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    before = page.state()["perspective"]
    page.press("p", code="KeyP")
    page.settle()
    assert page.state()["perspective"] != before


def test_the_share_menu_copies_the_diagram_as_mermaid(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("document.querySelector('#flow [aria-label=\"Share\"]').click()")
    labels = page.evaluate(
        "[...document.querySelectorAll('#flow .ak-pop button')].map((b) => b.textContent)"
    )
    assert labels == ["Copy link to this view", "Copy diagram as Mermaid", "Download SVG"]
    page.evaluate(
        "[...document.querySelectorAll('#flow .ak-pop button')]"
        ".find((b) => b.textContent === 'Copy diagram as Mermaid').click()"
    )
    # A headless Chrome refuses the clipboard, so the page offers the text in a dialog.
    page.wait("Boolean(document.querySelector('#flow dialog textarea'))")
    copied = page.evaluate("document.querySelector('#flow dialog textarea').value")
    assert copied.startswith("flowchart LR") and "Python shell" in copied
