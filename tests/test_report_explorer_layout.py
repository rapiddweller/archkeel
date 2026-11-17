# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The layout of large and stacked levels of the Explorer, in a headless Chrome.

The self report holds a part with more than 600 modules ("Rust core"). Its Modules view took
three seconds of ELK work and then showed an empty corner of a 50000 px sheet (issue 1488); two
stacked boxes got an edge that ran around the upper box (issue 1489); the first view after a
drill was drawn at 40 percent, too small to read (issue 1490).
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

PAGES = {"system": (None, "docs/architecture/architecture-system.json")}
CORE = "PART%3Acore"
# The click on a view and the ready layout: 3 s before issue 1488, 0.1 s after it on a laptop.
BUDGET_SECONDS = 2.0
# The readable floor of `fit` in flow.js (READABLE_SCALE).
READABLE_ZOOM = 85
STATE = "document.getElementById('flow').dataset.layoutState"
VISIBLE_CARDS = """(() => {
  const canvas = document.querySelector('#flow .flow-canvas').getBoundingClientRect();
  return [...document.querySelectorAll('#flow svg [data-uml-id] .card')].filter((card) => {
    const box = card.getBoundingClientRect();
    return box.left >= canvas.left && box.right <= canvas.right
      && box.top >= canvas.top && box.bottom <= canvas.bottom;
  }).length;
})()"""


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


def choose(page: Browser, content: str) -> float:
    """Click the Components or Modules choice; the seconds until the layout is ready."""
    started = time.monotonic()
    page.evaluate(
        "document.querySelector("
        f"'#flow .atlas-content-choice button[data-content=\"{content}\"]').click()"
    )
    page.wait(f"{STATE} === 'ready' || {STATE} === 'error'", timeout=30)
    elapsed = time.monotonic() - started
    assert page.evaluate(STATE) == "ready"
    page.settle()
    return elapsed


@pytest.mark.parametrize("content", ["components", "modules"])
def test_each_view_of_the_rust_core_is_ready_in_budget(
    site: str, page: Browser, content: str
) -> None:
    other = "components" if content == "modules" else "modules"
    page.open(f"{site}/system.html?scope={CORE}&content={other}")
    elapsed = choose(page, content)
    assert elapsed < BUDGET_SECONDS, f"{content}: ready after {elapsed:.2f} s"
    assert page.evaluate(VISIBLE_CARDS) > 0, "the canvas shows no complete box"


def test_a_level_with_too_many_modules_groups_them_by_component(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope={CORE}&content=modules")
    scene = page.evaluate(
        "(() => { const s = ArchkeelFlow.state().scene;"
        " return { nodes: s.nodes.length, grouped: s.grouped,"
        " counts: s.nodes.reduce((sum, n) => sum + (n.group || 0), 0) }; })()"
    )
    modules = scene["grouped"]["modules"]
    assert modules > scene["grouped"]["limit"] == 150
    assert scene["nodes"] <= 150
    assert scene["counts"] == modules
    assert f"{modules} observed modules in" in page.evaluate(
        "document.querySelector('.atlas-summary').textContent"
    )
    page.evaluate(
        "document.querySelector('#flow [data-uml-id=\"LAYER:PART:core:report\"]')"
        ".dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))"
    )
    page.settle()
    assert page.state()["scope"] == "LAYER:PART:core:report"
    nodes = page.evaluate("ArchkeelFlow.state().scene.nodes.map((n) => n.kind)")
    assert nodes and set(nodes) == {"module"}


def test_two_stacked_boxes_get_a_direct_edge(tmp_path: Path, site: str) -> None:
    # A tall canvas wraps the two parts of the system into two rows.
    with browser(tmp_path, width=1440, height=1300) as tall:
        tall.open(f"{site}/system.html")
        shell, core, path = tall.evaluate(
            "(() => { const box = (id) => { const r = document.querySelector("
            '`#flow [data-uml-id="${id}"] .card`).getBoundingClientRect();'
            " return [r.left, r.right, r.top, r.bottom]; };"
            " return [box('PART:shell'), box('PART:core'), document.querySelector("
            "'#flow [data-uml-id=\"interface:core-frame-protocol\"] .line')"
            ".getAttribute('d')]; })()"
        )
    assert shell[3] <= core[2] and shell[0] < core[1] and core[0] < shell[1], "not stacked"
    bends = path.count("L") - 1
    assert bends <= 2, path


def test_the_first_view_after_a_drill_is_readable(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.openComponent('PART:core')")
    page.settle()
    page.evaluate("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    zoom = page.evaluate("document.querySelector('#flow .flow-zoom-value').textContent")
    assert int(zoom.rstrip("%")) >= READABLE_ZOOM
    assert page.evaluate(VISIBLE_CARDS) > 0
