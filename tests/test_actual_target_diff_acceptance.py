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
                "packages": ["shop.ghost"],
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
