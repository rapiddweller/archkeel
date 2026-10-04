# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-128 executable examples for exact module ownership."""

from __future__ import annotations

import json

from fixtures.demo_catalog_support import FIXTURE_DIR, Variant


def _exact_overlay(owner: str) -> str:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    component = next(item for item in contract["components"] if item["label"] == owner)
    component["exact_modules"] = ["shop.store.repository"]
    return json.dumps(contract, indent=2) + "\n"


def _repository_initializer_overlay() -> str:
    contract = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    repository = next(item for item in contract["components"] if item["label"] == "repository")
    repository["exact_modules"] = ["shop.store"]
    return json.dumps(contract, indent=2) + "\n"


VARIANTS = (
    Variant(
        id="ownership-exact-module-positive",
        section="class_d",
        item="exact_module_ownership:package initializer",
        summary="the store initializer's OrderRepository re-export is assigned exactly to the "
        "existing repository owner; sibling store modules retain their declared owners under "
        "STORE-REQUIRES-COMPLETE.",
        files={"shop/store/architecture-contract.json": _repository_initializer_overlay()},
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="PASS",
    ),
    Variant(
        id="ownership-exact-module-not-recursive",
        section="class_d",
        item="exact_module_ownership:sibling import remains separate",
        summary="a new backend sibling imports the repository without a declared requirement; the "
        "exact shop.store initializer claim does not recursively absorb it.",
        files={
            "shop/store/architecture-contract.json": _repository_initializer_overlay(),
            "shop/store/backend/probe.py": "from shop.store.repository import OrderRepository\n\n"
            "REPOSITORY_TYPE = OrderRepository\n",
        },
        expected_violations=("store:STORE-REQUIRES-COMPLETE",),
        expected_codes=("rule.violated",),
    ),
    Variant(
        id="ownership-exact-module-ambiguous",
        section="class_d",
        item="exact_module_ownership:competing owner",
        summary="app's exact claim overlaps store's recursive package claim; ArchKeel does not "
        "choose selector precedence or assign the module twice.",
        files={"architecture-contract.json": _exact_overlay("app")},
        expected_violations=("ASSIGNMENT-COMPLETE", "DEP-STORE-NO-APP"),
        expected_codes=("reference.public_owner",),
    ),
)
