# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-86 root layout demos, and AD-107's child whose own file has no text to quote."""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant, contract_rule_field, contract_with_rule

VARIANTS: tuple[Variant, ...] = (
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
