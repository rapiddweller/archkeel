# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-86 root layout demos, and AD-107's child whose own file has no text to quote."""

from __future__ import annotations

import json

from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    Variant,
    contract_component_field_set,
    contract_rule_field,
    contract_with_rule,
)


def _module_target_contract(path: str) -> str:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    contract.setdefault("declarations", {})["modules"] = [
        {"path": path, "responsibility": "Coordinate order workflows."}
    ]
    return json.dumps(contract)


def _empty_responsibility_files() -> dict[str, str]:
    nested = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    next(item for item in nested["components"] if item["id"] == "COMP-STORE-API")[
        "responsibilities"
    ] = []
    return {
        "architecture-contract.json": contract_component_field_set("app", "responsibilities", []),
        "shop/store/architecture-contract.json": json.dumps(nested),
    }


def _target_hierarchy_files(case: str) -> dict[str, str]:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    if case == "missing":
        root_layout["allowed_children"].append("shop.missing")
    elif case == "ambiguous":
        contract["rules"].append(
            {
                **root_layout,
                "id": "ROOT-LAYOUT-SECOND",
                "rationale": "Second declaration for the same physical root.",
            }
        )
    elif case == "cycle":
        app = next(
            component for component in contract["components"] if component["id"] == "COMP-APP"
        )
        cli = next(
            component for component in contract["components"] if component["id"] == "COMP-CLI"
        )
        store = next(
            component for component in contract["components"] if component["id"] == "COMP-STORE"
        )
        app["requires"] = [{"component": "store", "rationale": "The target declares app to store."}]
        store["requires"] = [
            {"component": "app", "rationale": "The target declares store back to app."}
        ]
        cli["requires"] = [{"component": "app", "rationale": "The target declares CLI after app."}]
    elif case != "positive":
        raise ValueError(f"unknown target hierarchy case: {case}")

    nested = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    if case == "positive":
        app = next(
            component for component in contract["components"] if component["id"] == "COMP-APP"
        )
        app["requires"] = [
            {
                "component": "store",
                "through": ["shop.store.repository:OrderRepository"],
                "rationale": "Order use cases persist through the declared repository API.",
            }
        ]
        nested["rules"].append(
            {
                "id": "STORE-ROOT-LAYOUT",
                "kind": "root_layout",
                "root": "shop.store",
                "allowed_children": [
                    "shop.store.backend",
                    "shop.store.codec",
                    "shop.store.repository",
                    "shop.store.sqlite",
                ],
                "rationale": "The store root exposes its declared immediate children.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    files = {
        "architecture-contract.json": json.dumps(contract),
        "shop/store/architecture-contract.json": json.dumps(nested),
    }
    if case == "cycle":
        target_graph = (FIXTURE_DIR / "docs/architecture/shop.md").read_text()
        marker = "<!-- archkeel-target-graph -->"
        before, separator, after = target_graph.partition(marker)
        if not separator:
            raise ValueError("shop fixture has no target graph marker")
        files["docs/architecture/shop.md"] = (
            before
            + separator
            + after.replace("    store --> model\n", "    store --> app\n    store --> model\n", 1)
        )
    return files


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="target-module-present",
        section="clean",
        item="declarations.modules:present",
        summary="The Target report reaches the declared shop/app/orders.py file and its "
        "responsibility.",
        files={"architecture-contract.json": _module_target_contract("shop/app/orders.py")},
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="target-module-absent",
        section="clean",
        item="declarations.modules:absent",
        summary="The Target report retains a missing file while Diff names it as absent.",
        files={"architecture-contract.json": _module_target_contract("shop/app/missing.py")},
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="target-empty-responsibilities",
        section="clean",
        item="target.responsibilities:missing",
        summary="Target shows missing responsibility design information; the unowned store facade "
        "keeps STORE-REQUIRES-COMPLETE unproven.",
        files=_empty_responsibility_files(),
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="target-hierarchy-positive",
        section="clean",
        item="target.hierarchy:declared",
        summary="The declared shop and store roots expose one nested physical hierarchy.",
        files=_target_hierarchy_files("positive"),
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="target-hierarchy-ambiguous",
        section="clean",
        item="target.hierarchy:ambiguous-root",
        summary="Two declarations for the same root stay explicit and do not guess placement.",
        files=_target_hierarchy_files("ambiguous"),
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="target-hierarchy-missing",
        section="clean",
        item="target.hierarchy:missing-child",
        summary="An allowed child with no observed package remains a declared physical target.",
        files=_target_hierarchy_files("missing"),
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="target-hierarchy-cycle",
        section="clean",
        item="target.hierarchy:requirement-cycle",
        summary="A declared target cycle remains inspectable without changing the shop verdict.",
        files=_target_hierarchy_files("cycle"),
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="class-a-root-layout-clean",
        section="clean",
        item="root_layout:clean",
        summary="The shop root contains only its five declared immediate children.",
        files={},
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="class-a-root-layout-nested-root",
        section="clean",
        item="root_layout:nested-root",
        summary="A nested package root may declare its own immediate children.",
        files={
            "architecture-contract.json": contract_with_rule(
                {
                    "id": "ROOT-LAYOUT-STORE",
                    "kind": "root_layout",
                    "root": "shop.store",
                    "allowed_children": [
                        "shop.store.backend",
                        "shop.store.codec",
                        "shop.store.repository",
                        "shop.store.sqlite",
                    ],
                    "rationale": "The store root exposes only its declared immediate children.",
                    "provenance": ["docs/architecture/shop.md"],
                    "decided_by": "architect",
                }
            )
        },
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="validation-root-layout-invalid-child",
        section="validation",
        item="root_layout:invalid-contract",
        summary="A nested allowed child is rejected at the contract boundary.",
        files={
            "architecture-contract.json": contract_rule_field(
                "ROOT-LAYOUT", allowed_children=["shop.store.backend.nested"]
            )
        },
        expected_violations=(),
        expected_codes=("contract.invalid",),
    ),
    Variant(
        id="class-a-root-layout-violation",
        section="class_a",
        item="root_layout:unexpected-child",
        summary="An unexpected module directly below shop is a root layout violation.",
        files={"shop/rogue.py": HEADER + '"""Unexpected root child."""\n\nVALUE = 1\n'},
        expected_violations=("ASSIGNMENT-COMPLETE", "ROOT-LAYOUT"),
        expected_codes=("rule.violated", "rule.violated"),
    ),
    Variant(
        id="class-a-root-layout-empty-package",
        section="class_a",
        item="root_layout:empty-initializer",
        summary="An unexpected package whose __init__.py is empty is the same root layout "
        "violation a docstring gives: the file is the evidence, not its first line (AD-107).",
        files={"shop/extra/__init__.py": ""},
        expected_violations=("ROOT-LAYOUT",),
        expected_codes=("rule.violated",),
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="class-a-root-layout-blank-first-line",
        section="class_a",
        item="root_layout:blank-first-line",
        summary="An unowned root module whose first line is blank fails both module rules "
        "instead of turning the run UNKNOWN (AD-107).",
        files={"shop/stray.py": "\nVALUE = 1\n"},
        expected_violations=("ASSIGNMENT-COMPLETE", "ROOT-LAYOUT"),
        expected_codes=("rule.violated", "rule.violated"),
        expected_declared_rules="FAIL",
    ),
)
