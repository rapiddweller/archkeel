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
      const x = r.x + r.width / 2, y = r.y + r.height / 2;
      const hit = document.elementFromPoint(x, y);
      return {{x, y, hit: hit?.outerHTML.slice(0, 200), expected: e.outerHTML.slice(0, 200),
        matches: e === hit || e.contains(hit)}};
    }})()""")
    assert point.pop("matches"), point
    point.pop("hit")
    point.pop("expected")
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
        assert page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-dialog');
          const guide = d.querySelector('details');
          return !guide.open && guide.textContent.includes('empty position')
            && d.textContent.includes('Rows import columns.')
            && d.textContent.includes('UNKNOWN');
        })()""")
        click(page, ".atlas-matrix-dialog summary")
        assert page.evaluate("document.querySelector('.atlas-matrix-dialog details').open")
        click(page, ".atlas-matrix-dialog summary")
        page.settle()
        summary = page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-dialog');
          const cells = [...d.querySelectorAll('button[data-row]')];
          const labels = d.querySelectorAll('th[data-row], th[data-column]');
          const max = cells.reduce((a, b) => Number(a.textContent)
            > Number(b.textContent) ? a : b);
          max.focus();
          return {labels: labels.length, cells: cells.length,
            count: Number(max.textContent),
            name: max.getAttribute('aria-label'), fullscreen: !!document.fullscreenElement,
            row: max.dataset.row, column: max.dataset.column};
        })()""")
        assert 2 <= summary["labels"] < 1424
        assert 0 < summary["cells"] < 712 * 712
        assert not summary["fullscreen"]
        if width < 500:
            point = page.evaluate(f"""(() => {{
              const cell = document.querySelector(
                'button[data-row="{summary["row"]}"][data-column="{summary["column"]}"]');
              cell.scrollIntoView({{block: 'center', inline: 'center'}});
              cell.addEventListener('click', () => {{ window.matrixTouch = true; }},
                {{once: true}});
              const r = cell.getBoundingClientRect();
              const grid = cell.closest('.atlas-matrix-grid');
              const row = grid.querySelector(`th[data-row="${{cell.dataset.row}}"]`)
                .getBoundingClientRect();
              const column = grid.querySelector(`th[data-column="${{cell.dataset.column}}"]`)
                .getBoundingClientRect();
              const x = r.x + r.width / 2, y = r.y + r.height / 2;
              return {{x, y, hit: document.elementFromPoint(x, y) === cell,
                axesVisible: column.left >= row.right - 1
                  && column.right <= grid.getBoundingClientRect().right + 1}};
            }})()""")
            assert point["hit"], point
            assert point.pop("axesVisible"), point
            point.pop("hit")
            page.send(
                "Input.dispatchTouchEvent",
                type="touchStart",
                touchPoints=[{"x": point["x"], "y": point["y"]}],
            )
            page.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
            page.wait("window.matrixTouch === true")
        else:
            assert page.evaluate("document.activeElement?.dataset.row") == summary["row"]
            page.press("Enter")
        page.wait("!document.querySelector('.atlas-matrix-detail').hidden", timeout=5)
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
          const row = nodes[Number(d.dataset.row)].id;
          const column = nodes[Number(d.dataset.column)].id;
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
        click(page, ".atlas-matrix-back")
        assert page.evaluate("!document.querySelector('.atlas-matrix-grid').hidden")
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
        page.open(f"{site}/system.html?scope=SHELL-ENTRY")
        page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        click(page, "#flow [data-open-matrix]")
        page.wait("!!document.querySelector('.atlas-matrix-table button[data-cell]')")
        assert page.evaluate("document.querySelectorAll('.atlas-matrix-table th').length") > 2
        assert page.evaluate("!!document.querySelector('.atlas-matrix-module wbr')")
        click(page, ".atlas-matrix-table button[data-cell]")
        assert "Observed import cell" in page.evaluate(
            "document.querySelector('#flow .flow-inspector-content').textContent"
        )
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        if width < 500:
            assert page.evaluate("!document.querySelector('#flow .ak-drawer')")
        click(page, ".atlas-matrix-back")
        click(page, ".atlas-matrix-close")
        page.wait("!document.querySelector('.atlas-matrix-dialog')")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        if not page.evaluate(
            "document.querySelector('#flow [data-open-matrix]').getClientRects().length > 0"
        ):
            page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        click(page, "#flow [data-open-matrix]")
        click(page, ".atlas-matrix-table th[scope=row] button[data-module]")
        page.wait("!document.querySelector('.atlas-matrix-dialog')")
        assert "Observed module" in page.evaluate(
            "document.querySelector('#flow .flow-inspector-content').textContent"
        )


def test_shell_matrix_opens_separately_with_fixed_axes(site: str, tmp_path: Path) -> None:
    with browser(tmp_path / "profile", width=1260, height=904) as page:
        page.open(f"{site}/system.html")
        click(page, '[data-ak-theme="light"]')
        page.evaluate("document.querySelector('#flow').scrollIntoView()")
        point = page.evaluate("""(() => {
          const node = document.querySelector('#flow [data-uml-id="PART:shell"]');
          const r = node.getBoundingClientRect();
          return {x:r.x + r.width / 2,y:r.y + r.height / 2};
        })()""")
        for count in (1, 2):
            for event in ("mousePressed", "mouseReleased"):
                page.send(
                    "Input.dispatchMouseEvent", type=event, button="left", clickCount=count, **point
                )
        page.wait("ArchkeelFlow.state().scope === 'PART:shell'")
        page.settle()
        if (
            page.evaluate(
                "document.querySelector('.flow-details-toggle').getAttribute('aria-expanded')"
            )
            != "true"
        ):
            click(page, ".flow-details-toggle")
        for _ in range(20):
            if (
                page.evaluate("parseInt(document.querySelector('.flow-zoom-value').textContent)")
                <= 28
            ):
                break
            click(page, ".flow-zoom-out")
        click(page, '#flow [data-drawer="overview"]')
        assert page.evaluate("!!document.querySelector('#flow [data-open-matrix]')")
        assert not page.evaluate("!!document.querySelector('#flow .flow-matrix')")
        click(page, "#flow [data-open-matrix]")
        assert page.evaluate("document.querySelector('.atlas-matrix-dialog').open")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        assert page.evaluate("""(() => {
          const grid = document.querySelector('.atlas-matrix-grid');
          const dialog = document.querySelector('.atlas-matrix-dialog');
          const cell = [...grid.querySelectorAll('button[data-row]')].at(-1);
          cell.scrollIntoView({block:'center', inline:'center'});
          const row = grid.querySelector(`th[data-row="${cell.dataset.row}"]`);
          const col = grid.querySelector(`th[data-column="${cell.dataset.column}"]`);
          const b = grid.getBoundingClientRect(), r = row.getBoundingClientRect();
          const c = col.getBoundingClientRect(), selected = cell.getBoundingClientRect();
          return grid.scrollLeft > 0 && grid.scrollTop > 0
            && r.left >= b.left && r.right <= b.right && c.top >= b.top && c.bottom <= b.bottom
            && c.left >= r.right && c.right <= b.right
            && selected.left >= r.right && selected.right <= b.right
            && selected.top >= c.bottom && selected.bottom <= b.bottom
            && row.scrollWidth <= row.clientWidth && col.scrollWidth <= col.clientWidth
            && dialog.scrollHeight <= dialog.clientHeight + 1;
        })()""")
        click(page, ".atlas-matrix-close")
        page.wait("!document.querySelector('.atlas-matrix-dialog')")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
