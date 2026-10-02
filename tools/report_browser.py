# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small browser acceptance pass over the report demo catalog."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError as error:
    raise SystemExit("Playwright is missing; run `make browser-install` first.") from error

from fixtures.architecture_demo import replay

WIDE_MODULES = {
    "shop.store.backend.tasks",
    *(
        f"shop.store.backend.tasks.{name}"
        for name in (
            "alpha",
            "bravo",
            "charlie",
            "delta",
            "echo",
            "foxtrot",
            "isolated",
            "source",
            "target",
        )
    ),
}


def _make_reports(output: Path) -> dict[str, Path]:
    cases = {
        "tour": ("tour", 2),
        "clean": ("clean", 0),
        "wide": ("class-a-recursive-wide-package", 0),
        "deep": ("class-a-recursive-inside-violation", 2),
        "mixed": ("class-a-boundary-types-mixed-evidence", 2),
        "unknown": ("class-a-boundary-types-ordinary-reexport-chain-unknown", 0),
        "known": ("validation-baseline-subject-order", 0),
        "target-present": ("target-module-present", 0),
        "target-absent": ("target-module-absent", 0),
        "target-store": ("target-hierarchy-positive", 0),
        "empty-responsibility": ("target-empty-responsibilities", 0),
    }
    reports = {}
    for name, (variant, expected_exit) in cases.items():
        report = output / f"{name}.json"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            actual_exit = replay(variant, report)
        assert actual_exit == expected_exit, (
            f"{variant}: exit {actual_exit}, expected {expected_exit}\n"
            f"{stdout.getvalue()}\n{stderr.getvalue()}"
        )
        html = report.with_name(f"{name}.report.html")
        assert html.is_file(), f"{variant} did not produce {html}"
        reports[name] = html
    return reports


def _flow(page: Page) -> dict[str, object]:
    return json.loads(page.locator("#flow-data").text_content() or "{}")


def _target_component_route(
    nodes: list[dict[str, object]], target_id: str, route: tuple[str, ...] = ()
) -> tuple[str, ...] | None:
    for node in nodes:
        current = (*route, str(node["id"])) if node["kind"] == "component" else route
        if node["id"] == target_id:
            return route
        children = node["children"]
        if isinstance(children, list):
            found = _target_component_route(children, target_id, current)
            if found is not None:
                return found
    return None


def _walk_target_nodes(node: dict[str, object]):
    yield node
    children = node["children"]
    if isinstance(children, list):
        for child in children:
            yield from _walk_target_nodes(child)


def _stat(page: Page, label: str) -> str:
    return page.locator(".flow-inspector .kv").evaluate(
        "(list, label) => { const terms = [...list.querySelectorAll('dt')]; "
        "const term = terms.find(item => item.textContent === label); "
        "return term ? term.nextElementSibling.textContent : ''; }",
        label,
    )


def _click_card(page: Page, label: str) -> None:
    page.locator(f'.flow-alternative [data-flow-card="{label}"]').first.click()


def _show_details(page: Page) -> None:
    toggle = page.locator(".flow-details-toggle")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def _open_selected(page: Page) -> None:
    button = page.locator(".flow-open-selected")
    assert button.is_enabled(), "The selected item has no drill destination"
    button.click()


def _return_to_root(page: Page) -> None:
    crumbs = page.locator(".flow-breadcrumb button")
    if crumbs.count() > 1:
        crumbs.first.click()


def _check_wide_navigation(page: Page) -> None:
    _return_to_root(page)
    page.get_by_role("button", name="Structure").click()
    _show_details(page)
    for label in ("store", "backend", "tasks"):
        _click_card(page, label)
    modules = _flow(page)["modules"]
    observed = {name for name in modules if name.startswith("shop.store.backend.tasks")}
    assert observed == WIDE_MODULES, f"task module inventory differs: {observed ^ WIDE_MODULES}"
    assert (
        _stat(page, "Modules shown / in this scope") == f"{len(WIDE_MODULES)}/{len(WIDE_MODULES)}"
    )

    for name in sorted(WIDE_MODULES):
        leaf = name.split(".")[-1]
        label = (
            name
            if name
            in {
                "shop.store.backend.tasks",
                "shop.store.backend.tasks.isolated",
            }
            else leaf
        )
        _click_card(page, label)
        if label != name:
            _click_card(page, name)
        actual = page.locator(".flow-inspector h2").text_content()
        assert actual == name, f"opening {name} from card {label} showed {actual!r}"
        page.locator(".flow-back").click()
        if label != name:
            page.locator(".flow-back").click()


def _check_projection_navigation(page: Page) -> None:
    actual = page.locator('[data-flow-view="actual"]')
    actual.focus()
    page.keyboard.press("Enter")
    assert actual.get_attribute("aria-pressed") == "true"
    _return_to_root(page)
    for identifier, title in (
        ("shop", "shop"),
        ("shop.store", "store"),
        ("shop.store.backend", "backend"),
        ("shop.store.backend.tasks", "tasks"),
    ):
        page.locator(f'.flow-alternative [data-projection-id="{identifier}"]').focus()
        page.keyboard.press("Enter")
        assert page.locator(".flow-projection h2").text_content() == title
        assert page.evaluate("document.activeElement.tagName") != "BODY"
    page.locator('.flow-alternative [data-projection-id="shop.store.backend.tasks.alpha"]').focus()
    page.keyboard.press("Enter")
    assert page.locator(
        '[data-projection-id="shop.store.backend.tasks.alpha"][aria-pressed="true"]'
    ).is_visible()
    _show_details(page)
    assert page.get_by_role("heading", name="alpha", exact=True).is_visible()
    assert page.evaluate("document.activeElement.tagName") != "BODY"
    page.locator(".flow-breadcrumb").get_by_role("button", name="store", exact=True).click()
    assert page.locator(".flow-projection h2").text_content() == "store"
    assert page.evaluate("document.activeElement.tagName") != "BODY"
    _return_to_root(page)
    assert page.locator(".flow-projection h2").text_content() == "Observed modules"
    assert page.evaluate("document.activeElement.tagName") != "BODY"
    for mode, title in (("Diff", "Differences"), ("Actual", "Observed modules")):
        button = page.locator(f'[data-flow-view="{mode.lower()}"]')
        button.click()
        assert button.get_attribute("aria-pressed") == "true"
        assert page.locator(".flow-projection h2").text_content() == title
        assert page.locator(".flow-canvas").is_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def _check_target_navigation(page: Page, output: Path, width: int) -> None:
    target = page.locator('[data-flow-view="target"]')
    target.click()
    _return_to_root(page)
    _show_details(page)
    canvas = page.locator(".flow-canvas")
    assert canvas.is_visible()
    assert page.locator(".flow-diagram-filter").first.is_hidden()
    root_graph = _flow(page)["explorers"]["target_diagrams"]["root"]
    assert page.locator(".flow-nodes .node").count() == len(root_graph["nodes"])
    if width == 375:
        # Readable 100% diagrams scroll inside the canvas, never outside the page.
        assert page.locator(".flow-zoom-value").text_content() == "100%"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    root_labels = set(
        page.locator(".flow-nodes .node").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-label'))"
        )
    )
    assert {"store", "shop"} <= root_labels
    page.screenshot(path=str(output / f"target-root-{width}.png"), full_page=False)

    for label in ("store", "backend", "tasks", "source"):
        node = page.locator(f'.flow-nodes .node[data-label="{label}"]').first
        assert node.is_visible(), f"Target node {label!r} is not reachable"
        node.click()
        _open_selected(page)
        if label == "store":
            if width == 1440:
                page.get_by_role("button", name="Fit overview").click()
                page.screenshot(path=str(output / "target-store-1440.png"), full_page=False)
                page.get_by_role("button", name="Set zoom to 100%").click()
            requirement = page.locator(".flow-edges .target-edge.requires").first
            line = requirement.locator(".line")
            line.evaluate("element => element.scrollIntoView({block: 'center', inline: 'center'})")
            path_state = line.evaluate(
                """element => ({
                  length: element.getTotalLength(),
                  stroke: getComputedStyle(element).stroke,
                  display: getComputedStyle(element).display,
                  visibility: getComputedStyle(element).visibility,
                })"""
            )
            assert path_state["length"] > 0, path_state
            assert path_state["stroke"] != "none" and path_state["display"] != "none", path_state
            assert path_state["visibility"] == "visible", path_state
            point = requirement.evaluate(
                """group => {
                  const path = group.querySelector('.line');
                  const length = path.getTotalLength();
                  const matrix = path.getScreenCTM();
                  for (let fraction = 0.15; fraction <= 0.85; fraction += 0.05) {
                    const local = path.getPointAtLength(length * fraction);
                    const screen = new DOMPoint(local.x, local.y).matrixTransform(matrix);
                    const hit = document.elementFromPoint(screen.x, screen.y);
                    if (hit?.closest('[data-target-edge]') === group) {
                      return {x: screen.x, y: screen.y};
                    }
                  }
                  return null;
                }"""
            )
            assert point is not None, "No unambiguous visible point on the requirement edge"
            page.mouse.click(point["x"], point["y"])
            assert page.locator(".flow-inspector").get_by_text("Rationale").is_visible()
            requirement.focus()
            page.keyboard.press("Enter")
            assert page.locator(".flow-inspector").get_by_text("Rationale").is_visible()
    assert page.locator(".flow-inspector").is_visible()
    package_scope = page.get_by_role("button", name="shop.store.backend.tasks.source", exact=True)
    assert package_scope.is_visible()
    package_scope.press("Enter")
    assert "shop.store.backend.tasks.source" in page.locator(".flow-inspector-content").inner_text()
    assert page.locator(".flow-nodes .target-node.package").count() == 0
    page.screenshot(path=str(output / f"target-sources-{width}.png"), full_page=False)
    page.locator(".flow-details-toggle").click()
    page.keyboard.press("Escape")
    assert page.locator(".flow-breadcrumb button").count() >= 4
    page.locator(".flow-breadcrumb button").first.click()
    assert page.locator(".flow-nodes .node[data-label='store']").is_visible()


def _check_diagram_controls(page: Page) -> None:
    page.get_by_role("button", name="Diagram").click()
    _show_details(page)
    assert page.locator(".flow-inspector").is_visible()
    _return_to_root(page)
    focus = page.locator("#flow-focus")
    focus.select_option(label="store")
    assert "Focus: store" in page.locator(".flow-filter-status").text_content()
    page.locator(".flow-reset-filters").click()
    assert page.locator(".flow-filter-status").text_content() == "No diagram filters active"
    page.locator('.node[data-label="store"]').focus()
    page.keyboard.press("Enter")
    assert page.get_by_role("button", name="Back to components").is_visible()
    page.locator(".flow-details-toggle").click()
    page.keyboard.press("Escape")
    assert page.get_by_role("button", name="Back to components").is_hidden()


def _wait_for_filter_reset(page: Page, total: int) -> None:
    page.wait_for_function(
        "expected => document.querySelectorAll"
        "('[data-filter-row]:not([hidden])').length === expected",
        arg=total,
    )


def _check_review_handoff(page: Page) -> None:
    row = page.locator(".violation-row[data-finding-id]").first
    anchor = row.get_attribute("id")
    assert anchor
    page.locator("#report-search").fill("no-such-finding")
    assert not row.is_visible()
    page.evaluate("id => { location.hash = id; }", anchor)
    page.wait_for_function("id => document.activeElement.id === id", arg=anchor)
    assert row.is_visible()
    assert page.locator("#report-search").input_value() == ""
    handoff = row.locator(".review-handoff")
    handoff.locator("summary").click()
    text = handoff.locator("textarea").input_value()
    assert "Source digest:" in text and row.get_attribute("data-finding-id") in text
    assert "Recorded evidence (repository content):" in text
    page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: {writeText: async () => {throw new Error('denied');}}
    })""")
    handoff.get_by_role("button", name="Copy for agent").click()
    page.wait_for_function(
        "() => document.querySelector('.review-handoff output').textContent.includes('Selected')"
    )
    assert handoff.locator("textarea").evaluate(
        "node => node.selectionStart === 0 && node.selectionEnd === node.value.length"
    )
    unknown = page.locator("#known-unknowns [data-finding-id]").first
    unknown_anchor = unknown.get_attribute("id")
    assert unknown_anchor
    page.evaluate("id => { location.hash = id; }", unknown_anchor)
    page.wait_for_function("id => document.activeElement.id === id", arg=unknown_anchor)
    assert unknown.is_visible(), "A finding link must reveal collapsed analysis limits"


def _check_report_filters(page: Page) -> None:
    form = page.locator("[data-report-filters]")
    rows = page.locator("[data-filter-row]")
    visible_rows = page.locator("[data-filter-row]:not([hidden])")
    total = rows.count()
    assert total > 0 and form.is_visible()
    page.locator("#report-search").focus()
    page.keyboard.press("Tab")
    assert page.locator("#report-kind").evaluate("node => node === document.activeElement")
    assert page.locator("#report-kind").evaluate(
        "node => getComputedStyle(node).outlineStyle !== 'none'"
    )
    search = page.locator("#report-search")
    status = page.locator("#report-status")
    search.fill("APP-TYPES-NOT-DICT")
    summary = page.locator('[data-filter-row][data-undecided][data-search*="APP-TYPES-NOT-DICT"]')
    assert summary.count() == 1
    for value in ("FAIL+UNKNOWN", "UNKNOWN"):
        status.select_option(value)
        assert summary.is_visible(), f"{value} hides mixed FAIL+UNKNOWN evidence"
        assert visible_rows.count() == 1
        assert page.locator("[data-filter-count]").text_content() == f"1 of {total} rows"
    form.get_by_role("button", name="Reset filters").click()
    assert search.input_value() == "" and status.input_value() == ""
    _wait_for_filter_reset(page, total)
    assert visible_rows.count() == total
    for field in ("kind", "component"):
        select = form.locator(f'select[name="{field}"]')
        value = select.locator("option").nth(1).get_attribute("value")
        assert value
        select.select_option(value)
        visible = visible_rows
        assert visible.count() > 0
        for row in visible.all():
            actual = row.get_attribute(f"data-{field}") or ""
            if field == "component":
                assert value in actual.split()
            else:
                assert actual == value
        form.get_by_role("button", name="Reset filters").click()
        _wait_for_filter_reset(page, total)
        assert visible_rows.count() == total
    overflowing = form.locator("input,select,button,label,output").evaluate_all(
        "nodes => nodes.filter(node => { const r = node.getBoundingClientRect(); "
        "return r.left < 0 || r.right > innerWidth; }).map(node => node.outerHTML)"
    )
    assert not overflowing, f"filter controls overflow viewport: {overflowing}"


def _check_status_colors(page: Page) -> None:
    fail = page.locator('[data-filter-row] strong[data-status="fail"]').first
    passed = page.locator('[data-filter-row] strong[data-status="pass"]').first
    assert fail.is_visible() and passed.is_visible()
    fail_color = fail.evaluate("node => getComputedStyle(node).color")
    pass_color = passed.evaluate("node => getComputedStyle(node).color")
    expected_fail = page.evaluate(
        "() => { const n = document.createElement('span'); "
        "n.style.color = 'var(--ck-fail)'; document.body.append(n); "
        "const c = getComputedStyle(n).color; n.remove(); return c; }"
    )
    expected_pass = page.evaluate(
        "() => { const n = document.createElement('span'); "
        "n.style.color = 'var(--ck-pass)'; document.body.append(n); "
        "const c = getComputedStyle(n).color; n.remove(); return c; }"
    )
    assert fail_color == expected_fail
    assert pass_color == expected_pass


def _check_unknown_color(page: Page) -> None:
    unknown = page.locator('[data-filter-row] strong[data-status="unknown"]').first
    assert unknown.is_visible()
    color = unknown.evaluate("node => getComputedStyle(node).color")
    expected = page.evaluate(
        "() => { const n = document.createElement('span'); "
        "n.style.color = 'var(--ck-unknown)'; document.body.append(n); "
        "const c = getComputedStyle(n).color; n.remove(); return c; }"
    )
    assert color == expected


def _check_violation_bar(page: Page) -> None:
    _return_to_root(page)
    page.get_by_role("button", name="Structure").click()
    for label in ("store", "backend", "tasks"):
        _click_card(page, label)
    page.get_by_role("button", name="Diagram").click()
    _show_details(page)
    toggle = page.locator("#flow-violations-only")
    toggle.check()
    heading = page.locator(".flow-inspector h3", has_text="Violating connections")
    assert heading.is_visible()
    rows = heading.locator("xpath=following-sibling::div[contains(@class, 'bars')]")
    violation = rows.locator('.row[data-state="violation"]').first
    assert violation.is_visible()
    bar = violation.locator(".track b")
    assert bar.is_visible()
    actual = bar.evaluate("node => getComputedStyle(node).backgroundColor")
    expected = page.evaluate(
        "() => { const n = document.createElement('span'); "
        "n.style.color = 'var(--ck-fail)'; document.body.append(n); "
        "const c = getComputedStyle(n).color; n.remove(); return c; }"
    )
    assert actual == expected, f"violation bar is {actual}, expected failure color {expected}"


def _visit(browser: Browser, report: Path, name: str, output: Path) -> tuple[Page, list[str]]:
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    try:
        page.goto(report.as_uri(), wait_until="load")
        page.screenshot(path=str(output / f"{name}-1440x1000.png"), full_page=True)
    except Exception:
        try:
            _finish(page, name, output)
        except Exception:
            pass
        raise
    return page, errors


def _finish(page: Page, name: str, output: Path) -> None:
    page.context.tracing.stop(path=str(output / f"{name}-trace.zip"))
    page.context.close()


def _check_no_javascript(browser: Browser, report: Path, output: Path) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, java_script_enabled=False)
    try:
        page.goto(report.as_uri(), wait_until="load")
        assert not page.locator(".flow-views").is_visible()
        assert page.locator(".flow-alternative").is_hidden()
        assert page.get_by_text("Observed module tree", exact=False).is_visible()
        assert not page.locator("[data-report-filters]").is_visible()
        assert page.locator('[data-filter-row][data-search*="APP-TYPES-NOT-DICT"]').count() > 0
        assert page.locator(
            '[data-filter-row][data-search*="APP-TYPES-NOT-DICT"]'
        ).first.is_visible()
        handoff = page.locator(".violation-row .review-handoff").first
        handoff.locator("summary").click()
        assert "Source digest:" in handoff.locator("textarea").input_value()
        assert handoff.locator("textarea").get_attribute("readonly") is not None
        assert not handoff.get_by_role("button", name="Copy for agent").is_visible()
        page.screenshot(path=str(output / "mixed-nojs-1440.png"), full_page=True)
    finally:
        page.close()


def _check_module_target_reports(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    for name, file in (("target-present", "orders.py"), ("target-absent", "missing.py")):
        page, errors = _visit(browser, reports[name], name, output)
        try:
            page.locator('[data-flow-view="target"]').click()
            _show_details(page)
            target = _flow(page)["explorers"]["target"]
            module = next(
                node
                for root in target
                for node in _walk_target_nodes(root)
                if node["kind"] == "module_target"
                and any(
                    detail["label"] == "File" and detail["value"] == f"shop/app/{file}"
                    for detail in node["details"]
                )
            )
            route = _target_component_route(target, module["id"])
            assert route is not None
            for component_id in route:
                page.locator(f'.flow-nodes .node[data-target-node="{component_id}"]').click()
                _open_selected(page)
            leaf = page.locator(f'.flow-nodes .node[data-target-node="{module["id"]}"]')
            assert leaf.is_visible()
            assert leaf.locator(".target-kind").text_content() == "MODULE"
            leaf.click()
            content = page.locator(".flow-inspector-content")
            assert content.get_by_text(f"shop/app/{file}", exact=True).is_visible()
            assert content.get_by_text("Coordinate order workflows.").is_visible()
            assert content.get_by_text("architecture-contract.json").is_visible()
            page.screenshot(path=str(output / f"{name}-drilldown.png"), full_page=False)
            if name == "target-present":
                page.set_viewport_size({"width": 1440, "height": 1300})
                page.get_by_role("button", name="Fit overview").click()
                page.locator("#flow").evaluate(
                    "element => element.scrollIntoView({block: 'start'})"
                )
                page.screenshot(path=str(output / "archkeel-module-target.png"), full_page=False)
            page.locator('[data-flow-view="diff"]').click()
            category = (
                "Absent declared targets"
                if name == "target-absent"
                else "Observed modules without a declared target"
            )
            category_id = "absent" if name == "target-absent" else "observed-only-targets"
            if name == "target-absent":
                assert page.locator(".flow-projection h2").text_content() == "missing"
                page.locator('[data-projection-id="diff:absent:shop.app.missing"]').click()
                _open_selected(page)
                page.locator(".flow-projection [data-projection-id]").filter(
                    has=page.get_by_text("shop/app/missing.py", exact=True)
                ).click()
                assert page.locator(".flow-projection h2").text_content() == category
                _show_details(page)
                assert (
                    page.locator('.flow-inspector-content [aria-label="Selected entry"]')
                    .get_by_role("heading", name="shop/app/missing.py", exact=True)
                    .is_visible()
                )
            _return_to_root(page)
            page.locator(f'.flow-alternative [data-projection-id="diff:{category_id}"]').click()
            _open_selected(page)
            assert page.locator(".flow-projection h2").text_content() == category
            if name == "target-absent":
                assert (
                    page.locator(".flow-projection").get_by_text("shop/app/missing.py").is_visible()
                )
            page.screenshot(path=str(output / f"{name}-diff.png"), full_page=False)
            assert not errors, f"{name} JavaScript errors: {errors}"
        finally:
            _finish(page, name, output)


def _capture_readme_assets(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    tour, errors = _visit(browser, reports["tour"], "readme-tour", output)
    try:
        tour.evaluate("() => document.fonts.ready")
        tour.get_by_role("button", name="Diagram").click()
        focus = tour.locator("#flow-focus")
        focus.select_option(label="app")
        tour.locator("#flow-violations-only").check()
        _show_details(tour)
        tour.get_by_role("button", name="Fit overview").click()
        tour.locator("#flow").screenshot(path=str(output / "archkeel-component-flow.png"))
        assert not errors, f"tour JavaScript errors: {errors}"
    finally:
        _finish(tour, "readme-tour", output)

    clean, errors = _visit(browser, reports["clean"], "readme-clean", output)
    try:
        clean.evaluate("() => document.fonts.ready")
        clean.set_viewport_size({"width": 1440, "height": 1400})
        clean.get_by_role("button", name="Diagram").click()
        focus = clean.locator("#flow-focus")
        focus.select_option(value="")
        clean.locator("#flow-violations-only").uncheck()
        assert clean.locator("#flow-threshold-input").input_value() == "0"
        _show_details(clean)
        clean.get_by_role("button", name="Fit overview").click()
        clean.locator("#flow").screenshot(path=str(output / "archkeel-shop-components.png"))
        clean.set_viewport_size({"width": 1440, "height": 1000})
        clean.locator('.flow-nodes .node[data-label="store"]').click()
        _open_selected(clean)
        clean.get_by_role("button", name="Fit overview").click()
        clean.locator("#flow").screenshot(path=str(output / "archkeel-shop-store-inside.png"))
        assert not errors, f"clean JavaScript errors: {errors}"
    finally:
        _finish(clean, "readme-clean", output)

    preview, errors = _visit(browser, reports["tour"], "readme-preview", output)
    try:
        preview.evaluate("() => document.fonts.ready")
        preview.screenshot(path=str(output / "archkeel-report-preview.png"), full_page=False)
        assert not errors, f"tour JavaScript errors: {errors}"
    finally:
        _finish(preview, "readme-preview", output)

    evidence, errors = _visit(browser, reports["mixed"], "readme-evidence", output)
    try:
        evidence.evaluate("() => document.fonts.ready")
        evidence.locator("#report-search").fill("APP-TYPES-NOT-DICT")
        evidence.locator("#report-status").select_option("UNKNOWN")
        row = evidence.locator(
            '[data-filter-row][data-undecided][data-search*="APP-TYPES-NOT-DICT"]'
        )
        assert row.count() == 1 and row.is_visible()
        row.locator("summary", has_text="Scope, decision and evidence").click()
        evidence.locator("[data-report-filters]").evaluate(
            "element => element.scrollIntoView({block: 'start'})"
        )
        evidence.screenshot(path=str(output / "archkeel-rule-evidence.png"), full_page=False)
        assert not errors, f"mixed JavaScript errors: {errors}"
    finally:
        _finish(evidence, "readme-evidence", output)

    target, errors = _visit(browser, reports["target-store"], "readme-target-store", output)
    try:
        target.evaluate("() => document.fonts.ready")
        target.locator('[data-flow-view="target"]').click()
        _show_details(target)
        target.locator('.flow-nodes .node[data-label="store"]').click()
        _open_selected(target)
        target.get_by_role("button", name="Fit overview").click()
        target.locator("#flow").screenshot(path=str(output / "archkeel-target-store.png"))
        assert not errors, f"target hierarchy JavaScript errors: {errors}"
    finally:
        _finish(target, "readme-target-store", output)

    empty, errors = _visit(
        browser, reports["empty-responsibility"], "readme-empty-responsibility", output
    )
    try:
        empty.evaluate("() => document.fonts.ready")
        empty.locator('[data-flow-view="target"]').click()
        _show_details(empty)
        empty.locator('.flow-nodes .node[data-label="store"]').click()
        _open_selected(empty)
        api = empty.locator('.flow-nodes .node[data-label="api"]')
        assert api.count() == 1
        api.click()
        assert (
            empty.locator(".flow-selected-responsibility")
            .get_by_text("No declared responsibility.", exact=True)
            .is_visible()
        )
        empty.locator(".flow-responsibilities summary").click()
        empty.get_by_role("button", name="Fit overview").click()
        empty.locator("#flow").screenshot(path=str(output / "archkeel-empty-responsibility.png"))
        assert not errors, f"empty responsibility JavaScript errors: {errors}"
    finally:
        _finish(empty, "readme-empty-responsibility", output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("OUTPUT", "test-artifacts/report-browser")),
    )
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports = _make_reports(output)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL"),
        )
        wide, wide_errors = _visit(browser, reports["wide"], "wide", output)
        try:
            _check_wide_navigation(wide)
            _check_projection_navigation(wide)
            _check_target_navigation(wide, output, 1440)
            _check_diagram_controls(wide)
            assert not wide_errors, f"wide JavaScript errors: {wide_errors}"
            wide.set_viewport_size({"width": 375, "height": 844})
            _check_target_navigation(wide, output, 375)
            _check_projection_navigation(wide)
            wide.screenshot(path=str(output / "actual-375.png"), full_page=False)
            wide.locator('[data-flow-view="diff"]').click()
            wide.screenshot(path=str(output / "diff-375.png"), full_page=False)
            _check_wide_navigation(wide)
            _check_diagram_controls(wide)
            _return_to_root(wide)
            assert wide.evaluate("document.documentElement.scrollWidth <= innerWidth")
            wide.screenshot(path=str(output / "wide-375x2400.png"), full_page=True)
            assert not wide_errors, f"mobile wide JavaScript errors: {wide_errors}"
            for width in (1440, 375):
                name = f"mixed-{width}"
                mixed, mixed_errors = _visit(browser, reports["mixed"], name, output)
                try:
                    mixed.set_viewport_size({"width": width, "height": 1000})
                    _check_review_handoff(mixed)
                    _check_report_filters(mixed)
                    _check_status_colors(mixed)
                    assert not mixed_errors, f"mixed JavaScript errors: {mixed_errors}"
                    mixed.screenshot(path=str(output / f"{name}.png"), full_page=True)
                finally:
                    _finish(mixed, name, output)
            _check_no_javascript(browser, reports["mixed"], output)
            deep, deep_errors = _visit(browser, reports["deep"], "deep", output)
            try:
                assert deep.locator(
                    '[data-filter-row][data-search*="DEEP-REQUIRES-COMPLETE"]'
                ).count()
                for width in (1440, 375):
                    deep.set_viewport_size({"width": width, "height": 1200})
                    _check_violation_bar(deep)
                    assert deep.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    deep.screenshot(path=str(output / f"deep-{width}.png"), full_page=True)
                assert not deep_errors, f"deep JavaScript errors: {deep_errors}"
            finally:
                _finish(deep, "deep", output)
            unknown, unknown_errors = _visit(browser, reports["unknown"], "unknown", output)
            try:
                assert unknown.locator('[data-filter-row][data-status="UNKNOWN"]').count()
                _check_unknown_color(unknown)
                unknown.locator('[data-flow-view="diff"]').click()
                unknown.locator('[data-projection-id="diff:unknowns"]').click()
                _open_selected(unknown)
                rows = unknown.locator(".flow-projection [data-projection-id]")
                assert rows.count() > 0, "UNKNOWN records are missing from Diff navigation"
                rows.first.click()
                _show_details(unknown)
                assert unknown.locator(
                    '.flow-inspector-content [aria-label="Selected entry"]'
                ).is_visible()
                assert not unknown_errors, f"unknown JavaScript errors: {unknown_errors}"
            finally:
                _finish(unknown, "unknown", output)
            known, known_errors = _visit(browser, reports["known"], "known", output)
            try:
                assert known.locator(".known-badge").first.is_visible()
                assert not known_errors, f"known JavaScript errors: {known_errors}"
            finally:
                _finish(known, "known", output)
            _check_module_target_reports(browser, reports, output)
            _capture_readme_assets(browser, reports, output)
        finally:
            _finish(wide, "wide", output)
            browser.close()
    print(f"Browser acceptance artifacts: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
