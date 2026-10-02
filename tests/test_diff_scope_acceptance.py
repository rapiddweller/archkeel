# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested Diff navigation keeps physical evidence scope without deciding missing evidence."""

from pathlib import Path

import pytest
from test_actual_target_diff_acceptance import _acceptance_page, _open_projection_entry, _walk
from test_target_hierarchy_independent_acceptance import _ce_nested_route_page


@pytest.mark.parametrize("width", [1600, 375])
@pytest.mark.parametrize("scope", ["workers", "policies"])
def test_ce_sized_nested_diff_retains_scope_and_only_its_recorded_differences(
    tmp_path: Path, width: int, scope: str
) -> None:
    html, payload = _ce_nested_route_page(tmp_path, include_scoped_diff_controls=True)
    assert sum(node["kind"] == "module" for node in _walk(payload["explorers"]["actual"])) >= 492
    global_violations = payload["explorers"]["diff"][0]["children"]
    assert len(global_violations) == 2
    worker_violation = next(row for row in global_violations if "workers.make" in row["label"])
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            for node_id in (
                "COMP-RUNTIME",
                "runtime:RUNTIME-TASKS",
                "runtime:tasks:TASKS-GENERATE",
                f"runtime:tasks:generate:GENERATE-{scope.upper()}",
            ):
                page.locator(f'.flow-nodes [data-target-node="{node_id}"]').dblclick()
            target_path = page.locator(".flow-breadcrumb button").all_text_contents()
            page.locator('[data-flow-view="actual"]').click()
            actual_path = page.locator(".flow-breadcrumb button").all_text_contents()[1:]
            assert actual_path[-1] == scope
            page.locator('[data-flow-view="diff"]').click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == [
                "Diff",
                *actual_path,
            ]
            assert page.locator(".flow-projection h2").inner_text() == scope
            if scope == "policies":
                assert (
                    "No recorded differences in this scope"
                    in page.locator(".flow-projection").inner_text()
                )
                assert (
                    "missing evidence remains UNKNOWN"
                    in page.locator(".flow-projection").inner_text()
                )
                assert not page.locator('[data-projection-id="diff:violations"]').count()
            else:
                category = page.locator(".flow-item-list button").filter(
                    has=page.get_by_text("Violations", exact=True)
                )
                _open_projection_entry(
                    page, f'[data-projection-id="{category.get_attribute("data-projection-id")}"]'
                )
                assert page.locator(".flow-item-list [data-projection-id]").count() == 1
                assert (
                    page.locator(".flow-item-list [data-projection-id]").first.get_attribute(
                        "data-projection-id"
                    )
                    == worker_violation["id"]
                )
                page.locator(".flow-back").click()
                unknowns = page.locator(".flow-item-list button:visible").filter(
                    has=page.get_by_text("Unknown / unresolved evidence", exact=True)
                )
                _open_projection_entry(
                    page, f'[data-projection-id="{unknowns.get_attribute("data-projection-id")}"]'
                )
                visible_unknowns = page.locator(
                    ".flow-item-list [data-projection-id]:visible"
                ).evaluate_all("nodes => nodes.map(node => node.dataset.projectionId)")
                assert visible_unknowns
                assert all(
                    "workers" in row["scopes"][0]
                    for row in payload["explorers"]["diff"][1]["children"]
                    if row["id"] in visible_unknowns
                )
                page.locator(".flow-back").click()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == target_path
            page.locator('[data-flow-view="diff"]').click()
            page.locator(".flow-breadcrumb button").nth(-2).click()
            assert page.locator(".flow-breadcrumb button").all_text_contents()[-1] == "generate"
            page.locator(".flow-back").click()
            assert page.locator(".flow-breadcrumb button").all_text_contents()[-1] == "tasks"
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("width", [1600, 375])
@pytest.mark.parametrize("action", ["nearest", "back", "breadcrumb"])
def test_missing_actual_counterpart_waits_for_explicit_nearest_scope(
    tmp_path: Path, width: int, action: str
) -> None:
    html, payload, _ = _acceptance_page(
        tmp_path,
        module_declarations=[{"path": "shop/missing.py", "responsibility": "Own missing work."}],
    )
    missing = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target" and node["label"] == "missing.py"
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator("[data-flow-details-toggle]").click()
            page.locator(".flow-responsibilities summary").click()
            page.locator(".flow-responsibility-search").fill("missing.py")
            page.locator(".flow-responsibility-list button:visible").first.click()
            source_path = page.locator(".flow-breadcrumb button").all_text_contents()[1:]
            page.locator('[data-flow-view="actual"]').click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == [
                "Actual",
                *source_path,
                "missing.py",
            ]
            assert page.locator("[data-projection-id]:visible").count() == 0
            nearest = page.get_by_role("button", name="Open nearest scope: shop", exact=True)
            assert nearest.is_visible()
            assert (
                "No matching scope" in page.locator(".flow-projection-context:visible").inner_text()
            )
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(f'[data-target-node="{missing["id"]}"]:visible').count() == 1
            page.locator('[data-flow-view="actual"]').click()
            if action == "nearest":
                nearest.focus()
                page.keyboard.press("Enter")
            elif action == "back":
                page.locator(".flow-back").click()
            else:
                page.locator(".flow-breadcrumb button").first.click()
            expected_path = ["Actual", "shop"] if action == "nearest" else ["Actual"]
            assert page.locator(".flow-breadcrumb button").all_text_contents() == expected_path
            assert page.locator(".flow-projection-context:visible").count() == 0
        finally:
            browser.close()
