# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each fact sheet of the Explorer, rendered in a headless Chrome, holds no filler word.

The fact sheet tests of the report check strings in the script. This test shows every sheet of
the system page in As-Is, Target and Diff (each level, each component, each module) and reads
the text that the user sees.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from explorer_support import Browser, browser, serve, write_pages

FILLER = r"\bNone\b|unavailable|Nothing stated|Does this fit|[Oo]bservation\b"
SHEETS = """(async (views) => {
  const F = window.ArchkeelFlow, root = F.root;
  const words = new RegExp(%r);
  const ready = () => new Promise((done) => {
    const tick = () => root.dataset.layoutState === "ready" ? done() : setTimeout(tick, 20);
    tick();
  });
  const found = [];
  let sheets = 0;
  const check = (view, what) => {
    sheets += 1;
    const match = root.querySelector(".flow-inspector-content").textContent.match(words);
    if (match) found.push(`${view} ${what}: ${match[0]}`);
  };
  for (const view of views) {
    root.querySelector(`[data-flow-view="${view}"]`).click();
    for (const level of F.atlas.levels) {
      F.openComponent(level.parent_id);
      await ready();
      check(view, `level ${level.parent_id}`);
      for (const id of level.component_ids) { F.selectElement(id); check(view, `component ${id}`); }
    }
    if (view === "target") continue;
    F.openComponent(null);
    await ready();
    for (const module of F.atlas.modules) {
      F.selectElement(module.id);
      check(view, `module ${module.id}`);
    }
  }
  return { sheets, found };
})"""


def walk(page: Browser, views: tuple[str, ...]) -> dict[str, Any]:
    """Show each sheet in the views; return the count of sheets and each filler word found."""
    return page.evaluate(f"({SHEETS % FILLER})({list(views)!r})")


@pytest.fixture(scope="module")
def page(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    folder = tmp_path_factory.mktemp("site")
    write_pages(
        release_core, folder, {"system": (None, "docs/architecture/architecture-system.json")}
    )
    with serve(folder) as base, browser(tmp_path_factory.mktemp("profile")) as driven:
        driven.open(f"{base}/system.html")
        yield driven


def test_no_rendered_fact_sheet_holds_a_filler_word(page: Browser) -> None:
    result = walk(page, ("diagram", "target", "diff"))
    assert result["sheets"] > 1000, "the walk showed too few sheets to mean anything"
    assert result["found"] == []


def test_the_sheet_walk_finds_a_planted_filler_word(page: Browser) -> None:
    page.evaluate("ArchkeelFlow.atlas.components[0].responsibilities.push('Nothing stated')")
    found = walk(page, ("diagram",))["found"]
    assert any("Nothing stated" in item for item in found)
