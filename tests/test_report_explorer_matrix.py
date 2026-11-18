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
        assert page.evaluate("!!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("""(() => {
          const view = document.querySelector('.atlas-matrix-view');
          return view.parentElement.matches('.flow-map-column')
            && getComputedStyle(document.querySelector('.flow-canvas')).display === 'none'
            && !document.querySelector('dialog[open]');
        })()""")
        assert page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-view');
          const guide = d.querySelector('details');
          return !guide.open && guide.textContent.includes('empty position')
            && d.textContent.includes('Rows import columns.')
            && d.textContent.includes('UNKNOWN');
        })()""")
        click(page, ".atlas-matrix-view summary")
        assert page.evaluate("document.querySelector('.atlas-matrix-view details').open")
        click(page, ".atlas-matrix-view summary")
        page.settle()
        summary = page.evaluate("""(() => {
          const d = document.querySelector('.atlas-matrix-view');
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
        click(page, "[data-diagram-view]")
        page.wait("!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("!!document.querySelector('#flow [data-open-matrix]')")
        click(page, "#flow .flow-fullscreen")
        page.wait("!!document.querySelector('#flow').dataset.expanded")
        assert not page.evaluate("!!document.querySelector('#flow .flow-matrix')")
        click(page, "[data-matrix-view]")
        assert page.evaluate("!!document.querySelector('.atlas-matrix-view')")
        click(page, "[data-diagram-view]")
        click(page, "#flow .flow-fullscreen")
        page.wait("!document.querySelector('#flow').dataset.expanded")


@pytest.mark.parametrize("width", [1260, 390])
def test_foundation_matrix_keeps_module_relationships(
    site: str, tmp_path: Path, width: int
) -> None:
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
        page.open(f"{site}/system.html?scope=LAYER%3APART%3Acore%3Afoundation")
        page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        click(page, "#flow [data-open-matrix]")
        summary = page.evaluate("""(() => {
          const R = ArchkeelFlow.reportScene;
          const level = R.atlas.levels.find((x) => x.parent_id === 'LAYER:PART:core:foundation');
          const buttons = [...document.querySelectorAll('.atlas-matrix-table td button')];
          return {modules: R.atlasModules(level, 'diagram').length, observed: level.cells.length,
            rows: document.querySelectorAll('.atlas-matrix-table tbody th').length,
            cells: buttons.length, single: buttons.every((button) => button.dataset.cell)};
        })()""")
        assert summary == {"modules": 47, "observed": 103, "rows": 47, "cells": 103, "single": True}
        if width < 500:
            point = page.evaluate("""(() => {
              const cell = document.querySelector('.atlas-matrix-table button[data-cell]');
              cell.scrollIntoView({block:'center', inline:'center'});
              const r = cell.getBoundingClientRect();
              const x = r.x + r.width / 2, y = r.y + r.height / 2;
              return {x, y, hit: document.elementFromPoint(x, y) === cell};
            })()""")
            assert point.pop("hit"), point
            page.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=[point])
            page.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        else:
            click(page, ".atlas-matrix-table button[data-cell]")
        page.wait("!document.querySelector('.atlas-matrix-detail').hidden")
        assert page.evaluate("document.querySelectorAll('.atlas-matrix-detail li').length") == 1
        assert "Observed import cell" in page.evaluate(
            "document.querySelector('#flow .flow-inspector-content').textContent"
        )
        selected = page.evaluate("ArchkeelFlow.state().cell")
        assert selected is not None
        click(page, ".atlas-matrix-back")
        assert page.evaluate("!document.querySelector('.atlas-matrix-grid').hidden")
        click(page, "[data-diagram-view]")
        page.wait("!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("ArchkeelFlow.state().scope") == "LAYER:PART:core:foundation"
        assert page.evaluate("ArchkeelFlow.state().cell") == selected


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
        click(page, "[data-diagram-view]")
        page.wait("!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        click(page, "[data-matrix-view]")
        click(page, ".atlas-matrix-table th[scope=row] button[data-module]")
        page.wait("!document.querySelector('.atlas-matrix-view')")
        assert "Observed module" in page.evaluate(
            "document.querySelector('#flow .flow-inspector-content').textContent"
        )


def test_touch_matrix_has_room_with_fact_sheet_open(site: str, tmp_path: Path) -> None:
    with browser(tmp_path / "profile", width=390, height=844) as page:
        page.send(
            "Emulation.setDeviceMetricsOverride",
            width=390,
            height=844,
            deviceScaleFactor=1,
            mobile=True,
        )
        page.send("Emulation.setTouchEmulationEnabled", enabled=True)
        page.open(f"{site}/system.html?scope=PART%3Ashell")
        if (
            page.evaluate(
                "document.querySelector('.flow-details-toggle').getAttribute('aria-expanded')"
            )
            != "true"
        ):
            click(page, ".flow-details-toggle")
        page.evaluate("document.querySelector('#flow [data-drawer=overview]').click()")
        click(page, "#flow [data-open-matrix]")
        assert page.evaluate("document.querySelector('.atlas-matrix-grid').clientHeight") >= 150
        point = page.evaluate("""(() => {
          const cells = document.querySelectorAll('.atlas-matrix-table button[data-cell]');
          const cell = [...cells].at(-1);
          cell.scrollIntoView({block:'center', inline:'center'});
          const grid = cell.closest('.atlas-matrix-grid');
          const row = grid.querySelector(`th[data-row="${cell.dataset.row}"]`)
            .getBoundingClientRect();
          const col = grid.querySelector(`th[data-column="${cell.dataset.column}"]`)
            .getBoundingClientRect();
          const r = cell.getBoundingClientRect();
          const x = r.x + r.width / 2, y = r.y + r.height / 2;
          return {x, y, hit: document.elementFromPoint(x, y) === cell,
            axesVisible: col.top >= 0 && col.bottom <= innerHeight
              && col.left >= row.right - 1 && col.right <= innerWidth
              && row.top >= col.bottom - 1 && row.bottom <= innerHeight
              && r.top >= col.bottom - 1 && r.bottom <= innerHeight};
        })()""")
        assert point.pop("axesVisible"), point
        assert point.pop("hit"), point
        page.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=[point])
        page.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        page.wait("!document.querySelector('.atlas-matrix-detail').hidden")
        click(page, ".atlas-matrix-back")
        click(page, "[data-diagram-view]")
        assert page.evaluate("ArchkeelFlow.state().scope") == "PART:shell"


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
        assert page.evaluate("!!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
        assert page.evaluate("""(() => {
          const grid = document.querySelector('.atlas-matrix-grid');
          const dialog = document.querySelector('.atlas-matrix-view');
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
        click(page, "[data-diagram-view]")
        page.wait("!document.querySelector('.atlas-matrix-view')")
        assert page.evaluate("!document.querySelector('#flow .flow-inspector').hidden")
