# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested Diff navigation keeps physical evidence scope without deciding missing evidence."""

from pathlib import Path

import pytest
from test_actual_target_diff_acceptance import _acceptance_page, _open_projection_entry, _walk
from test_target_hierarchy_independent_acceptance import _ce_nested_route_page


@pytest.mark.parametrize("width", [1600, 375])
@pytest.mark.parametrize("back", ["button", "breadcrumb", "escape"])
def test_nested_diff_keyboard_drill_recovers_logical_target_after_view_switch_and_back(
    tmp_path: Path, width: int, back: str
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    html, _ = _ce_nested_route_page(tmp_path, include_scoped_diff_controls=True)
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
                "runtime:tasks:generate:GENERATE-WORKERS",
            ):
                page.locator(f'.flow-nodes [data-target-node="{node_id}"]').dblclick()
            target_path = page.locator(".flow-breadcrumb button").all_text_contents()
            page.locator('[data-flow-view="actual"]').click()
            page.locator('[data-flow-view="diff"]').click()
            page.locator(
                '[data-projection-id="diff-scope:datamimic_ce.engine.runtime.tasks.generate.workers.generate_worker"]'
            ).focus()
            page.keyboard.press("Enter")
            page.locator('[data-flow-view="actual"]').click()
            page.locator('[data-flow-view="diff"]').click()
            if back == "button":
                page.locator(".flow-back").click()
            elif back == "breadcrumb":
                page.locator(".flow-breadcrumb button").nth(-2).click()
            else:
                page.keyboard.press("Escape")
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == target_path
            assert page.locator(".flow-projection-context:visible").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("width", [1600, 375])
@pytest.mark.parametrize("declared", [True, False])
@pytest.mark.parametrize("action", ["select", "open"])
def test_diff_module_counterparts_keep_exact_declaration_or_explain_absence(
    tmp_path: Path, width: int, declared: bool, action: str
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    html, payload = _ce_nested_route_page(
        tmp_path, include_scoped_diff_controls=True, include_worker_module_target=True
    )
    scope = (
        "datamimic_ce.engine.runtime.tasks.generate.workers"
        if declared
        else "datamimic_ce.engine.runtime.storage"
    )
    module = "generate_worker" if declared else "extra_0"
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_default_timeout(2_000)
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="diff"]').click()
            for end in range(1, len(scope.split(".")) + 1):
                identifier = ".".join(scope.split(".")[:end])
                page.locator(f'[data-projection-id="diff-scope:{identifier}"]').focus()
                page.keyboard.press("Enter")
            leaf = page.locator(f'[data-projection-id="diff-scope:{scope}.{module}"]')
            leaf.click()
            if action == "open":
                page.locator(".flow-open-selected").click()
            page.locator('[data-flow-view="target"]').click()
            if declared:
                target = next(
                    node
                    for node in _walk(payload["explorers"]["target"])
                    if node["kind"] == "module_target"
                    and any(
                        item["label"] == "File" and item["value"].endswith("/generate_worker.py")
                        for item in node["details"]
                    )
                )
                assert (
                    page.locator(f'[data-target-node="{target["id"]}"]:visible').get_attribute(
                        "aria-pressed"
                    )
                    == "true"
                )
                assert page.locator(".flow-projection-context:visible").count() == 0
            else:
                assert (
                    "No matching scope"
                    in page.locator(".flow-projection-context:visible").inner_text()
                )
                assert page.locator("[data-target-node]:visible").count() == 0
                assert page.get_by_role(
                    "button", name=f"Open nearest scope: {scope}", exact=True
                ).is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


@pytest.mark.parametrize("width", [1600, 375])
def test_overlapping_diff_scope_owners_require_explicit_target_navigation(
    tmp_path: Path, width: int
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    html, payload = _ce_nested_route_page(
        tmp_path, include_scoped_diff_controls=True, include_overlapping_worker_owner=True
    )
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_content(html, wait_until="load")
            page.locator('[data-flow-view="diff"]').click()
            scope = "datamimic_ce.engine.runtime.tasks.generate.workers"
            for end in range(1, len(scope.split(".")) + 1):
                identifier = ".".join(scope.split(".")[:end])
                page.locator(f'[data-projection-id="diff-scope:{identifier}"]').focus()
                page.keyboard.press("Enter")
            source_path = page.locator(".flow-breadcrumb button").all_text_contents()[1:]
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == [
                "Target",
                *source_path,
            ]
            assert (
                "No matching scope" in page.locator(".flow-projection-context:visible").inner_text()
            )
            assert page.locator("[data-target-node]:visible").count() == 0
            page.get_by_role("button", name="Open Target root", exact=True).click()
            assert page.locator(".flow-breadcrumb button").all_text_contents() == ["Target"]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            diff_node = next(
                node
                for node in _walk(payload["explorers"]["diff"])
                if node["id"] == f"diff-scope:{scope}"
            )
            declaration_ids = {
                item["value"]
                for item in diff_node["details"]
                if item["label"] == "Target declaration ID"
            }
            assert declaration_ids == {
                "runtime:tasks:generate:GENERATE-WORKERS",
                "runtime:tasks:generate:GENERATE-OTHER-WORKERS",
            }
        finally:
            browser.close()


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
