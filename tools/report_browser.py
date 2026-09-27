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
        "wide": ("class-a-recursive-wide-package", 0),
        "deep": ("class-a-recursive-inside-violation", 2),
        "mixed": ("class-a-boundary-types-mixed-evidence", 2),
        "unknown": ("class-a-boundary-types-ordinary-reexport-chain-unknown", 0),
        "known": ("validation-baseline-subject-order", 0),
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


def _stat(page: Page, label: str) -> str:
    return page.locator(".flow-inspector .kv").evaluate(
        "(list, label) => { const terms = [...list.querySelectorAll('dt')]; "
        "const term = terms.find(item => item.textContent === label); "
        "return term ? term.nextElementSibling.textContent : ''; }",
        label,
    )


def _click_card(page: Page, label: str) -> None:
    page.locator(f'.flow-alternative [data-flow-card="{label}"]').first.click()


def _return_to_root(page: Page) -> None:
    crumbs = page.locator(".flow-breadcrumb button")
    if crumbs.count() > 1:
        crumbs.first.click()


def _check_wide_navigation(page: Page) -> None:
    _return_to_root(page)
    page.get_by_role("button", name="Structure").click()
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


def _check_diagram_controls(page: Page) -> None:
    _return_to_root(page)
    page.get_by_role("button", name="Diagram").click()
    focus = page.locator("#flow-focus")
    focus.select_option(label="store")
    assert "Focus: store" in page.locator(".flow-filter-status").text_content()
    page.locator(".flow-reset-filters").click()
    assert page.locator(".flow-filter-status").text_content() == "No diagram filters active"
    page.locator('.node[data-label="store"]').focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    assert page.get_by_role("button", name="Back to components").is_visible()
    page.keyboard.press("Escape")
    assert page.get_by_role("button", name="Back to components").is_hidden()


def _wait_for_filter_reset(page: Page, total: int) -> None:
    page.wait_for_function(
        "expected => document.querySelectorAll"
        "('[data-filter-row]:not([hidden])').length === expected",
        arg=total,
    )


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
        assert not page.locator("[data-report-filters]").is_visible()
        assert page.locator('[data-filter-row][data-search*="APP-TYPES-NOT-DICT"]').count() > 0
        assert page.locator(
            '[data-filter-row][data-search*="APP-TYPES-NOT-DICT"]'
        ).first.is_visible()
        page.screenshot(path=str(output / "mixed-nojs-1440.png"), full_page=True)
    finally:
        page.close()


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
            _check_diagram_controls(wide)
            assert not wide_errors, f"wide JavaScript errors: {wide_errors}"
            wide.set_viewport_size({"width": 375, "height": 2400})
            _check_wide_navigation(wide)
            _check_diagram_controls(wide)
            _return_to_root(wide)
            assert wide.evaluate("document.documentElement.scrollWidth <= innerWidth")
            wide.screenshot(path=str(output / "wide-375x2400.png"), full_page=True)
            for width in (1440, 375):
                name = f"mixed-{width}"
                mixed, mixed_errors = _visit(browser, reports["mixed"], name, output)
                try:
                    mixed.set_viewport_size({"width": width, "height": 1000})
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
                assert not unknown_errors, f"unknown JavaScript errors: {unknown_errors}"
            finally:
                _finish(unknown, "unknown", output)
            known, known_errors = _visit(browser, reports["known"], "known", output)
            try:
                assert known.locator(".known-badge").first.is_visible()
                assert not known_errors, f"known JavaScript errors: {known_errors}"
            finally:
                _finish(known, "known", output)
        finally:
            _finish(wide, "wide", output)
            browser.close()
    print(f"Browser acceptance artifacts: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
