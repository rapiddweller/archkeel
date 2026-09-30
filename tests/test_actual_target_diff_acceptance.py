# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Acceptance checks for the report's Actual, Target, and Diff projections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def _acceptance_page(
    tmp_path: Path,
    *,
    module_declarations: list[dict[str, str]] | None = None,
    include_absent_component: bool = False,
    extra_files: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any], set[str]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    root_layout["allowed_children"].append("shop.missing")
    if module_declarations is not None:
        contract.setdefault("declarations", {})["modules"] = module_declarations
    if include_absent_component:
        ghost = next(
            component for component in contract["components"] if component["id"] == "COMP-MODEL"
        )
        contract["components"].append(
            {
                **ghost,
                "id": "COMP-GHOST",
                "label": "ghost",
                "packages": ["shop.ghost", "shop.phantom"],
                "namespace": "shop.ghost",
                "public": [],
                "responsibilities": ["Own the absent ghost package."],
            }
        )
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        "shop/orphan.py": "VALUE = 1\n",
        **(extra_files or {}),
    }
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    assert '<nav class="flow-views" aria-label="Architecture views" hidden>' in page
    assert "Observed module tree" in page
    assert "shop.orphan" in page  # the static report retains evidence with JavaScript disabled
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    observed_modules = {
        record.data.get("qualified_name")
        for record in observation.records("modules") or ()
        if isinstance(record.data.get("qualified_name"), str)
    }
    return page, payload, observed_modules


def test_actual_target_diff_retains_absent_orphan_and_violating_evidence(tmp_path: Path) -> None:
    page, payload, observed_modules = _acceptance_page(tmp_path)
    explorers = payload["explorers"]
    actual = list(_walk(explorers["actual"]))
    target = list(_walk(explorers["target"]))
    diff = list(_walk(explorers["diff"]))

    # Actual is an inventory, including modules without a declared owner.
    actual_modules = {node["id"] for node in actual if node["kind"] == "module"}
    assert actual_modules == observed_modules
    assert "shop.orphan" in actual_modules
    assert any(
        node["label"] == "shop.orphan" for node in diff if node["id"] == "unmapped:shop.orphan"
    )

    # The absent child is a declaration, not an observed module.
    assert any(
        node["id"] == "physical:shop.missing" and node["kind"] == "physical_child"
        for node in target
    )
    assert any(
        node["label"] == "shop.missing" and node["kind"] == "physical_child" for node in diff
    )
    assert "shop.missing" not in actual_modules

    # Existing forbidden imports belong to Diff; they must not masquerade as target facts.
    violations = [node for node in diff if node["kind"] == "violation"]
    assert violations, "tour fixture must retain its violating-import positive control"
    assert all(node["kind"] != "violation" for node in target)
    assert "Violations" in page and "Absent declared targets" in page


def test_exact_module_target_covers_unassigned_module_without_hiding_orphans(
    tmp_path: Path,
) -> None:
    _, payload, observed_modules = _acceptance_page(
        tmp_path,
        module_declarations=[
            {"path": "shop/orphan.py", "responsibility": "Own the standalone module."},
            {"path": "shop/namespace/__init__.py", "responsibility": "Mark the namespace."},
        ],
        extra_files={
            "shop/namespace/__init__.py": "",
            "shop/stray.py": "VALUE = 2\n",
        },
    )
    actual = {
        node["id"] for node in _walk(payload["explorers"]["actual"]) if node["kind"] == "module"
    }
    target_files = {
        detail["value"]
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target"
        for detail in node["details"]
        if detail["label"] == "File"
    }
    diff = {node["id"] for node in _walk(payload["explorers"]["diff"])}

    assert actual == observed_modules
    assert {"shop.orphan", "shop.namespace", "shop.stray"} <= actual
    assert {"shop/orphan.py", "shop/namespace/__init__.py"} <= target_files
    assert "unmapped:shop.orphan" not in diff
    assert "unmapped:shop.namespace" not in diff
    assert "unmapped:shop.stray" in diff
    assert "observed-only-target:shop.stray" in diff


def test_absent_diff_module_keeps_exact_target_declaration_reference(tmp_path: Path) -> None:
    _, payload, _ = _acceptance_page(
        tmp_path,
        module_declarations=[
            {
                "path": "shop/missing.py",
                "responsibility": "Own the missing module boundary.",
            }
        ],
    )
    target = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target"
        and any(
            detail["label"] == "File" and detail["value"] == "shop/missing.py"
            for detail in node["details"]
        )
    )
    absent = next(
        node
        for node in _walk(payload["explorers"]["diff"])
        if node["kind"] == "module_target" and node["label"] == "shop/missing.py"
    )
    assert any(
        detail["label"] == "File" and detail["value"] == "shop/missing.py"
        for detail in absent["details"]
    ), f"absent Diff entry must link to exact target declaration {target['id']}"
    assert any(
        detail["label"] == "Responsibility"
        and detail["value"] == "Own the missing module boundary."
        for detail in absent["details"]
    )


def test_selected_module_responsibility_uses_exact_path_across_views(tmp_path: Path) -> None:
    page_html, payload, _ = _acceptance_page(
        tmp_path,
        module_declarations=[
            {
                "path": "shop/app/orders.py",
                "responsibility": "Own <order> decisions & totals.",
            },
            {
                "path": "shop/model/orders.py",
                "responsibility": "Own order value types.",
            },
            {
                "path": "shop/missing.py",
                "responsibility": "Own the missing module boundary.",
            },
        ],
        include_absent_component=True,
    )
    missing_id = next(
        node["id"]
        for node in _walk(payload["explorers"]["diff"])
        if node["label"] == "shop/missing.py" and node["kind"] == "module_target"
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 375, "height": 844})
            page.set_content(page_html, wait_until="load")
            responsibility = page.locator(".flow-selected-responsibility")
            assert not responsibility.is_visible()
            page.get_by_role("button", name="Actual").click()
            page.locator('[data-projection-id="shop"]').click()
            page.locator('[data-projection-id="shop.orphan"]').click()
            assert responsibility.get_by_text("No matching target declaration.").is_visible()
            page.locator("[data-projection-root]").click()
            page.locator('[data-projection-id="shop"]').click()
            page.locator('[data-projection-id="shop.app"]').click()
            page.locator('[data-projection-id="shop.app.orders"]').click()

            assert responsibility.get_by_text(
                "Own <order> decisions & totals.", exact=True
            ).is_visible()
            assert "observed" not in responsibility.inner_text().lower()

            page.get_by_role("button", name="Target").click()
            assert responsibility.get_by_text(
                "Own <order> decisions & totals.", exact=True
            ).is_visible()
            assert "No matching entry" not in responsibility.inner_text()
            page.get_by_role("button", name="Diff").click()
            assert responsibility.get_by_text(
                "Own <order> decisions & totals.", exact=True
            ).is_visible()
            page.locator('[data-projection-id="diff:absent"]').click()
            page.locator(f'[data-projection-id="{missing_id}"]').click()
            assert responsibility.get_by_text(
                "Own the missing module boundary.", exact=True
            ).is_visible()
            assert "No matching entry" not in responsibility.inner_text()
            page.get_by_role("button", name="Actual").click()
            assert responsibility.get_by_text(
                "Own the missing module boundary.", exact=True
            ).is_visible()
            assert "No matching entry in this view" in responsibility.inner_text()

            page.get_by_role("button", name="Diff").click()
            assert (
                page.locator(f'[data-projection-id="{missing_id}"]').get_attribute("aria-pressed")
                == "true"
            )
            page.locator("[data-projection-root]").click()
            page.locator('[data-projection-id="diff:absent"]').click()
            ghost = next(
                node
                for node in _walk(payload["explorers"]["diff"])
                if node["kind"] == "component" and node["label"] == "ghost"
            )
            page.locator(f'[data-projection-id="{ghost["id"]}"]').click()
            assert responsibility.get_by_text(
                "Own the absent ghost package.", exact=True
            ).is_visible()
            page.locator("[data-projection-root]").click()
            assert not responsibility.is_visible()

            page.get_by_role("button", name="Target", exact=True).click()
            app = next(
                node
                for node in _walk(payload["explorers"]["target"])
                if node["kind"] == "component" and node["label"] == "app"
            )
            page.locator(f'[data-target-node="{app["id"]}"]').click()
            assert responsibility.is_visible()
            page.locator(".flow-back").click()
            assert not responsibility.is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


def test_actual_target_switch_preserves_scope_or_names_missing_counterpart(tmp_path: Path) -> None:
    page_html, payload, _ = _acceptance_page(
        tmp_path,
        module_declarations=[
            {"path": "shop/app/orders.py", "responsibility": "Own order decisions."},
            {"path": "shop/missing.py", "responsibility": "Own the missing module."},
        ],
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 800, "height": 900})
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.set_content(page_html, wait_until="load")
            actual = payload["explorers"]["actual"]
            target = payload["explorers"]["target"]

            def path_to(nodes: list[dict[str, Any]], target_id: str) -> list[str]:
                for node in nodes:
                    if node["id"] == target_id:
                        return [target_id]
                    path = path_to(node["children"], target_id)
                    if path:
                        return [node["id"], *path]
                return []

            def open_actual_path(path: list[str]) -> None:
                for node_id in path:
                    page.locator(f'[data-projection-id="{node_id}"]').click()

            # The initial Diagram view switches to a visible projection without a JS error.
            page.locator('[data-flow-view="actual"]').click()
            open_actual_path(path_to(actual, "shop.app.orders"))
            module_target = next(
                node
                for node in _walk(target)
                if node["kind"] == "module_target" and node["label"] == "orders.py"
            )
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(
                f'.target-node[data-target-node="{module_target["id"]}"]'
            ).is_visible()
            assert (
                page.locator(".flow-inspector")
                .get_by_role("heading", name="orders.py")
                .is_visible()
            )
            page.locator('[data-flow-view="actual"]').click()
            assert page.get_by_role("heading", name="orders").is_visible()
            assert page_errors == []

            # A target-only nested edge returns to its uniquely mapped package context.
            page.locator('[data-flow-view="target"]').click()
            page.locator(".flow-breadcrumb button").first.click()
            page.locator('.target-node[data-target-node="COMP-STORE"]').click()
            edge = next(
                item
                for item in payload["explorers"]["target_diagrams"]["nested"]["COMP-STORE"]["edges"]
                if item["kind"] == "requires"
            )
            edge_button = page.locator(f'[data-target-edge="{edge["declaration"]}"]')
            hit_path = edge_button.locator(".target-hit")
            hit_path.scroll_into_view_if_needed()
            point = hit_path.evaluate(
                "path => { const length = path.getTotalLength();"
                " const matrix = path.getScreenCTM();"
                " if (!length || !matrix) return null;"
                " const edge = path.closest('[data-target-edge]');"
                " for (let ratio = 0.2; ratio <= 0.8; ratio += 0.05) {"
                " const p = path.getPointAtLength(length * ratio);"
                " const s = new DOMPoint(p.x, p.y).matrixTransform(matrix);"
                " const under = document.elementFromPoint(s.x, s.y);"
                " if (under && edge.contains(under)) return {x: s.x, y: s.y}; } return null; }"
            )
            assert point is not None
            page.mouse.click(point["x"], point["y"])
            page.locator('[data-flow-view="actual"]').click()
            assert (
                "No matching scope for requires"
                in page.locator(".flow-projection-context").inner_text()
            )
            assert page.locator(".flow-projection-breadcrumb").inner_text().endswith("store")

            # A missing Target child maps to the nearest actual namespace ancestor.
            page.locator('[data-flow-view="target"]').click()
            page.locator(".flow-breadcrumb button").first.click()
            page.locator('.target-node[data-target-node="layout:ROOT-LAYOUT"]').click()
            page.locator('.target-node[data-target-node="physical:shop.missing"]').click()
            page.locator('[data-flow-view="diff"]').click()
            assert page.locator(
                '[data-projection-id="absent:ROOT-LAYOUT:shop.missing"]'
            ).is_visible()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(
                '.target-node[data-target-node="physical:shop.missing"]'
            ).is_visible()
            assert page_errors == []
        finally:
            browser.close()


@pytest.mark.parametrize(
    "navigation", ["round_trip", "actual_round_trip", "diff_category", "diff_root"]
)
def test_unmatched_target_diff_round_trip_preserves_or_replaces_context(
    tmp_path: Path, navigation: str
) -> None:
    page_html, payload, _ = _acceptance_page(
        tmp_path,
        module_declarations=[
            {"path": "shop/missing.py", "responsibility": "Own the missing module."},
        ],
    )
    target_module = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target" and node["label"] == "missing.py"
    )
    next(detail for detail in target_module["details"] if detail["label"] == "File")["value"] = (
        "runtime/tasks/values/construction/global_increment.py"
    )
    if navigation == "actual_round_trip":
        actual = {
            "id": "runtime",
            "label": "runtime",
            "kind": "group",
            "details": [],
            "children": [],
        }
        current = actual
        for label in ("tasks", "values", "construction"):
            child = {
                "id": f"{current['id']}.{label}",
                "label": label,
                "kind": "group",
                "details": [],
                "children": [],
            }
            current["children"].append(child)
            current = child
        current["children"].append(
            {
                "id": "runtime.tasks.values.construction.global_increment",
                "label": "global_increment",
                "kind": "module",
                "details": [
                    {
                        "label": "File",
                        "value": "runtime/tasks/values/construction/global_increment.py",
                    },
                ],
                "children": [],
            }
        )
        payload["explorers"]["actual"].append(actual)

    def remove_node(nodes: list[dict[str, Any]], node_id: str) -> bool:
        for index, node in enumerate(nodes):
            if node["id"] in {node_id, f"absent:{node_id}"} or any(
                detail["label"] == "Target declaration ID" and detail["value"] == node_id
                for detail in node["details"]
            ):
                del nodes[index]
                return True
            if remove_node(node["children"], node_id):
                return True
        return False

    assert remove_node(payload["explorers"]["diff"], target_module["id"])
    start = page_html.index('id="flow-data"')
    payload_start = page_html.index(">", start) + 1
    payload_end = page_html.index("</script>", payload_start)
    page_html = page_html[:payload_start] + json.dumps(payload) + page_html[payload_end:]
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator(".flow-responsibilities summary").click()
            page.locator(".flow-responsibility-search").fill("global_increment.py")
            page.locator(".flow-responsibility-list button:visible").first.click()
            page.locator('[data-flow-view="diff"]').click()
            assert "No matching scope" in page.locator(".flow-projection-context").inner_text()

            if navigation == "actual_round_trip":
                page.locator('[data-flow-view="actual"]').click()
                module_id = "runtime.tasks.values.construction.global_increment"
                assert (
                    page.locator(f'[data-projection-id="{module_id}"]').get_attribute(
                        "aria-pressed"
                    )
                    == "true"
                )
                page.locator('[data-flow-view="target"]').click()
                assert page.locator(
                    f'.target-node[data-target-node="{target_module["id"]}"]'
                ).is_visible()
            elif navigation == "diff_category":
                page.locator('[data-projection-id="diff:absent"]').click()
            elif navigation == "diff_root":
                page.locator("[data-projection-root]").click()
            if navigation != "actual_round_trip":
                page.locator('[data-flow-view="target"]').click()
                if navigation == "round_trip":
                    assert page.locator(
                        f'.target-node[data-target-node="{target_module["id"]}"]'
                    ).is_visible()
                    assert (
                        page.locator(".flow-inspector")
                        .get_by_role("heading", name="missing.py")
                        .is_visible()
                    )
                else:
                    assert not page.locator(
                        f'.target-node[data-target-node="{target_module["id"]}"]'
                    ).is_visible()
        finally:
            browser.close()


def test_ambiguous_target_package_uses_unique_ancestor_context(tmp_path: Path) -> None:
    page_html, payload, _ = _acceptance_page(tmp_path)
    target = payload["explorers"]["target"]
    duplicate = next(
        node
        for node in _walk(target)
        if node["kind"] == "package_scope" and node["label"] == "shop.app"
    )
    owner = next(node for node in target if node["id"] == "COMP-CLI")
    owner["children"].append(
        {
            **duplicate,
            "id": "package:COMP-CLI:shop.app-duplicate",
            "children": [],
        }
    )
    start = page_html.index('id="flow-data"')
    payload_start = page_html.index(">", start) + 1
    payload_end = page_html.index("</script>", payload_start)
    page_html = page_html[:payload_start] + json.dumps(payload) + page_html[payload_end:]
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="actual"]').click()
            page.locator('[data-projection-id="shop"]').click()
            page.locator('[data-projection-id="shop.app"]').click()
            page.locator('[data-flow-view="target"]').click()
            assert (
                "No matching scope for shop.app"
                in page.locator(".flow-projection-context").inner_text()
            )
            assert page.locator(".flow-breadcrumb").inner_text().endswith("shop")
            assert page_errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("escape_at_root", [False, True])
def test_selected_root_actual_leaf_names_missing_target_context(
    tmp_path: Path, escape_at_root: bool
) -> None:
    page_html, payload, _ = _acceptance_page(tmp_path)
    payload["explorers"]["actual"].append(
        {
            "id": "standalone",
            "label": "standalone",
            "kind": "module",
            "details": [{"label": "File", "value": "standalone.py"}],
            "children": [],
        }
    )
    start = page_html.index('id="flow-data"')
    payload_start = page_html.index(">", start) + 1
    payload_end = page_html.index("</script>", payload_start)
    page_html = page_html[:payload_start] + json.dumps(payload) + page_html[payload_end:]
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="actual"]').click()
            page.locator('[data-projection-id="standalone"]').click()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            assert "standalone" in page.locator(".flow-projection-context").inner_text(timeout=1000)
            if escape_at_root:
                page.keyboard.press("Escape")
                assert page.locator(".flow-projection-context").count() == 0
                assert page.locator(".flow-breadcrumb").inner_text() == "Target"
                page.keyboard.press("Escape")
                assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            page.locator('[data-flow-view="actual"]').click()
            expected_selection = "false" if escape_at_root else "true"
            assert (
                page.locator('[data-projection-id="standalone"]').get_attribute("aria-pressed")
                == expected_selection
            )
        finally:
            browser.close()


def test_absent_multi_package_component_uses_declared_identity_across_views(tmp_path: Path) -> None:
    page_html, _, _ = _acceptance_page(tmp_path, include_absent_component=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="diff"]').click()
            page.locator('[data-projection-id="diff:absent"]').click()
            page.locator('[data-projection-id="absent:COMP-GHOST"]').click()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-breadcrumb").inner_text().endswith("ghost")
            assert page.locator(".flow-inspector").get_by_role("heading", name="ghost").is_visible()
            assert page.locator(".flow-projection-context").count() == 0
            page.locator('[data-flow-view="diff"]').click()
            assert (
                page.locator('[data-projection-id="absent:COMP-GHOST"]').get_attribute(
                    "aria-pressed"
                )
                == "true"
            )
            assert page.locator(".flow-projection-context").count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("navigation", ["card", "edge", "breadcrumb", "back", "escape", "index"])
def test_explicit_target_navigation_clears_fallback_context(
    tmp_path: Path, navigation: str
) -> None:
    page_html, _, _ = _acceptance_page(
        tmp_path,
        extra_files={
            "shop/app/unclaimed.py": "VALUE = 2\n",
            "shop/store/unclaimed.py": "VALUE = 3\n",
        },
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.set_content(page_html, wait_until="load")
            if navigation in {"edge", "breadcrumb", "back", "escape"}:
                page.locator('[data-flow-view="actual"]').click()
                path = (
                    ["shop", "shop.orphan"]
                    if navigation == "edge"
                    else [
                        "shop",
                        "shop.app",
                        "shop.app.unclaimed",
                    ]
                )
                for node_id in path:
                    page.locator(f'[data-projection-id="{node_id}"]').click()
            else:
                page.locator('[data-flow-view="diff"]').click()
                page.locator('[data-projection-id="diff:violations"]').click()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(".flow-projection-context").is_visible()
            if navigation == "card":
                page.locator('.target-node[data-target-node="COMP-APP"]').click()
                assert (
                    page.locator(".flow-inspector").get_by_role("heading", name="app").is_visible()
                )
            elif navigation == "edge":
                edge = page.locator('[data-target-edge="physical:shop.app"]')
                edge.focus()
                page.keyboard.press("Enter")
                assert edge.get_attribute("aria-pressed") == "true"
                assert page.locator(".flow-selected-responsibility").is_hidden()
            elif navigation == "breadcrumb":
                page.locator(".flow-breadcrumb button").first.click()
                assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            elif navigation == "back":
                assert page.locator(".flow-breadcrumb").inner_text().endswith("app")
                page.locator(".flow-back").click()
                assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            elif navigation == "escape":
                assert page.locator(".flow-breadcrumb").inner_text().endswith("app")
                page.keyboard.press("Escape")
                assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            else:
                page.locator(".flow-responsibilities summary").click()
                page.locator(".flow-responsibility-search").fill("app")
                page.locator(".flow-responsibility-list button:visible").first.click()
                assert (
                    page.locator(".flow-inspector").get_by_role("heading", name="app").is_visible()
                )
            assert page.locator(".flow-projection-context").count() == 0
            if navigation == "edge":
                page.locator('[data-flow-view="actual"]').click()
                visible_path = page.locator(".flow-projection-breadcrumb")
                assert visible_path.is_visible()
                assert " ".join(visible_path.inner_text().split()) == "Actual / shop / app"
                assert (
                    page.locator('[data-projection-id="shop.orphan"][aria-pressed="true"]').count()
                    == 0
                )
                assert page.locator(".flow-selected-responsibility").is_hidden()
            assert page_errors == []
        finally:
            browser.close()
