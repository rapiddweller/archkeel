# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Ownership, independent Target and report verdicts survive presentation changes."""

import json
import re

import pytest
from browser_report_support import _browser_page, _open_details, _tour_report_page
from test_atlas_report import _page
from test_exact_module_ownership import _component, _contract, _report
from test_module_explore import _sample
from test_uml_rendering import _open_module, _uml_report

from archkeel.ir.architecture_graph import Entity


@pytest.mark.parametrize("source,destination", [("As-Is", "Target"), ("Target", "Diff")])
def test_view_switch_uses_the_corresponding_scope_and_restores_selection(
    tmp_path, source, destination
):
    html, _ = _uml_report(tmp_path)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, source)
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.press("Space")
        identity = client.get_attribute("data-uml-id")
        breadcrumb = page.locator(".flow-breadcrumb").inner_text()
        page.get_by_role("button", name=destination, exact=True).click()
        assert page.locator('.flow-nodes [data-label="Client"]').count() == 1
        assert page.locator(".flow-breadcrumb button").count() == 3
        page.get_by_role("button", name=source, exact=True).click()
        assert page.locator(".flow-breadcrumb").inner_text() == breadcrumb
        assert client.get_attribute("data-uml-id") == identity
        assert client.get_attribute("aria-pressed") == "true"
    finally:
        browser.close()
        playwright.stop()


def test_view_switch_does_not_restore_an_unrelated_saved_target_scope(tmp_path):
    html, _ = _uml_report(tmp_path)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').press("Enter")
        page.get_by_role("button", name="As-Is", exact=True).click()
        page.locator(".flow-breadcrumb button").nth(2).click()
        page.get_by_role("button", name="Target", exact=True).click()
        assert page.locator('.flow-nodes [data-label="Client"]').count() == 1
        assert page.locator(".flow-breadcrumb button").count() == 3
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_unavailable_counterpart_keeps_location_and_offers_verified_ancestor(tmp_path, ambiguous):
    html, _ = _uml_report(
        tmp_path,
        extra_source=("class Twin:\n def run(self): pass\n" * 2) if ambiguous else "",
        extra_target_entities=(
            Entity(
                "twin",
                "class",
                "sample.core.Twin",
                "python",
                "module",
                presence="planned",
                responsibilities=("Own Twin operations.",),
                provenance=("docs/target.md",),
            ),
            Entity(
                "twin-run",
                "method",
                "sample.core.Twin.run",
                "python",
                "twin",
                presence="planned",
                responsibilities=("Run Twin.",),
                provenance=("docs/target.md",),
            ),
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Twin"]').press("Enter")
        page.locator('.flow-nodes [data-label="run"]').press("Space")
        original = page.locator(".flow-breadcrumb").inner_text()
        data = page.locator("#flow-data").text_content()
        verdicts = page.locator(".verdict-grid").inner_text()
        page.get_by_role("button", name="As-Is", exact=True).click()
        notice = page.locator(".flow-scope-notice")
        assert ("ambiguous" if ambiguous else "No counterpart") in notice.inner_text()
        assert "Twin" in page.locator(".flow-breadcrumb").inner_text()
        assert page.locator(".flow-canvas").is_hidden()
        page.get_by_role("button", name="Target", exact=True).click()
        assert page.locator(".flow-breadcrumb").inner_text() == original
        assert (
            page.locator('.flow-nodes [data-label="run"]').get_attribute("aria-pressed") == "true"
        )
        page.get_by_role("button", name="As-Is", exact=True).click()
        notice.get_by_role("button", name="Open nearest scope").click()
        assert page.locator('.flow-nodes [data-label="Client"]').count() == 1
        assert page.locator(".flow-breadcrumb button").count() == 3
        page.get_by_role("button", name="Target", exact=True).click()
        assert page.locator('.flow-nodes [data-label="Client"]').count() == 1
        assert "Twin" not in page.locator(".flow-breadcrumb").inner_text()
        assert page.locator("#flow-data").text_content() == data
        assert page.locator(".verdict-grid").inner_text() == verdicts
    finally:
        browser.close()
        playwright.stop()


def test_unmapped_namespace_offers_root_without_inventing_a_target_owner(tmp_path):
    contract = _contract([_component("other", [], exact_modules=["sample.absent"])])
    _, html, _, _ = _report(tmp_path, contract)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator(".flow-unassigned-code").click()
        groups = page.locator(".flow-inspector-content details").filter(
            has=page.locator("summary", has_text="Recorded namespace groups")
        )
        groups.locator("summary").click()
        groups.get_by_role("button", name="Open", exact=True).click()
        page.get_by_role("button", name="Target", exact=True).click()
        notice = page.locator(".flow-scope-notice")
        assert "No counterpart" in notice.inner_text()
        assert "sample" in page.locator(".flow-breadcrumb").inner_text()
        notice.get_by_role("button", name="Open nearest scope").click()
        assert page.locator(".flow-breadcrumb button").count() == 1
        assert page.locator('.flow-nodes [data-label="other"]').count() == 1
        assert page.locator('.flow-nodes [data-uml-kind="package"]').count() == 0
        page.get_by_role("button", name="As-Is", exact=True).click()
        assert page.locator(".flow-breadcrumb button").count() == 1
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("keyboard", [False, True])
def test_direct_failed_edge_selection_keeps_core_rule_and_source_evidence(tmp_path, keyboard):
    html, _ = _tour_report_page(tmp_path)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        data = page.locator("#flow-data").text_content()
        verdicts = page.locator(".verdict-grid").inner_text()
        edge = page.locator(".flow-edges .edge.violation .hit").first
        if keyboard:
            edge.press("Enter")
        else:
            edge.scroll_into_view_if_needed()
            point = edge.evaluate("""node => {
              const matrix = node.getScreenCTM(), length = node.getTotalLength();
              for (let fraction = .1; fraction < .95; fraction += .05) {
                const point = node.getPointAtLength(length * fraction).matrixTransform(matrix);
                if (document.elementFromPoint(point.x, point.y)?.closest('.hit') === node)
                  return {x: point.x, y: point.y};
              }
              return null;
            }""")
            assert point
            page.mouse.click(point["x"], point["y"])
        assert edge.get_attribute("aria-pressed") == "true"
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        assert details.get_by_role("heading", name="Recorded findings").count() == 1
        assert "INTERFACE-BOUNDARY" in details.inner_text()
        assert "Source sites" in details.inner_text()
        assert "shop/" in details.inner_text()
        page.get_by_role("button", name="Fit overview").click()
        assert details.get_by_role("heading", name="Recorded findings").count() == 1
        assert "INTERFACE-BOUNDARY" in details.inner_text()
        assert page.locator("#flow-data").text_content() == data
        assert page.locator(".verdict-grid").inner_text() == verdicts
    finally:
        browser.close()
        playwright.stop()


def test_legacy_diff_observed_selection_keeps_exact_source_site(tmp_path):
    contract = _contract([_component("other", [], exact_modules=["sample.absent"])])
    _, html, payload, _ = _report(
        tmp_path, contract, extra_files={"sample/__init__.py": "import sample.core.api\n"}
    )
    assert payload["comparison"] is None
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        page.locator(".flow-unassigned-code").click()
        groups = page.locator(".flow-inspector-content details").filter(
            has=page.locator("summary", has_text="Recorded namespace groups")
        )
        groups.locator("summary").click()
        groups.get_by_role("button", name="Open", exact=True).click()
        _open_details(page)
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Relationship sites" in details
        assert "Source sites" in details
        assert "sample/__init__.py:1:" in details
        assert "import sample.core.api" in details
        assert "OBSERVED UML" in details
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["Target", "Diff"])
def test_source_free_exact_target_is_inspectable_without_invented_files(tmp_path, view):
    contract = _contract([_component("registry", [], exact_modules=["sample.core"])])
    _, html, payload, actual = _report(tmp_path, contract, source_paths=[])
    assert not actual and not payload["target"]["module_inventories"]
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name=view, exact=True).click()
        card = page.locator('.flow-nodes [data-label="registry"]')
        card.press("Space")
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Exact module ownership" in details and "sample.core" in details
        assert "Own registry." in details and "docs/architecture/sample.md" in details
        before = page.locator(".flow-breadcrumb").inner_text()
        card.press("Enter")
        assert page.locator(".flow-breadcrumb").inner_text() == before
        assert page.locator('.flow-nodes [data-uml-kind="module"]').count() == 0
        assert page.locator('.flow-nodes [data-uml-kind="file"]').count() == 0
        assert "sample/core.py" not in page.locator(".flow-inspector-content").inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Diff"])
def test_ambiguous_root_module_stays_reachable_without_an_invented_owner(tmp_path, view):
    contract = _contract(
        [_component(label, [], exact_modules=["sample.core"]) for label in ("one", "two")]
    )
    _, html, payload, _ = _report(tmp_path, contract)
    module = next(
        item
        for item in payload["observed"]["entities"]
        if item["kind"] == "module" and item["qualified_name"] == "sample.core"
    )
    assert not any(module["id"] in item["module_ids"] for item in payload["memberships"])
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name=view, exact=True).click()
        page.locator(".flow-unassigned-code").click()
        groups = page.locator(".flow-inspector-content details").filter(
            has=page.locator("summary", has_text="Recorded namespace groups")
        )
        groups.locator("summary").click()
        groups.get_by_role("button", name="Open", exact=True).click()
        page.locator('.flow-nodes [data-label="core"][data-uml-kind="package"]').press("Enter")
        card = page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]')
        card.press("Space")
        _open_details(page)
        text = page.locator(".flow-inspector-content").inner_text()
        assert "sample.core" in text and "Own one." not in text and "Own two." not in text
        scope = page.locator(".flow-breadcrumb").inner_text()
        page.get_by_role("button", name="Target", exact=True).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert page.locator(".flow-breadcrumb").inner_text() == scope
        assert card.get_attribute("aria-pressed") == "true"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width", [375, 1440])
def test_hiding_all_failed_and_unknown_entities_does_not_change_the_report(tmp_path, width):
    html, payload = _uml_report(tmp_path, mismatch=True)
    assert {item["status"] for item in payload["comparison"]["assessments"]} >= {"FAIL", "UNKNOWN"}
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html, width=width)
    try:
        _open_module(page, "Diff")
        data = page.locator("#flow-data").text_content()
        verdicts = page.locator(".verdict-grid").inner_text()
        unknowns = page.locator("#known-unknowns").inner_text()
        assert page.locator('.verdict-card[data-verdict="fail"]').count() > 0
        if width == 375:
            page.locator(".flow-filters > summary").click()
        page.get_by_label("Element kind", exact=True).select_option("interface")
        assert page.locator(".flow-nodes [data-uml-id]").count() > 0
        assert page.locator('.flow-nodes [data-assessment-status="FAIL"]').count() == 0
        assert page.locator('.flow-nodes [data-assessment-status="UNKNOWN"]').count() == 0
        assert page.locator(".flow-edges .hit").count() == 0
        assert page.locator(".verdict-grid").inner_text() == verdicts
        assert page.locator("#known-unknowns").inner_text() == unknowns
        assert page.locator("#flow-data").text_content() == data
        page.locator("#flow").get_by_role("button", name="Reset filters", exact=True).click()
        assert page.locator('.flow-nodes [data-assessment-status="FAIL"]').count() > 0
        assert page.locator('.flow-nodes [data-assessment-status="UNKNOWN"]').count() > 0
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("reverse", [False, True])
def test_source_free_file_and_initializer_intents_keep_distinct_details(tmp_path, reverse):
    contract = _contract([_component("registry", [], exact_modules=["sample.core"])])
    files = [
        {"path": "sample/core.py", "responsibility": "Own the standalone module."},
        {"path": "sample/core/__init__.py", "responsibility": "Own the package initializer."},
    ]
    contract["declarations"] = {"modules": list(reversed(files)) if reverse else files}
    _, html, _, _ = _report(tmp_path, contract, source_paths=[])
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        details.get_by_text("Module inventory · 2 planned files", exact=True).click()
        for file in files:
            row = details.locator(f'[data-file-intent="{file["path"]}"]').inner_text()
            assert file["path"] in row and file["responsibility"] in row
            assert "Observed module:" not in row
            assert "Not in the observed file inventory" not in row
        assert (
            "File intent does not define classes, methods, imports or calls" in details.inner_text()
        )
        page.get_by_role("button", name="Diff", exact=True).click()
        details.get_by_text("Module inventory · 2 planned files", exact=True).click()
        for file in files:
            assert (
                "Not in the observed file inventory"
                in details.locator(f'[data-file-intent="{file["path"]}"]').inner_text()
            )
        assert page.locator('.flow-nodes [data-uml-kind="file"]').count() == 0
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width", [375, 1440])
def test_long_target_names_paths_and_responsibilities_remain_accessible(tmp_path, width):
    label = "architecture_boundary_" * 4
    responsibility = (
        "Own a stable architecture boundary and preserve every original evidence site. " * 3
    )
    path = "sample/" + "/".join(["long_package_name"] * 8) + "/interface_definition.py"
    contract = _contract(
        [_component(label, [], exact_modules=["sample.missing"], responsibilities=[responsibility])]
    )
    contract["declarations"] = {"modules": [{"path": path, "responsibility": responsibility}]}
    _, html, payload, _ = _report(tmp_path, contract, source_paths=[])
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html, width=width)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        identity = payload["target"]["component_intents"][0]["component_id"]
        page.locator(f'.flow-nodes [data-uml-id="{identity}"]').press("Space")
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        assert label in details.inner_text() and responsibility.strip() in details.inner_text()
        assert details.evaluate("node => getComputedStyle(node).writingMode") == "horizontal-tb"
        page.locator(".flow-graph").dispatch_event("click")
        details.get_by_text("Module inventory · 1 planned file", exact=True).click()
        row = details.locator(f'[data-file-intent="{path}"]').inner_text()
        assert path in row and responsibility.strip() in row
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width", [375, 1440])
def test_target_atlas_root_inspector_ignores_observed_verdict_and_analysis_limits(tmp_path, width):
    html = _page(_sample(tmp_path, uml=True))
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    original = json.loads(match.group(1))
    assert original["atlas"]["unknown_count"] > 0
    variants = [original]
    for status, count in (("PASS", 0), ("FAIL", 17), ("UNKNOWN", 37)):
        changed = json.loads(match.group(1))
        changed["atlas"].update(
            status=status,
            reason="Changed recorded verdict",
            unknown_count=count,
            unknowns=[{"reason": "Changed recorded analysis limit", "count": count}]
            if count
            else [],
        )
        variants.append(changed)
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, width=width, errors=errors)
    try:
        target_details = []
        for payload in variants:
            page.goto("about:blank")
            page.set_content(html.replace(match.group(1), json.dumps(payload), 1))
            page.get_by_role("button", name="Target", exact=True).click()
            _open_details(page)
            details = page.locator(".flow-inspector-content")
            text = details.text_content()
            assert "Core " not in text and "analysis limits" not in text
            assert "Declared intent" in text
            assert "import cell" not in text and "Every count refers" not in text
            target_details.append(details.inner_html())
            for view in ("As-Is", "Diff"):
                page.get_by_role("button", name=view, exact=True).click()
                text = details.text_content()
                atlas = payload["atlas"]
                assert f"Core {atlas['status']}: {atlas['reason']}" in text
                assert f"{atlas['unknown_count']} analysis limits" in text
                for item in atlas["unknowns"]:
                    assert f"{item['count']} × {item['reason']}" in text
            assert json.loads(page.locator("#flow-data").text_content()) == payload
        assert target_details == [target_details[0]] * len(variants)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("selection", ["component", "module"])
def test_target_atlas_component_and_module_details_ignore_observed_measurements(
    tmp_path, selection
):
    html = _page(_sample(tmp_path, uml=True))
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    original = json.loads(match.group(1))
    changed = json.loads(match.group(1))
    for component in changed["atlas"]["components"]:
        component.update(
            status="FAIL",
            reason="Changed recorded component check",
            observed_modules=91,
            observed_symbols=93,
            symbols_complete=False,
            used_by=[],
        )
        for edge in component["requires"]:
            edge["observed_imports"] = 97
    for module in changed["atlas"]["modules"]:
        module.update(symbols=101, fan_in=103, fan_out=107)
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        target_details = []
        for payload in (original, changed):
            page.goto("about:blank")
            page.set_content(html.replace(match.group(1), json.dumps(payload), 1))
            page.get_by_role("button", name="Target", exact=True).click()
            component = page.locator('.flow-nodes [data-uml-id="core"]')
            component.press("Space")
            if selection == "module":
                component.press("Enter")
                page.locator('.flow-nodes [data-uml-id="core-module"]').press("Space")
            _open_details(page)
            details = page.locator(".flow-inspector-content").text_content()
            assert "Responsibility" in details and "Provenance" in details
            assert "Recorded checks" not in details and "Observed weight" not in details
            assert "Changed recorded" not in details and "observed imports" not in details
            assert "fan-in" not in details and "fan-out" not in details
            target_details.append(details)
            assert json.loads(page.locator("#flow-data").text_content()) == payload
        assert target_details[0] == target_details[1]
        assert not errors
    finally:
        browser.close()
        playwright.stop()
