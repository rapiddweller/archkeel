# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 symbol_placement and boundary_types rows (issue #9, AD-58)."""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant, contract_with_rule

_ROGUE_DATACLASS_MODULE = HEADER + (
    '"""A dataclass declared outside shop.model.entities, for the placement demo."""\n\n'
    "from __future__ import annotations\n\n"
    "from dataclasses import dataclass\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class Coupon:\n"
    "    code: str\n"
)

_SYMBOL_PLACEMENT = Variant(
    id="class-a-symbol-placement",
    section="class_a",
    item="symbol_placement:exact_sources",
    summary="A new shop.model.promotions module declares a dataclass outside "
    "shop.model.entities, the only module MODEL-TYPES-IN-ENTITIES allows for a dataclass "
    "below shop.model (AD-49, AD-58).",
    files={
        "shop/model/promotions.py": _ROGUE_DATACLASS_MODULE,
        "architecture-contract.json": contract_with_rule(
            {
                "id": "MODEL-TYPES-IN-ENTITIES",
                "kind": "symbol_placement",
                "source": "shop.model",
                "class_kinds": ["dataclass"],
                "exact_sources": ["shop.model.entities"],
                "rationale": "Every order, line and money type shop.model owns lives in one "
                "module, not scattered across the package.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        ),
    },
    expected_violations=("MODEL-TYPES-IN-ENTITIES",),
    expected_codes=("rule.violated",),
)

_BROAD_PARAM_MODULE = HEADER + (
    '"""A stray function taking a bare dict, for the boundary-types demo."""\n\n'
    "from __future__ import annotations\n\n\n"
    "def snapshot(context: dict) -> str:\n"
    "    return str(context)\n"
)

_BOUNDARY_TYPES = Variant(
    id="class-a-boundary-types",
    section="class_a",
    item="boundary_types:dict",
    summary="A new shop.app.reports module takes a bare dict, which APP-TYPES-NOT-DICT "
    "reports: a facade decides what crosses it, never a dict or object standing in for a "
    "typed model (AD-58). Restricted to what the annotation string alone decides (issue #9 "
    "part 2): no name is resolved, so only a bare dict/Dict/object or a dict[...]/Dict[...] "
    "generic fires.",
    files={
        "shop/app/reports.py": _BROAD_PARAM_MODULE,
        "architecture-contract.json": contract_with_rule(
            {
                "id": "APP-TYPES-NOT-DICT",
                "kind": "boundary_types",
                "source": "shop.app",
                "rationale": "shop.app's functions take and return typed models, never a "
                "bare dict standing in for one.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

VARIANTS: tuple[Variant, ...] = (_SYMBOL_PLACEMENT, _BOUNDARY_TYPES)
