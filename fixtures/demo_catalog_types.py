# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 symbol_placement and boundary_types rows (issue #9, AD-58).

MODEL-TYPES-IN-ENTITIES and APP-TYPES-NOT-DICT are declared directly on the clean sample's own
`architecture-contract.json` (AD-11, issue #47), since the clean tree already satisfies both;
these rows overlay only the violating file, not the rule.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant

# Public so demo_catalog_showcase can reuse this family's file content instead of duplicating it.
ROGUE_DATACLASS_MODULE = HEADER + (
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
    files={"shop/model/promotions.py": ROGUE_DATACLASS_MODULE},
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
    files={"shop/app/reports.py": _BROAD_PARAM_MODULE},
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

VARIANTS: tuple[Variant, ...] = (_SYMBOL_PLACEMENT, _BOUNDARY_TYPES)
