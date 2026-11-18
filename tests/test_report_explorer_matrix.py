# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check grouped and small module matrices in a real system report."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("matrix-site")
    runs = {"system": (None, "docs/architecture/architecture-system.json")}
    write_pages(release_core, folder, runs)
    with serve(folder) as base:
        yield base


def click(page: Browser, selector: str) -> None:
    point = page.evaluate(f"""(() => {{
      const e = document.querySelector({selector!r});
      e.scrollIntoView({{block: 'center', inline: 'center'}});
      const r = e.getBoundingClientRect();
      return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
    }})()""")
    for event in ("mousePressed", "mouseReleased"):
        page.send("Input.dispatchMouseEvent", type=event, button="left", clickCount=1, **point)


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_large_level_opens_a_grouped_matrix_and_its_real_relationships(
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
        page.open(f"{site}/system.html?scope=PART%3Acore")
        page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        assert not page.evaluate("!!document.querySelector('#flow .flow-matrix')")
        click(page, "#flow [data-open-matrix]")
        assert page.evaluate("document.querySelector('.atlas-matrix-dialog').open")
        summary = page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-dialog');
          const cells = [...d.querySelectorAll('[data-row]')];
          const labels = d.querySelectorAll('.matrix-label');
          const max = cells.reduce((a, b) => Number(a.nextSibling.textContent)
            > Number(b.nextSibling.textContent) ? a : b);
          max.focus();
          return {labels: labels.length, cells: cells.length,
            count: Number(max.nextSibling.textContent),
            name: max.getAttribute('aria-label'), fullscreen: !!document.fullscreenElement,
            row: max.dataset.row, column: max.dataset.column};
        })()""")
        assert 2 <= summary["labels"] < 1424
        assert 0 < summary["cells"] < 712 * 712
        assert not summary["fullscreen"]
        page.press("Enter")
        if width < 500:
            point = page.evaluate(f"""(() => {{
              const cell = document.querySelector(
                '[data-row="{summary["row"]}"][data-column="{summary["column"]}"]');
              cell.scrollIntoView({{block: 'center', inline: 'center'}});
              cell.addEventListener('click', () => {{ window.matrixTouch = true; }},
                {{once: true}});
              const r = cell.getBoundingClientRect();
              const x = r.x + r.width / 2, y = r.y + r.height / 2;
              return {{x, y, hit: document.elementFromPoint(x, y) === cell}};
            }})()""")
            assert point["hit"], point
            page.send(
                "Input.dispatchTouchEvent",
                type="touchStart",
                touchPoints=[{"x": point["x"], "y": point["y"]}],
            )
            page.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
            page.wait("window.matrixTouch === true")
            page.evaluate(f"""document.querySelector(
              '[data-row="{summary["row"]}"][data-column="{summary["column"]}"]').focus()""")
        detail = page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-detail');
          const R = ArchkeelFlow.reportScene, A = R.atlas;
          const byId = new Map(A.modules.map((m) => [m.id, m.name]));
          const known = A.cells.filter((c) => byId.has(c.source_id) && byId.has(c.target_id));
          const names = new Set(known
            .map((c) => `${byId.get(c.source_id)} → ${byId.get(c.target_id)}`));
          const rows = [...d.querySelectorAll('li')].map((li) => li.textContent);
          const level = A.levels.find((item) => item.parent_id === 'PART:core');
          const nodes = R.atlasModuleScene(level, 'diagram').nodes;
          const ids = new Set(nodes.map((node) => node.id));
          const groups = new Map(R.atlasModules(level, 'diagram').map((module) => [module.id,
            R.componentRoute(module.place_id || module.component_id)
              .find((item) => ids.has(item.id))?.id || module.id]));
          const focused = document.activeElement;
          const row = nodes[Number(focused.dataset.row)].id;
          const column = nodes[Number(focused.dataset.column)].id;
          const expected = level.cells.map((index) => A.cells[index])
            .filter((cell) => groups.get(cell.source_id) === row
              && groups.get(cell.target_id) === column)
            .map((cell) => `${byId.get(cell.source_id)} → ${byId.get(cell.target_id)} · `
              + `${R.countLabel(cell.import_sites, 'site')} · Core ${cell.status}`);
          return {heading: d.querySelector('h3')?.textContent, rows,
            expected, real: rows.every((row) =>
              [...names].some((name) => row.startsWith(name + ' · ')))};
        })()""")
        assert " imports " in detail["heading"]
        assert summary["name"].startswith(detail["heading"] + ": ")
        assert len(detail["rows"]) == summary["count"]
        assert detail["real"]
        assert detail["rows"] == detail["expected"]
        click(page, ".atlas-matrix-close")
        page.wait("!document.querySelector('.atlas-matrix-dialog')")
        assert page.evaluate("!!document.querySelector('#flow [data-open-matrix]')")
        click(page, "#flow .flow-fullscreen")
        page.wait("!!document.querySelector('#flow').dataset.expanded")
        assert not page.evaluate("!!document.querySelector('#flow .flow-matrix')")
        click(page, "#flow [data-open-matrix]")
        assert page.evaluate("document.querySelector('.atlas-matrix-dialog').open")
        click(page, ".atlas-matrix-close")
        click(page, "#flow .flow-fullscreen")
        page.wait("!document.querySelector('#flow').dataset.expanded")


@pytest.mark.parametrize("width", [1440, 390])
def test_small_level_keeps_a_selectable_matrix(site: str, tmp_path: Path, width: int) -> None:
    with browser(tmp_path / "profile", width=width, height=844) as page:
        if width < 500:
            page.send(
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=844,
                deviceScaleFactor=1,
                mobile=True,
            )
            page.send("Emulation.setTouchEmulationEnabled", enabled=True)
        page.open(f"{site}/system.html?scope=PART%3Ashell")
        page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        page.wait("!!document.querySelector('#flow .matrix-cell')")
        assert page.evaluate("document.querySelectorAll('#flow .matrix-label').length") > 0
        page.evaluate("""document.querySelector('#flow .matrix-cell')
          .dispatchEvent(new MouseEvent('click', {bubbles:true}))""")
        assert "Observed import cell" in page.evaluate(
            "document.querySelector('#flow .flow-inspector-content').textContent"
        )
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        if width < 500:
            assert page.evaluate("!document.querySelector('#flow .ak-drawer')")
