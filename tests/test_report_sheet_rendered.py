# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The fact sheets and the perspective bar of the Explorer, checked in a headless Chrome.

Each test loads the real system report of this repository and, where it needs a case that the report
does not have, plants it in the data that the page holds and reads the sheet that the page draws.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

PAGES = {"system": (None, "docs/architecture/architecture-system.json")}


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("site")
    write_pages(release_core, folder, PAGES)
    with serve(folder) as base:
        yield base


@pytest.fixture
def page(tmp_path: Path) -> Iterator[Browser]:
    with browser(tmp_path / "profile") as driven:
        yield driven


def _open_module(page: Browser, site: str, name: str) -> None:
    """Open the page with the modules of the shell component `commands`."""
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.openComponent('PART:shell')")
    page.settle()
    page.evaluate("ArchkeelFlow.openComponent('SHELL-COMMANDS', 'modules')")
    page.settle()


def _module_sheet(page: Browser, module: str) -> str:
    """The text of the sheet of a module, selected after another module so that it is drawn anew."""
    others = page.evaluate(
        "ArchkeelFlow.state().scene.nodes.filter((n) => n.module).map((n) => n.id)"
    )
    other = next(item for item in others if item != module)
    for chosen in (other, module):
        page.evaluate(f"ArchkeelFlow.selectElement({json.dumps(chosen)})")
        page.settle()
    return page.evaluate("document.querySelector('.flow-inspector').innerText")


def _module_id(page: Browser, suffix: str) -> str:
    return page.evaluate(
        f"ArchkeelFlow.state().scene.nodes.find((n) => n.module && n.id.endsWith({suffix!r})).id"
    )


def test_the_module_sheet_states_the_symbol_limit_once_and_the_count_when_there_is_one(
    site: str, page: Browser
) -> None:
    _open_module(page, site, "commands")
    module = _module_id(page, "core_only")
    unavailable = _module_sheet(page, module)
    # The limit in plain words, once; the owner banned empty filler, not an honest limit.
    assert unavailable.count("Symbols: not counted") == 1
    assert "(this version does not list symbols)" in unavailable
    assert "5.0 frame" not in unavailable and "in this run" not in unavailable
    page.evaluate(f"ArchkeelFlow.reportScene.atlasModuleById({json.dumps(module)}).symbols = 12")
    counted = _module_sheet(page, module)
    assert "12 observed symbols" in counted and "not counted" not in counted


def test_every_public_name_of_a_component_is_in_the_fold_that_lists_them(
    site: str, page: Browser
) -> None:
    page.open(f"{site}/system.html")
    names = ",".join(json.dumps(f"app.mod:name{n}") for n in range(1, 11))
    page.evaluate(
        "(() => { const c = ArchkeelFlow.reportScene.atlas.components"
        ".find((item) => item.id === 'SHELL-COMMANDS');"
        f" c.public = [{names}]; ArchkeelFlow.selectComponent('SHELL-COMMANDS'); }})()"
    )
    page.settle()
    fold = page.evaluate(
        "document.querySelector('.flow-inspector details.atlas-provides')?.innerText"
    )
    assert fold is not None, "ten names fold behind a count"
    html = page.evaluate(
        "document.querySelector('.flow-inspector details.atlas-provides').innerHTML"
    )
    for number in range(1, 11):
        assert f"name{number}" in html, f"name{number} cannot be revealed"
    assert "more" not in fold.split("(10)")[-1], "no name is replaced by a count"


def test_an_unknown_owner_is_counted_apart_from_the_components(site: str, page: Browser) -> None:
    _open_module(page, site, "commands")
    module = _module_id(page, "core_only")
    # Two of the modules that core_only imports have no owner; the others have one each.
    page.evaluate(
        "(() => { const atlas = ArchkeelFlow.reportScene.atlas;"
        " const imported = atlas.cells.filter((c) => c.source_id === " + json.dumps(module) + ")"
        ".slice(0, 2).map((c) => c.target_id);"
        " atlas.assignments.filter((a) => imported.includes(a.id))"
        ".forEach((a) => { a.component_id = null; }); })()"
    )
    sheet = _module_sheet(page, module)
    imports = next(line for line in sheet.splitlines() if line.startswith("Imports ·"))
    assert "2 modules outside the contract" in imports
    assert "13 modules in 13 components" in imports, imports
    assert "UNKNOWN owner" not in sheet
    # The fold holds the group that no component owns; it is drawn under its own name.
    assert "Outside the contract" in page.evaluate(
        "document.querySelector('.flow-inspector').innerHTML"
    )


def _bar_rects(page: Browser) -> dict:
    return page.evaluate(
        "(() => { const flow = document.getElementById('flow').getBoundingClientRect();"
        " const bar = document.querySelector('.ak-bottom-center').getBoundingClientRect();"
        " const chips = [...document.querySelectorAll('.ak-bottom-center button')]"
        ".map((b) => { const r = b.getBoundingClientRect();"
        " return { text: b.textContent.trim(), left: r.left, right: r.right,"
        " top: r.top, bottom: r.bottom }; });"
        " return { flow: { left: flow.left, right: flow.right, top: flow.top,"
        " bottom: flow.bottom },"
        " bar: { left: bar.left, right: bar.right, width: bar.width }, chips }; })()"
    )


@pytest.mark.parametrize("width", [390, 1024])
def test_the_perspective_chips_are_inside_the_embedded_explorer_on_a_narrow_screen(
    site: str, tmp_path: Path, width: int
) -> None:
    with browser(tmp_path / "profile", width=width, height=900) as page:
        page.open(f"{site}/system.html")
        page.evaluate("document.getElementById('flow').scrollIntoView()")
        rects = _bar_rects(page)
        flow = rects["flow"]
        assert rects["bar"]["width"] > 150, rects["bar"]
        assert len(rects["chips"]) >= 5
        for chip in rects["chips"]:
            assert flow["left"] - 1 <= chip["left"] and chip["right"] <= flow["right"] + 1, chip
            assert flow["top"] <= chip["top"] and chip["bottom"] <= flow["bottom"] + 1, chip
            assert chip["right"] <= rects["bar"]["right"] + 1, chip


def test_a_mixed_language_badge_text_stays_inside_its_badge(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate(
        "(() => { const node = ArchkeelFlow.state().scene.nodes[0];"
        " node.component.language = 'python + typescript + dart';"
        " [...document.querySelectorAll('.ak-bottom-center button')]"
        ".find((b) => b.textContent.trim() === 'Language').click(); })()"
    )
    page.settle()
    fit = page.evaluate(
        "(() => { const badge = document.querySelector('.ak-language-badge');"
        " const rect = badge.querySelector('rect').getBoundingClientRect();"
        " const text = badge.querySelector('text').getBoundingClientRect();"
        " const card = badge.closest('[data-uml-id]').querySelector('.card')"
        ".getBoundingClientRect();"
        " return { rect: [rect.left, rect.right], text: [text.left, text.right],"
        " card: [card.left, card.right], shown: badge.querySelector('text').textContent }; })()"
    )
    assert fit["rect"][0] <= fit["text"][0] and fit["text"][1] <= fit["rect"][1] + 0.5, fit
    # The badge is never cut: it shows the whole value, inside its box (lead review, item 2).
    assert fit["shown"] == "python + typescript + dart", fit
    assert fit["card"][0] <= fit["rect"][0] and fit["rect"][1] <= fit["card"][1], fit
