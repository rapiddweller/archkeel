# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser checks of the module matrix in a real system report."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import browser, serve, write_pages


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("matrix-site")
    runs = {"system": (None, "docs/architecture/architecture-system.json")}
    write_pages(release_core, folder, runs)
    with serve(folder) as base:
        yield base


CORE = "PART%3Acore"


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_large_matrix_keeps_labels_and_survives_expansion(
    site: str, tmp_path: Path, width: int, height: int
) -> None:
    with browser(tmp_path / "profile", width=width, height=height) as page:
        if width < 500:
            page.send(
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=height,
                deviceScaleFactor=1,
                mobile=True,
            )
            page.send("Emulation.setTouchEmulationEnabled", enabled=True)

        def click_fullscreen() -> None:
            point = page.evaluate("""(() => {
              const e = document.querySelector('#flow .flow-fullscreen');
              e.scrollIntoView({block: 'center', inline: 'center'});
              const r = e.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            })()""")
            for event in ("mousePressed", "mouseReleased"):
                page.send(
                    "Input.dispatchMouseEvent", type=event, button="left", clickCount=1, **point
                )

        page.open(f"{site}/system.html?scope={CORE}")
        page.evaluate("document.querySelector('#flow .ak-rail [data-drawer=overview]').click()")
        page.wait("!!document.querySelector('#flow .matrix-cell')")
        result = page.evaluate(r"""(() => {
          const matrix = document.querySelector('#flow .flow-matrix');
          const labels = matrix.querySelectorAll('.matrix-label');
          const cell = matrix.querySelector('.matrix-cell');
          const label = matrix.querySelector('svg').getAttribute('aria-label');
          const modules = Number(label.match(/\d+/)[0]);
          return { labels: labels.length, cellWidth: cell.getBoundingClientRect().width, modules };
        })()""")
        assert result["modules"] > 80
        assert result["labels"] == 2 * result["modules"]
        assert result["cellWidth"] >= 11
        assert page.evaluate("""(() => {
          const m = document.querySelector('#flow .flow-matrix');
          const labels = m.querySelectorAll('.matrix-label');
          labels[labels.length - 1].scrollIntoView({block: 'center', inline: 'center'});
          const a = labels[labels.length - 1].getBoundingClientRect();
          const b = m.getBoundingClientRect();
          return m.scrollLeft > 0 && a.left < b.right && a.right > b.left
            && a.top < b.bottom && a.bottom > b.top;
        })()""")
        click_fullscreen()
        page.wait("!!document.querySelector('#flow').dataset.expanded")
        assert page.evaluate("""(() => {
          const f = document.querySelector('#flow');
          return (f.dataset.expanded === 'native') === (document.fullscreenElement === f);
        })()""")
        click_fullscreen()
        page.wait("!document.querySelector('#flow').dataset.expanded")
        page.evaluate("document.querySelector('#flow').requestFullscreen = undefined")
        click_fullscreen()
        page.wait("document.querySelector('#flow').dataset.expanded === 'fallback'")
        assert page.evaluate("""(() => {
          const m = document.querySelector('#flow .flow-matrix');
          return getComputedStyle(m.closest('.flow-explore')).display !== 'none'
            && m.getBoundingClientRect().width > 0;
        })()""")
        click_fullscreen()
        assert page.evaluate("!document.querySelector('#flow').dataset.expanded")
        assert (
            page.evaluate("getComputedStyle(document.querySelector('#flow .flow-explore')).display")
            != "none"
        )
        assert page.evaluate("""(() => {
          const m = document.querySelector('#flow .flow-matrix');
          const cells = m.querySelectorAll('.matrix-cell'), cell = cells[cells.length - 1];
          cell.scrollIntoView({block: 'center', inline: 'center'});
          const a = cell.getBoundingClientRect(), b = m.getBoundingClientRect();
          return a.left >= b.left && a.right <= b.right && a.top >= b.top && a.bottom <= b.bottom;
        })()""")
