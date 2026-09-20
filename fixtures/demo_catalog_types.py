# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 symbol_placement and boundary_types rows (issue #9, AD-58, AD-63).

MODEL-TYPES-IN-ENTITIES and APP-TYPES-NOT-DICT are declared directly on the clean sample's own
`architecture-contract.json` (AD-11, issue #47), since the clean tree already satisfies both;
these rows overlay only the violating file (and, since AD-63, the `public` entry that makes the
new function a facade function at all), not the rule.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant, contract_component_field_appended

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

_CLI_IMPORTS_REPORTS = HEADER + (
    '"""Argument parsing and composition; the single broad error boundary lives here."""\n\n'
    "from __future__ import annotations\n\n"
    "from pathlib import Path\n"
    "from typing import TYPE_CHECKING\n\n"
    "from shop.app.orders import place_order\n"
    "from shop.render.text import render_order\n\n"
    "if TYPE_CHECKING:\n"
    "    # Type-only, so the new public entry is used and not interface.unused (AD-56).\n"
    "    from shop.app.reports import snapshot\n\n\n"
    "def main(argv: list[str]) -> int:\n"
    "    try:\n"
    "        order_id, description, quantity, unit_price_cents, store_dir = argv\n"
    "        order = place_order(\n"
    "            Path(store_dir), order_id, description, int(quantity), int(unit_price_cents)\n"
    "        )\n"
    "        print(render_order(order))\n"
    "        return 0\n"
    "    except Exception:\n"
    "        return 1\n"
)

_BOUNDARY_TYPES = Variant(
    id="class-a-boundary-types",
    section="class_a",
    item="boundary_types:dict",
    summary="A new shop.app.reports:snapshot, declared in shop.app's own public list, takes a "
    "bare dict, which APP-TYPES-NOT-DICT reports: a facade decides what crosses it, never a "
    "dict or object standing in for a typed model (AD-58). Only a function the component's "
    "own public list declares is inspected -- a naming convention over every non-underscore "
    "function used to decide this instead, until issue #44 amended it to read the contract's "
    "declared facade (AD-63).",
    files={
        "shop/app/reports.py": _BROAD_PARAM_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": contract_component_field_appended(
            "app", "public", "shop.app.reports:snapshot"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

_UNDECLARED_TYPE_MODULE = HEADER + (
    '"""A stray function naming a type shop.app never declared, for the boundary-types '
    'demo."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.model.entities import Money, Order\n\n\n"
    "class Extra:\n"
    '    """Defined here, and never declared in shop.app\'s public list."""\n\n'
    "    def __init__(self, detail: str) -> None:\n"
    "        self.detail = detail\n\n\n"
    "def summarize(order: Order, extra: Extra) -> Money:\n"
    '    """Order and Money are shop.model\'s own declared facade; Extra never is anybody\'s."""\n'
    "    print(extra.detail)\n"
    "    return order.total()\n"
)

_BOUNDARY_TYPES_DECLARED = Variant(
    id="class-a-boundary-types-declared-type",
    section="class_a",
    item="boundary_types:declared_type",
    summary="A new shop.app.discounts:summarize, declared in shop.app's own public list, "
    "takes Order and returns Money -- both declared in shop.model's own facade, so "
    "APP-TYPES-NOT-DICT stays silent there, the provider-owns-the-contract pattern AD-58's own "
    "measurement mistook for a false positive -- and also takes Extra, a class defined right "
    "there and declared by nobody, which the rule reports: a bare name now resolves through "
    "the same import bindings interface_boundary reads (AD-63).",
    files={
        "shop/app/discounts.py": _UNDECLARED_TYPE_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS.replace(
            "from shop.app.reports import snapshot", "from shop.app.discounts import summarize"
        ),
        "architecture-contract.json": contract_component_field_appended(
            "app", "public", "shop.app.discounts:summarize"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

VARIANTS: tuple[Variant, ...] = (_SYMBOL_PLACEMENT, _BOUNDARY_TYPES, _BOUNDARY_TYPES_DECLARED)
