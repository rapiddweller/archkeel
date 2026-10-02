# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target leaves preserve exact module identity without observed-file inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_consistent_explorer_acceptance import _browser_page, _open_details
from test_declared_module_targets import _module, _walk
from test_exact_module_ownership import _component, _contract, _report

from fixtures.architecture_demo import main as demo_main


def _exact_target_nodes(payload: dict[str, Any], module: str) -> list[dict[str, Any]]:
    return [
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target" and node["label"] == module
    ]


def test_source_free_exact_claim_is_a_childless_target_leaf(tmp_path: Path) -> None:
    _, _, payload, actual = _report(
        tmp_path,
        _contract([_component("registry", [], exact_modules=["sample.core"])]),
        source_paths=[],
    )
    assert actual == set()

    leaves = _exact_target_nodes(payload, "sample.core")
    assert len(leaves) == 1
    leaf = leaves[0]
    assert leaf["children"] == []
    assert not any(detail["label"] == "File" for detail in leaf["details"])
    assert not any(
        node["kind"] == "package_scope" and node["label"] == "sample.core"
        for node in _walk(payload["explorers"]["target"])
    )

    graph = payload["explorers"]["target_diagrams"]["nested"]["COMP-REGISTRY"]
    assert any(
        node["id"] == leaf["id"] and node["kind"] == "module_target" for node in graph["nodes"]
    )
    assert any(
        edge["kind"] == "contains" and edge["target"] == leaf["id"] for edge in graph["edges"]
    )


def test_exact_leaf_reconciles_matching_explicit_module_declaration(tmp_path: Path) -> None:
    contract = _contract([_component("registry", [], exact_modules=["sample.core"])])
    contract["declarations"] = {
        "modules": [_module("sample/core/__init__.py", "Own the declared initializer.")]
    }
    _, _, payload, _ = _report(tmp_path, contract)
    target = list(_walk(payload["explorers"]["target"]))
    matching = [
        node
        for node in target
        if node["kind"] == "module_target"
        and (
            node["label"] == "sample.core"
            or any(
                detail["label"] == "File" and detail["value"] == "sample/core/__init__.py"
                for detail in node["details"]
            )
        )
    ]
    assert len(matching) == 1
    leaf = matching[0]
    assert leaf["label"] == "sample.core"
    details = {detail["label"]: detail["value"] for detail in leaf["details"]}
    assert details["File"] == "sample/core/__init__.py"
    assert details["Responsibility"] == "Own the declared initializer."


@pytest.mark.parametrize(
    "modules",
    [
        [
            _module("sample/core.py", "Own the module file."),
            _module("sample/core/__init__.py", "Own the package initializer."),
        ],
        [
            _module("sample/core/__init__.py", "Own the package initializer."),
            _module("sample/core.py", "Own the module file."),
        ],
    ],
    ids=["module-then-initializer", "initializer-then-module"],
)
def test_exact_claim_preserves_distinct_explicit_targets_in_either_order(
    tmp_path: Path, modules: list[dict[str, str]]
) -> None:
    contract = _contract([_component("registry", [], exact_modules=["sample.core"])])
    contract["declarations"] = {"modules": modules}
    _, _, payload, _ = _report(tmp_path, contract)

    target = list(_walk(payload["explorers"]["target"]))
    explicit = {
        path: {
            node["id"]: {detail["label"]: detail["value"] for detail in node["details"]}
            for node in target
            if node["kind"] == "module_target"
            and any(
                detail["label"] == "File" and detail["value"] == path for detail in node["details"]
            )
        }
        for path in ("sample/core.py", "sample/core/__init__.py")
    }
    expected_responsibilities = {
        "sample/core.py": "Own the module file.",
        "sample/core/__init__.py": "Own the package initializer.",
    }
    assert {path for path, nodes in explicit.items() if len(nodes) == 1} == set(
        expected_responsibilities
    )
    for path, nodes in explicit.items():
        ((_, details),) = nodes.items()
        assert details["Responsibility"] == expected_responsibilities[path]
        assert details["File"] == path

    explicit_ids = {next(iter(nodes)) for nodes in explicit.values()}
    synthetic = [
        node
        for node in target
        if node["kind"] == "module_target"
        and node["label"] == "sample.core"
        and not any(detail["label"] == "File" for detail in node["details"])
    ]
    assert synthetic == []

    graph = payload["explorers"]["target_diagrams"]["nested"]["COMP-REGISTRY"]
    graph_ids = {node["id"] for node in graph["nodes"]}
    assert explicit_ids <= graph_ids


def test_positive_demo_navigates_and_selects_observed_exact_initializer_in_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "positive.json"
    assert demo_main(["--replay", "ownership-exact-module-positive", "--output", str(output)]) == 0
    capsys.readouterr()
    html = output.with_name("positive.report.html").read_text()
    page_html_start = html.index('id="flow-data"')
    payload = json.loads(
        html[html.index(">", page_html_start) + 1 : html.index("</script>", page_html_start)]
    )

    playwright_api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(playwright_api, html)
    try:
        page.locator('[data-flow-view="actual"]').click()
        _open_details(page)
        page.locator('[data-projection-id="shop"]').click()
        page.locator(".flow-open-selected").click()
        page.locator('[data-projection-id="shop.store"]').click()
        assert "shop/store/__init__.py" in page.locator(".flow-inspector").inner_text()

        page.locator('[data-flow-view="target"]').click()
        _open_details(page)
        page.locator('[data-target-node="COMP-STORE"]').press("Enter")
        page.locator('[data-target-node="store:COMP-STORE-REPOSITORY"]').press("Enter")
        leaf = page.locator('.flow-nodes .target-node.module[data-label="shop.store"]')
        assert leaf.is_visible()
        node_id = leaf.get_attribute("data-target-node")
        target_leaf = next(
            node for node in _walk(payload["explorers"]["target"]) if node["id"] == node_id
        )
        assert target_leaf["kind"] == "module_target"
        assert target_leaf["children"] == []
        assert not any(detail["label"] == "File" for detail in target_leaf["details"])

        leaf.click()
        selected = page.locator(".flow-selected-responsibility")
        assert selected.get_attribute("data-declaration-id") == node_id
        assert "shop.store" in page.locator(".flow-inspector").inner_text()
        assert "shop/store/__init__.py" not in page.locator(".flow-inspector").inner_text()

        page.locator('[data-flow-view="actual"]').click()
        page.locator('[data-flow-view="target"]').click()
        leaf = page.locator(f'.flow-nodes .target-node.module[data-target-node="{node_id}"]')
        assert leaf.get_attribute("aria-pressed") == "true"
        assert selected.get_attribute("data-declaration-id") == node_id

        page.locator("button.flow-back").click()
        assert page.locator('[data-target-node="store:COMP-STORE-API"]').is_visible()
        page.locator('[aria-label="Diagram breadcrumb"] button').first.click()
        assert page.locator('[data-target-node="COMP-STORE"]').is_visible()
    finally:
        browser.close()
        playwright.stop()
