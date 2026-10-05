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

from archkeel.ir.graph_codec import parse_report
from archkeel.ir.model import RuleAssessment, RunResult
from archkeel.render.html import render_architecture_html
from fixtures.architecture_demo import replay


def _make_reports(output: Path) -> dict[str, Path]:
    cases = {
        "uml-match": ("uml-match", 0),
        "uml-complete": ("uml-complete", 0),
        "uml-dart": ("uml-dart", 0),
        "uml-typescript": ("uml-typescript", 0),
        "uml-mismatch": ("uml-mismatch", 2),
        "uml-partial": ("uml-partial", 0),
        "tour": ("tour", 2),
        "clean": ("clean", 0),
        "open": ("class-a-decision-open", 2),
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
        result = json.loads(stdout.getvalue().splitlines()[-1])
        (output / f"{name}.result.json").write_text(json.dumps(result, indent=2) + "\n")
        html = report.with_name(f"{name}.report.html")
        assert html.is_file(), f"{variant} did not produce {html}"
        reports[name] = html
    return reports


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


def _show_details(page: Page) -> None:
    toggle = page.locator(".flow-details-toggle")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def _check_graph_views(page: Page) -> None:
    payload = page.locator("#flow-data").text_content()
    report = parse_report(json.loads(payload or "{}"))
    assert report.observed is not None and report.target is not None
    for view in ("diagram", "target", "diff"):
        page.locator(f'[data-flow-view="{view}"]').click()
        assert page.locator(".flow-canvas").is_visible()
        nodes = page.locator(".flow-nodes [data-uml-id]")
        assert nodes.count() > 0
        assert page.locator(".flow-frames [tabindex],.flow-chips [tabindex]").count() == 0
        assert page.locator(".flow-edges .edge").evaluate_all("""edges => edges.every(edge => {
          const line = edge.querySelector('.line'), hit = edge.querySelector('.hit');
          return line.getAttribute('d') === hit.getAttribute('d')
            && getComputedStyle(line).markerEnd !== 'none';
        })""")
        assert nodes.evaluate_all("""nodes => nodes.every(node => {
          const card = node.querySelector('.card');
          return card && Number(card.getAttribute('width')) > 0
            && getComputedStyle(node.querySelector('.label')).writingMode === 'horizontal-tb';
        })""")
        for selector in ("html", ".flow-canvas", ".flow-inspector"):
            assert (
                page.locator(selector).evaluate("n => getComputedStyle(n).scrollbarWidth") == "none"
            )
        if nodes.count() > 1:
            nodes.first.press("Space")
            assert nodes.first.get_attribute("aria-pressed") == "true"
            _show_details(page)
            assert page.locator(".flow-inspector-content").inner_text()
        page.get_by_role("button", name="Fit overview").click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#flow-data").text_content() == payload


def _check_inner_uml(page: Page, name: str, output: Path) -> None:
    payload = page.locator("#flow-data").text_content()
    report = parse_report(json.loads(payload or "{}"))
    expected = {
        "uml-match": "PASS",
        "uml-complete": "UNKNOWN",
        "uml-mismatch": "FAIL",
        "uml-partial": "UNKNOWN",
        "uml-dart": "UNKNOWN",
        "uml-typescript": "UNKNOWN",
    }[name]
    assert report.comparison.status == expected
    language = next(e.language for e in report.target.entities if e.kind == "module")
    annotation = {"python": "str", "dart": "String", "typescript": "string"}[language]
    returns = "None" if language == "python" else "void"
    for view in ("diagram", "target", "diff"):
        page.reload(wait_until="load")
        page.locator(f'[data-flow-view="{view}"]').click()
        page.locator('.flow-nodes [data-label="demo"]').dblclick()
        if language != "python" and view == "diagram":
            assert not any(
                e.kind in {"class", "method", "function"} for e in report.observed.entities
            )
            page.locator('.flow-nodes [data-label="core"]').press("Space")
            _show_details(page)
            details = page.locator(".flow-inspector-content").inner_text()
            assert "Source file" in details and "Coverage" in details and "unavailable" in details
            page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-modules.png"))
            assert page.locator("#flow-data").text_content() == payload
            continue
        page.locator('.flow-nodes [data-label="core"]').dblclick()
        nodes = page.locator(".flow-nodes [data-uml-id]")
        assert {"class", "interface", "enum", "function"} <= set(
            nodes.evaluate_all("nodes => nodes.map(n => n.dataset.umlKind)")
        )
        edges = page.locator(".flow-edges .edge")
        assert edges.count() > 0
        assert nodes.evaluate_all("""nodes => {
          const boxes = nodes.map(n => n.querySelector('.card').getBoundingClientRect());
          return boxes.every((a, i) => boxes.slice(i + 1).every(b =>
            a.right <= b.left + 1 || b.right <= a.left + 1
            || a.bottom <= b.top + 1 || b.bottom <= a.top + 1));
        }""")
        assert edges.evaluate_all("""edges => edges.every(edge => {
          const line = edge.querySelector('.line'), hit = edge.querySelector('.hit');
          return line.getAttribute('d') === hit.getAttribute('d')
            && getComputedStyle(line).markerEnd !== 'none';
        })""")
        if name == "uml-complete":
            page.locator('.flow-nodes [data-label="describe"]').press("Space")
            related = page.locator(".flow-nodes .node.related").evaluate_all(
                "nodes => nodes.map(n => n.dataset.label)"
            )
            assert {"State", "VERSION"} <= set(related)
            assert (
                page.locator(
                    '.flow-edges .edge.related[data-relationship-kind="references"]'
                ).count()
                == 2
            )
            page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-internal-uses.png"))
        page.get_by_role("button", name="Member previews", exact=True).click()
        client = page.locator('.flow-nodes [data-label="Client"]')
        assert f"− _token: {annotation}" in client.text_content()
        assert client.locator(".uml-icon").count() > 0
        client.press("Space")
        page.mouse.move(0, 0)
        assert client.evaluate("n => n.classList.contains('selected')")
        assert page.locator(".flow-nodes .node.related").count() > 1
        assert page.locator(".flow-nodes .node.dim").count() > 0
        page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-core.png"))
        client.dblclick()
        reset = page.locator('.flow-nodes [data-label="reset"]')
        assert reset.get_attribute("data-uml-kind") == "method"
        assert (
            reset.locator(".label").evaluate("n => getComputedStyle(n).textDecorationLine")
            == "underline"
        )
        reset.press("Space")
        _show_details(page)
        assert f"+ reset(): {returns}" in page.locator(".flow-inspector-content").inner_text()
        page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-members.png"))
        page.locator(".flow-back").click()
        page.locator('.flow-nodes [data-label="State"]').dblclick()
        ready = page.locator('.flow-nodes [data-label="READY"][data-uml-kind="enum_literal"]')
        if name == "uml-partial" and view == "diagram":
            assert ready.count() == 0
            for kind in ("attribute", "binding"):
                assert (
                    page.locator(
                        f'.flow-nodes [data-label="READY"][data-uml-kind="{kind}"]'
                    ).count()
                    == 1
                )
        else:
            assert ready.count() == 1
            assert ready.locator(".stereotype").text_content() == "«enumeration literal»"
        page.locator(".flow-back").click()
        page.locator('.flow-nodes [data-label="build"]').dblclick()
        item = page.locator('.flow-nodes [data-label="item"]')
        assert item.get_attribute("data-uml-kind") == "binding"
        assert "Unit()" in item.text_content()
        assert page.locator('.flow-edges [data-relationship-kind="instance_of"]').count() > 0
        item.press("Space")
        _show_details(page)
        assert "live object" in page.locator(".flow-inspector-content").inner_text()
        assert page.locator("#flow-data").text_content() == payload


def _check_wide_inventory(page: Page) -> None:
    report = parse_report(json.loads(page.locator("#flow-data").text_content() or "{}"))
    names = {
        item.qualified_name
        for item in report.observed.entities
        if item.kind == "module" and item.presence == "defined"
    }
    expected = {
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
    assert {name for name in names if name.startswith("shop.store.backend.tasks")} == expected
    page.locator('[data-flow-view="diagram"]').click()
    root = page.locator(".flow-breadcrumb button").first
    if root.is_enabled():
        root.click()
    for label in ("store", "backend", "tasks"):
        page.locator(f'.flow-nodes [data-label="{label}"]').press("Enter")
    isolated = page.locator('.flow-nodes [data-label="isolated"]')
    assert isolated.is_visible()
    isolated.press("Space")
    _show_details(page)
    assert (
        "shop.store.backend.tasks.isolated" in page.locator(".flow-inspector-content").inner_text()
    )


def _capture_assets(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    captures = {
        "tour": ("archkeel-component-flow.png", "archkeel-report-preview.png"),
        "clean": ("archkeel-shop-components.png", "archkeel-shop-store-inside.png"),
        "target-store": ("archkeel-target-store.png",),
        "empty-responsibility": ("archkeel-empty-responsibility.png",),
        "target-present": ("archkeel-module-target.png",),
        "mixed": ("archkeel-rule-evidence.png",),
    }
    for name, filenames in captures.items():
        page, errors = _visit(browser, reports[name], f"assets-{name}", output)
        try:
            for filename in filenames:
                if "target" in filename or "responsibility" in filename:
                    page.locator('[data-flow-view="target"]').click()
                if (
                    "inside" in filename
                    or "target-store" in filename
                    or "responsibility" in filename
                ):
                    page.locator('.flow-nodes [data-label="store"]').press("Enter")
                if filename == "archkeel-shop-store-inside.png":
                    card = page.locator('.flow-nodes [data-label="api"]')
                    identity = card.get_attribute("data-uml-id")
                    assert identity
                    page.locator("#flow-focus").select_option(identity)
                    card.press("Space")
                    page.get_by_role("button", name="Fit overview", exact=True).click()
                if "responsibility" in filename:
                    page.locator('.flow-nodes [data-label="api"]').press("Space")
                    _show_details(page)
                    assert (
                        "No declared responsibility"
                        in page.locator(".flow-inspector-content").inner_text()
                    )
                if filename == "archkeel-report-preview.png":
                    page.evaluate("scrollTo(0, 0)")
                    page.screenshot(path=str(output / filename))
                else:
                    page.locator("#flow").screenshot(path=str(output / filename))
            assert not errors
        finally:
            _finish(page, f"assets-{name}", output)


def _check_report_verdicts(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    for name in ("open", "tour", "mixed", "clean"):
        result = json.loads((output / f"{name}.result.json").read_text())
        state = {"PASS": "pass", "FAIL": "fail", "UNKNOWN": "unknown"}[result["declared_rules"]]
        for javascript in (True, False):
            page = browser.new_page(java_script_enabled=javascript)
            try:
                page.goto(reports[name].as_uri(), wait_until="load")
                assert page.locator(".decision-banner").get_attribute("data-decision") == state
                rules = page.locator(".verdict-card").filter(
                    has=page.locator("code", has_text="declared_rules")
                )
                assert rules.get_attribute("data-verdict") == state
                rows = page.locator('[aria-labelledby="rule-assessments-heading"] tbody tr')
                statuses = rows.evaluate_all("rows => rows.map(row => row.dataset.status)")
                assert statuses == sorted(
                    statuses, key=lambda status: (status != "FAIL", status != "UNKNOWN")
                )
                headline = page.locator(".decision-banner").inner_text()
                for status in ("FAIL", "UNKNOWN"):
                    names = [
                        item["id"]
                        for item in result["rule_assessments"] or []
                        if item["status"] == status
                    ]
                    assert all(rule in headline for rule in names[:3])
                if name == "open":
                    assert "open decision(s) remain" in headline
                for width in (1440, 375):
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(
                        path=str(output / f"headline-{name}-{width}-js{int(javascript)}.png")
                    )
            finally:
                page.close()


def _check_long_rule_ids(browser: Browser, output: Path) -> None:
    names = ("R" * 200, '<rule&"unknown">' * 20)
    assessments = tuple(
        RuleAssessment(
            name, "complete_requires", status, False, 0, 1, "architect", "", (), "", "pkg", ()
        )
        for name, status in zip(names, ("FAIL", "UNKNOWN"), strict=True)
    )
    result = RunResult("report", 0, "PASS", "FAIL", "n/a", rule_assessments=assessments)
    report = output / "long-rule-ids.report.html"
    report.write_bytes(
        render_architecture_html(
            result,
            (output / "mixed.json").read_bytes(),
            repository="shop",
            architecture_href="mixed.json",
        )
    )
    for javascript in (True, False):
        page = browser.new_page(java_script_enabled=javascript)
        try:
            page.goto(report.as_uri(), wait_until="load")
            headline = page.locator(".decision-banner")
            assert all(name in headline.inner_text() for name in names)
            for width in (1440, 375):
                page.set_viewport_size({"width": width, "height": 1000})
                actual = page.evaluate("document.documentElement.scrollWidth")
                assert actual <= width, f"long rule IDs: {actual}px at {width}px"
                page.screenshot(
                    path=str(output / f"headline-long-ids-{width}-js{int(javascript)}.png")
                )
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
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL")
        )
        try:
            for name, report in reports.items():
                page, errors = _visit(browser, report, name, output)
                try:
                    for width in (1440, 375):
                        page.set_viewport_size({"width": width, "height": 1000})
                        _check_graph_views(page)
                    if name.startswith("uml-"):
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        _check_inner_uml(page, name, output)
                    if name == "wide":
                        _check_wide_inventory(page)
                    if name == "mixed":
                        _check_review_handoff(page)
                        _check_report_filters(page)
                    assert not errors, f"{name}: {errors}"
                finally:
                    _finish(page, name, output)
            _check_no_javascript(browser, reports["mixed"], output)
            _check_report_verdicts(browser, reports, output)
            _check_long_rule_ids(browser, output)
            _capture_assets(browser, reports, output)
        finally:
            browser.close()
    print(f"Browser acceptance artifacts: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
