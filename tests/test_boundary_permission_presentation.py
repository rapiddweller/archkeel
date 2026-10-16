# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Boundary permission disclosures preserve every offline audit record."""

import copy
import json
import re

import pytest
from browser_report_support import _browser_page, _open_details
from test_atlas_report import _boundary_permission_report, _flow_payload


@pytest.fixture(scope="module")
def permission_report(tmp_path_factory):
    output = _boundary_permission_report(tmp_path_factory.mktemp("permission-presentation"))
    index = output.with_suffix(".report.html")
    payload = _flow_payload(index)
    permissions = payload["boundary_permissions"]
    for kind in ("declared", "applied"):
        original = permissions[kind][0]
        rows = []
        for number in range(53):
            row = copy.deepcopy(original)
            row["id"] = f"permission-{kind}-{number}"
            selector = row if kind == "declared" else row["data"]
            selector["qualified_name"] = f"sample.app.permission{number}"
            if kind == "applied":
                row["declaration_id"] = f"permission-declared-{number}"
            rows.append(row)
        other = copy.deepcopy(rows[0])
        other.update(id=f"permission-{kind}-other", component_ids=["COMP-OTHER"])
        other["entity_ids"] = []
        other["routes"] = []
        unmapped = copy.deepcopy(rows[0])
        unmapped.update(
            id=f"permission-{kind}-unmapped", component_ids=[], entity_ids=[], routes=[]
        )
        if kind == "applied":
            other["declaration_id"] = "permission-declared-other"
            unmapped["declaration_id"] = "permission-declared-unmapped"
        permissions[kind] = [*rows, other, unmapped]
    html = index.read_text()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    assert match
    index.write_text(
        html[: match.start(1)] + json.dumps(payload).replace("<", "\\u003c") + html[match.end(1) :]
    )
    return index, payload


@pytest.mark.parametrize(
    "lens,kind", [("diagram", "applied"), ("target", "declared"), ("diff", None)]
)
def test_unselected_permissions_are_neutral_counts_with_deferred_audit(
    permission_report, lens, kind
):
    api = pytest.importorskip("playwright.sync_api")
    index, payload = permission_report
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + f"?view={lens}")
        _open_details(page)
        inspector = page.locator(".flow-inspector-content")
        assert inspector.locator("[data-boundary-permission]").count() == 0
        counts = inspector.locator(".boundary-permission-counts").inner_text()
        assert "55" in counts and "PASS" not in counts
        assert ("declared" in counts.lower()) is (kind != "applied")
        assert ("applied" in counts.lower()) is (kind != "declared")
        audit = inspector.locator("[data-boundary-audit]")
        assert audit.get_attribute("open") is None
        audit.locator(":scope > summary").press("Enter")
        inspector.locator("[data-boundary-group]").first.wait_for(state="attached")
        assert inspector.locator("[data-boundary-permission]").count() == 0
        assert "Unmapped boundary permission audit" in inspector.inner_text()
        for group in inspector.locator("[data-boundary-group]").all():
            group.locator(":scope > summary").press("Enter")
            group.locator("[data-boundary-permission]").first.wait_for()
            while group.locator("[data-boundary-more]").count():
                group.locator("[data-boundary-more]").press("Enter")
        assert set(
            inspector.locator("[data-boundary-permission]").evaluate_all(
                "rows => rows.map(row => row.dataset.boundaryPermission)"
            )
        ) == {
            row["id"]
            for section in ("declared", "applied")
            if kind is None or kind == section
            for row in payload["boundary_permissions"][section]
        }
        assert not errors and payload["boundary_permissions"]["applied"][-1]["entity_ids"] == []
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "lens,kinds",
    [("diagram", ["applied"]), ("target", ["declared"]), ("diff", ["declared", "applied"])],
)
def test_selected_permissions_are_scoped_bounded_and_lazy(permission_report, lens, kinds):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = permission_report
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + f"?view={lens}&selected=COMP-APP")
        _open_details(page)
        inspector = page.locator(".flow-inspector-content")
        assert inspector.locator("[data-boundary-audit]").count() == 0
        assert inspector.locator("[data-boundary-permission]").count() == 0
        for kind in kinds:
            group = inspector.locator(f'[data-boundary-group][data-boundary-kind="{kind}"]')
            assert group.count() == 1 and "53" in group.locator(":scope > summary").inner_text()
            group.locator(":scope > summary").press("Enter")
            rows = group.locator("[data-boundary-permission]")
            rows.first.wait_for()
            assert rows.count() == 20
            assert rows.first.locator("dl, p").count() == 0
            rows.first.locator("summary").press("Enter")
            rows.first.locator("dl").wait_for()
            assert "Recorded ID" in rows.first.inner_text()
            assert "Rationale unavailable" not in rows.first.inner_text()
            while group.get_by_role("button", name=re.compile("Show next")).count():
                group.get_by_role("button", name=re.compile("Show next")).press("Enter")
            assert rows.count() == 53
            assert set(
                rows.evaluate_all("rows => rows.map(row => row.dataset.boundaryPermission)")
            ) == {f"permission-{kind}-{number}" for number in range(53)}
        assert "permission-applied-other" not in inspector.inner_html()
        assert "permission-declared-unmapped" not in inspector.inner_html()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("selected", ["", "&selected=COMP-APP"])
@pytest.mark.parametrize(
    "lens,kind",
    [("diagram", "applied"), ("target", "declared"), ("diff", "applied"), ("diff", "declared")],
)
def test_permission_hash_beyond_initial_page_opens_exact_record(
    permission_report, selected, lens, kind
):
    api = pytest.importorskip("playwright.sync_api")
    index, _ = permission_report
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        record_id = f"permission-{kind}-52"
        page.goto(index.as_uri() + f"?view={lens}{selected}#{record_id}")
        _open_details(page)
        record = page.locator(f'[data-boundary-permission="{record_id}"]')
        assert record.get_attribute("open") is not None
        assert (
            "Recorded ID" in record.inner_text()
            and "sample.app.permission52" in record.inner_text()
        )
        assert page.locator("[data-boundary-permission]").count() <= 21
        page.reload()
        assert record.get_attribute("open") is not None
        page.evaluate(f"location.hash = 'permission-{kind}-51'")
        other = page.locator(f'[data-boundary-permission="permission-{kind}-51"]')
        other.locator("dl").wait_for()
        assert other.get_attribute("open") is not None
        assert "permission52" not in other.inner_text() and not errors
        group = other.locator("xpath=ancestor::details[@data-boundary-group]")
        while group.locator("[data-boundary-more]").count():
            group.locator("[data-boundary-more]").press("Enter")
        records = group.locator("[data-boundary-permission]")
        total = 53 if selected else 54
        assert records.count() == total
        assert (
            len(
                set(records.evaluate_all("rows => rows.map(row => row.dataset.boundaryPermission)"))
            )
            == total
        )
    finally:
        browser.close()
        playwright.stop()
