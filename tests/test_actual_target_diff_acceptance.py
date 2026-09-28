# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Acceptance checks for the report's Actual, Target, and Diff projections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _acceptance_page(tmp_path: Path) -> tuple[str, dict[str, Any], set[str]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    root_layout["allowed_children"].append("shop.missing")
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        "shop/orphan.py": "VALUE = 1\n",
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
