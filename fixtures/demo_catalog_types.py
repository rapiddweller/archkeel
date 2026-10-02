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

import json

from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    Variant,
    contract_component_field_appended,
)

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

_MAPPING_PARAM_MODULE = HEADER + (
    '"""An open map at a declared application boundary."""\n\n'
    "from __future__ import annotations\n\n"
    "from collections.abc import Mapping\n\n\n"
    "def snapshot(context: Mapping[str, str]) -> str:\n"
    "    return str(len(context))\n"
)


def _mapping_contract(*, allowed: bool) -> str:
    contract = json.loads(
        contract_component_field_appended("app", "public", "shop.app.reports:snapshot")
    )
    if allowed:
        rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
        rule["allowed_positions"] = [
            {
                "qualified_name": "shop.app.reports.snapshot",
                "position": "context",
                "field_path": "",
                "annotation": "Mapping[str, str]",
            }
        ]
    return json.dumps(contract, indent=2) + "\n"


_MAPPING_BROAD = Variant(
    id="class-a-boundary-types-mapping",
    section="class_a",
    item="boundary_types:proven_mapping",
    summary="A proven standard-library Mapping[str, str] is an open record and violates "
    "the typed boundary (AD-123).",
    files={
        "shop/app/reports.py": _MAPPING_PARAM_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _mapping_contract(allowed=False),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

_MAPPING_ALLOWED = Variant(
    id="class-a-boundary-types-mapping-allowed",
    section="class_a",
    item="boundary_types:exact_open_mapping",
    summary="One exact top-level allowance documents an intentional open map; the same "
    "boundary otherwise stays checked (AD-123).",
    files={
        "shop/app/reports.py": _MAPPING_PARAM_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _mapping_contract(allowed=True),
    },
    expected_violations=(),
    expected_codes=(),
)


def _opaque_map_contract(*, values: bool) -> str:
    contract = json.loads(_mapping_contract(allowed=False))
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    rule["allowed_positions"] = [
        {
            "qualified_name": "shop.app.reports.snapshot",
            "position": position,
            "annotation": "dict[str, object]",
            **({"container_depth": 1} if value else {}),
        }
        for position in ("context", "return")
        for value in ((False, True) if values else (False,))
    ]
    rule["rationale"] = "Validate this raw map before model construction; preserve its identity."
    return json.dumps(contract, indent=2) + "\n"


_RAW_MAP_SOURCE = HEADER + (
    "from __future__ import annotations\n\n"
    "def snapshot(context: dict[str, object]) -> dict[str, object]:\n"
    "    if 'count' not in context: raise ValueError('count required')\n"
    "    return context\n"
)

_OPAQUE_MAP_VALUES = Variant(
    id="class-a-boundary-types-opaque-map-values",
    section="class_a",
    item="boundary_types:exact_opaque_map_values",
    summary="Separate outer-map and depth-1 value decisions accept raw input/return opacity "
    "with provenance; type closure remains unproven (AD-142).",
    files={
        "shop/app/reports.py": _RAW_MAP_SOURCE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _opaque_map_contract(values=True),
    },
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)

_OPAQUE_MAP_VALUES_MISSING = Variant(
    id="class-a-boundary-types-opaque-map-values-missing",
    section="class_a",
    item="boundary_types:outer_map_keeps_opaque_values",
    summary="Two outer-map decisions leave both unnamed object values forbidden (AD-142).",
    files={
        **_OPAQUE_MAP_VALUES.files,
        "architecture-contract.json": _opaque_map_contract(values=False),
    },
    expected_violations=("APP-TYPES-NOT-DICT", "APP-TYPES-NOT-DICT"),
    expected_codes=("rule.violated", "rule.violated"),
)

_OPAQUE_MAP_VALUES_UNKNOWN = Variant(
    id="class-a-boundary-types-opaque-map-values-unknown",
    section="class_a",
    item="boundary_types:opaque_map_keeps_unknown",
    summary="Accepted raw-map opacity leaves an unresolved neighboring parameter UNKNOWN (AD-142).",
    files={
        **_OPAQUE_MAP_VALUES.files,
        "shop/app/reports.py": _RAW_MAP_SOURCE.replace(
            "context: dict[str, object])", "context: dict[str, object], pending: Missing)"
        ),
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("boundary_type_limit", "shop.app"),),
    expected_declared_rules="UNKNOWN",
)


def _contained_mapping_contract(annotation: str) -> str:
    contract = json.loads(
        contract_component_field_appended(
            "app", "public", "shop.app.reports:read_csv_having_weight_column"
        )
    )
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    rule["allowed_positions"] = [
        {
            "qualified_name": "shop.app.reports.read_csv_having_weight_column",
            "position": "return",
            "field_path": "",
            "annotation": annotation,
        }
    ]
    return json.dumps(contract, indent=2) + "\n"


def _contained_mapping_source(annotation: str) -> str:
    return HEADER + f"def read_csv_having_weight_column() -> {annotation}:\n    return ([], [])\n"


_CONTAINED_MAPPING_CLI = _CLI_IMPORTS_REPORTS.replace(
    "from shop.app.reports import snapshot",
    "from shop.app.reports import read_csv_having_weight_column",
)


_CONTAINED_MAPPING = Variant(
    id="class-a-boundary-types-contained-mapping",
    section="class_a",
    item="boundary_types:unique_contained_mapping",
    summary="An exact full-signature allowance applies to one contained mapping and records its "
    "annotation and depth; it does not turn another member into PASS (AD-127).",
    files={
        "shop/app/reports.py": _contained_mapping_source(
            "tuple[list[float], list[dict[str, str]]]"
        ),
        "shop/cli/main.py": _CONTAINED_MAPPING_CLI,
        "architecture-contract.json": _contained_mapping_contract(
            "tuple[list[float], list[dict[str, str]]]"
        ),
    },
    expected_violations=(),
    expected_codes=(),
)

_CONTAINED_MAPPING_SIBLINGS = Variant(
    id="class-a-boundary-types-contained-mapping-siblings",
    section="class_a",
    item="boundary_types:ambiguous_contained_mappings",
    summary="Two identical contained mappings count as two occurrences before finding dedup, so "
    "the allowance stays unused (AD-127).",
    files={
        "shop/app/reports.py": _contained_mapping_source(
            "tuple[list[float], list[dict[str, str]], list[dict[str, str]]]"
        ),
        "shop/cli/main.py": _CONTAINED_MAPPING_CLI,
        "architecture-contract.json": _contained_mapping_contract(
            "tuple[list[float], list[dict[str, str]], list[dict[str, str]]]"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

_CONTAINED_MAPPING_UNKNOWN = Variant(
    id="class-a-boundary-types-contained-mapping-unknown",
    section="class_a",
    item="boundary_types:contained_mapping_unknown_member",
    summary="The unique map is allowed, while its unresolved member remains UNKNOWN (AD-127).",
    files={
        "shop/app/reports.py": _contained_mapping_source(
            "tuple[list[float], list[dict[str, MissingRow]]]"
        ),
        "shop/cli/main.py": _CONTAINED_MAPPING_CLI,
        "architecture-contract.json": _contained_mapping_contract(
            "tuple[list[float], list[dict[str, MissingRow]]]"
        ),
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("boundary_type_limit", "shop.app"),),
    expected_declared_rules="UNKNOWN",
)

_DICT_ALLOWANCE = {
    "qualified_name": "shop.app.reports.snapshot",
    "position": "return",
    "field_path": "",
    "annotation": "dict[str, str]",
}


def _dict_allowance_contract() -> str:
    contract = json.loads(
        contract_component_field_appended("app", "public", "shop.app.reports:snapshot")
    )
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    rule["allowed_positions"] = [_DICT_ALLOWANCE]
    return json.dumps(contract, indent=2) + "\n"


_BUILTIN_DICT_ALLOWED = Variant(
    id="class-a-boundary-types-builtin-dict-allowed",
    section="class_a",
    item="boundary_types:exact_builtin_dict",
    summary="The exact allowance accepts the builtin dict boundary; the unowned store facade "
    "keeps aggregate declared rules UNKNOWN.",
    files={
        "shop/app/reports.py": HEADER + "def snapshot() -> dict[str, str]:\n    return {}\n",
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _dict_allowance_contract(),
    },
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)


def _direct_position_contract(*, neighbors: bool = False) -> str:
    contract = json.loads(_dict_allowance_contract())
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    del rule["allowed_positions"][0]["field_path"]
    if neighbors:
        app = next(item for item in contract["components"] if item["label"] == "app")
        app["public"].append("shop.app.reports:Request")
    return json.dumps(contract, indent=2) + "\n"


_DIRECT_POSITION_ALLOWED = Variant(
    id="class-a-boundary-types-direct-default",
    section="class_a",
    item="boundary_types:omitted_root_path",
    summary="Omitting field_path selects the exact direct return (AD-134, #207).",
    files={
        **_BUILTIN_DICT_ALLOWED.files,
        "architecture-contract.json": _direct_position_contract(),
    },
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)

_DIRECT_POSITION_NEIGHBORS = Variant(
    id="class-a-boundary-types-direct-neighbors",
    section="class_a",
    item="boundary_types:direct_allowance_keeps_neighbors",
    summary="The allowed return keeps broad inputs and nested fields visible (AD-134, #207).",
    files={
        "shop/app/reports.py": HEADER
        + (
            "class Request:\n"
            "    payload: dict[str, str]\n\n"
            "def snapshot(context: dict[str, str], request: Request) -> dict[str, str]:\n"
            "    return {}\n"
        ),
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _direct_position_contract(neighbors=True),
    },
    expected_violations=("APP-TYPES-NOT-DICT", "APP-TYPES-NOT-DICT"),
    expected_codes=("rule.violated", "rule.violated"),
)

_SHADOWED_DICT_ALLOWED = Variant(
    id="class-a-boundary-types-shadowed-dict-unknown",
    section="class_a",
    item="boundary_types:shadowed_dict_unknown",
    summary="The same allowance cannot prove a module-local dict; the boundary stays UNKNOWN.",
    files={
        "shop/app/reports.py": HEADER
        + "from __future__ import annotations\n\n\n"
        + "class dict:\n    pass\n\n\ndef snapshot() -> dict[str, str]:\n    return {}\n",
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": _dict_allowance_contract(),
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("boundary_type_limit", "shop.app"),),
    expected_declared_rules="UNKNOWN",
)


def _native_payload_contract() -> str:
    contract = json.loads(
        contract_component_field_appended("app", "public", "shop.app.reports:Converter")
    )
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    rule["allowed_positions"] = [
        {
            "qualified_name": "shop.app.reports.Converter.convert",
            "position": "value",
            "annotation": "object",
        }
    ]
    rule["rationale"] = "Accept the exact native payload as opaque; keep execution controls typed."
    return json.dumps(contract, indent=2) + "\n"


_NATIVE_PAYLOAD_ALLOWED = Variant(
    id="class-a-boundary-types-native-payload",
    section="class_a",
    item="boundary_types:exact_native_payload",
    summary="One exact object payload accepts opacity with its decision provenance (AD-135).",
    files={
        "shop/app/reports.py": HEADER
        + "class Converter:\n    def convert(self, value: object) -> str: return str(value)\n",
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS.replace(
            "from shop.app.reports import snapshot", "from shop.app.reports import Converter"
        ),
        "architecture-contract.json": _native_payload_contract(),
    },
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)

_NATIVE_PAYLOAD_NEIGHBORS = Variant(
    id="class-a-boundary-types-native-controls",
    section="class_a",
    item="boundary_types:native_payload_keeps_controls",
    summary="The accepted payload keeps returns, constructor context, masks and other methods "
    "forbidden (AD-135).",
    files={
        **_NATIVE_PAYLOAD_ALLOWED.files,
        "shop/app/reports.py": HEADER
        + (
            "class Converter:\n"
            "    def __init__(self, ctx: object) -> None: self.ctx = ctx\n"
            "    def convert(self, value: object, mask: object) -> object: return value\n"
            "    def other(self, value: object) -> object: return value\n"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",) * 5,
    expected_codes=("rule.violated",) * 5,
)

_BOUNDARY_TYPES_MIXED_EVIDENCE = Variant(
    id="class-a-boundary-types-mixed-evidence",
    section="class_a",
    item="boundary_types:mixed_fail_unknown",
    summary="shop.app.reports.snapshot has a known bare-dict violation and an unresolved "
    "FutureOrder parameter. The same rule assessment stays FAIL with one UNKNOWN position.",
    files={
        "shop/app/reports.py": _BROAD_PARAM_MODULE.replace(
            "def snapshot(context: dict) -> str:",
            "def snapshot(context: dict, future: FutureOrder) -> str:",
        ),
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS,
        "architecture-contract.json": contract_component_field_appended(
            "app", "public", "shop.app.reports:snapshot"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
    expected_declared_rules="FAIL",
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

_UNDECLARED_TYPE_IN_LIST_MODULE = HEADER + (
    '"""A stray function naming an undeclared type inside a list, for the boundary-types '
    'demo."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.model.entities import Money, Order\n\n\n"
    "class Extra:\n"
    '    """Defined here, and never declared in shop.app\'s public list."""\n\n'
    "    def __init__(self, detail: str) -> None:\n"
    "        self.detail = detail\n\n\n"
    "def summarize_all(orders: list[Order], extras: list[Extra]) -> Money:\n"
    '    """list[Order] holds shop.model\'s own declared facade; list[Extra] holds nobody\'s."""\n'
    "    for extra in extras:\n"
    "        print(extra.detail)\n"
    "    return orders[0].total()\n"
)

_BOUNDARY_TYPES_IN_COLLECTION = Variant(
    id="class-a-boundary-types-in-collection",
    section="class_a",
    item="boundary_types:collection_element",
    summary="A new shop.app.batches:summarize_all, declared in shop.app's own public list, "
    "takes list[Order] and returns Money -- both declared in shop.model's own facade, so "
    "APP-TYPES-NOT-DICT stays silent there -- and also takes list[Extra], whose element is a "
    "class declared by nobody. The same mistake used to disappear by being wrapped: a bare "
    "Extra was reported and a list[Extra] was silent, so moving a parameter into a list "
    "dropped the check. A known collection holding a bare name is now decided by the same "
    "resolution the rule runs on the name itself, one level in (AD-67).",
    files={
        "shop/app/batches.py": _UNDECLARED_TYPE_IN_LIST_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS.replace(
            "from shop.app.reports import snapshot", "from shop.app.batches import summarize_all"
        ),
        "architecture-contract.json": contract_component_field_appended(
            "app", "public", "shop.app.batches:summarize_all"
        ),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

_REEXPORTED_BROAD_MODULE = (
    (FIXTURE_DIR / "shop/render/text.py").read_text().replace("order: Order", "order: dict")
)


def _render_reexport_contract() -> str:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    render = next(item for item in contract["components"] if item["label"] == "render")
    render["public"] = [entry for entry in render["public"] if entry != "shop.render.text"]
    render["public"].append("shop.render:render_order")
    contract["rules"].append(
        {
            "id": "RENDER-TYPES-NOT-DICT",
            "kind": "boundary_types",
            "source": "shop.render",
            "rationale": "Keep the declared render boundary typed.",
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    return json.dumps(contract, indent=2) + "\n"


_BOUNDARY_TYPES_REEXPORT = Variant(
    id="class-a-boundary-types-reexport",
    section="class_a",
    item="boundary_types:reexport",
    summary="The shop.render package re-exports render_order from shop.render.text. The declared "
    "package facade owns the subject, while boundary_types reads the signature at its "
    "definition instead of guessing from the facade name (AD-84).",
    files={
        "shop/render/__init__.py": HEADER
        + (
            '"""Re-export the render component entry."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n\n"
            '__all__ = ["render_order"]\n'
        ),
        "shop/render/text.py": _REEXPORTED_BROAD_MODULE,
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from shop.render.text import render_order", "from shop.render import render_order"
        ),
        "architecture-contract.json": _render_reexport_contract(),
    },
    expected_violations=("RENDER-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


def _render_alias_contract() -> str:
    contract = json.loads(_render_reexport_contract())
    render = next(item for item in contract["components"] if item["label"] == "render")
    render["public"].append("shop.render:render_alias")
    return json.dumps(contract, indent=2) + "\n"


_BOUNDARY_TYPES_REEXPORT_ALIASES = Variant(
    id="class-a-boundary-types-reexport-aliases",
    section="class_a",
    item="boundary_types:reexport_aliases",
    summary="The shop.render facade exposes two aliases of the same render_order definition. "
    "They are one semantic origin and remain decidable; only distinct possible origins are "
    "UNKNOWN (AD-84).",
    files={
        "shop/render/__init__.py": HEADER
        + (
            '"""Re-export the render component entry under two facade aliases."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n"
            "from shop.render.text import render_order as render_alias\n\n"
            '__all__ = ["render_order", "render_alias"]\n'
        ),
        "shop/render/text.py": _REEXPORTED_BROAD_MODULE,
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from shop.render.text import render_order",
            "from shop.render import render_order, render_alias",
        ),
        "architecture-contract.json": _render_alias_contract(),
    },
    expected_violations=("RENDER-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


_BOUNDARY_TYPES_ORDINARY_REEXPORT = Variant(
    id="class-a-boundary-types-ordinary-reexport",
    section="class_a",
    item="boundary_types:ordinary_reexport",
    summary="An ordinary shop.render.facade module explicitly exports its imported entry in one "
    "literal __all__. boundary_types follows that declared facade to the implementation "
    "signature; imports without that proof remain UNKNOWN (AD-109).",
    files={
        "shop/render/facade.py": HEADER
        + (
            '"""Ordinary module facade for the renderer."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n\n"
            '__all__ = ["render_order"]\n'
        ),
        "shop/render/text.py": _REEXPORTED_BROAD_MODULE,
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from shop.render.text import render_order",
            "from shop.render.facade import render_order",
        ),
        "architecture-contract.json": _render_reexport_contract().replace(
            "shop.render:render_order", "shop.render.facade:render_order"
        ),
    },
    expected_violations=("RENDER-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


def _render_ordinary_chain_contract() -> str:
    contract = json.loads(_render_reexport_contract())
    render = next(item for item in contract["components"] if item["label"] == "render")
    render["public"] = [
        entry.replace("shop.render:render_order", "shop.render.facade:render_order")
        for entry in render["public"]
    ]
    render["public"].append("shop.render.facade:safe")
    return json.dumps(contract, indent=2) + "\n"


_BOUNDARY_TYPES_ORDINARY_REEXPORT_CHAIN_UNKNOWN = Variant(
    id="class-a-boundary-types-ordinary-reexport-chain-unknown",
    section="class_a",
    item="boundary_types:ordinary_reexport_chain",
    summary="The public ordinary facade exports render_order through an intermediate ordinary "
    "module with no literal __all__. That hop cannot prove the broad implementation signature, "
    "so the route stays UNKNOWN; the facade's local typed safe() remains decidable (AD-109).",
    files={
        "shop/render/facade.py": HEADER
        + (
            '"""Public ordinary facade for rendering."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.intermediate import render_order\n\n\n"
            "def safe(value: str) -> str:\n"
            "    return value\n\n"
            '__all__ = ["render_order", "safe"]\n'
        ),
        "shop/render/intermediate.py": HEADER
        + (
            '"""Intermediate ordinary import with no declared export list."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n"
        ),
        "shop/render/text.py": _REEXPORTED_BROAD_MODULE,
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from shop.render.text import render_order",
            "from shop.render.facade import render_order, safe",
        )
        .replace("print(render_order(order))", "print(safe(render_order(order)))"),
        "architecture-contract.json": _render_ordinary_chain_contract(),
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(
        ("boundary_type_route", "shop.render.facade.render_order"),
        ("boundary_type_route", "shop.render.facade"),
    ),
    expected_declared_rules="UNKNOWN",
)


def _owned_public_payload(value_type: str) -> dict[str, str]:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["label"] == "app")
    app["public"].extend(["shop.app.api:Payload", "shop.app.api:make"])
    value = "{}" if value_type == "dict" else '"ready"'
    return {
        "shop/app/payloads.py": HEADER
        + (
            '"""Payload owned and constructed by the app component."""\n\n'
            "from __future__ import annotations\n\n"
            "from dataclasses import dataclass\n\n\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class Payload:\n"
            f"    value: {value_type}\n\n\n"
            "def make() -> Payload:\n"
            f"    return Payload(value={value})\n"
        ),
        "shop/app/api.py": HEADER
        + (
            '"""The app component public API."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.app.payloads import Payload, make\n\n"
            '__all__ = ["Payload", "make"]\n'
        ),
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from shop.render.text import render_order",
            "from shop.render.text import render_order\nfrom shop.app.api import Payload, make",
        )
        .replace(
            "print(render_order(order))",
            "payload: Payload = make()\n        print(render_order(order), payload.value)",
        ),
        "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
    }


_BOUNDARY_TYPES_OWNED_PUBLIC_TYPE = Variant(
    id="class-a-boundary-types-owned-public-type",
    section="class_a",
    item="boundary_types:owned_public_type",
    summary="shop.app.api explicitly re-exports its own Payload and make from an ordinary module. "
    "The typed field is a proven same-owner public boundary with no violation. Aggregate rules "
    "remain UNKNOWN because store:STORE-REQUIRES-COMPLETE lacks a receipt for the unowned "
    "shop.store facade.",
    files=_owned_public_payload("str"),
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)

_BOUNDARY_TYPES_OWNED_PUBLIC_BROAD_FIELD = Variant(
    id="class-a-boundary-types-owned-public-broad-field",
    section="class_a",
    item="boundary_types:owned_public_broad_field",
    summary="The same proven app-owned public Payload has a broad dict field. The field remains "
    "a real APP-TYPES-NOT-DICT violation rather than being cleared with the re-export route.",
    files=_owned_public_payload("dict"),
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


def _datetime_payload(imports: str, annotation: str) -> dict[str, str]:
    files = _owned_public_payload(annotation)
    source = files["shop/app/payloads.py"]
    source = source.replace(
        "from dataclasses import dataclass", "from dataclasses import dataclass\n" + imports
    )
    source = source.replace("value:", "now:").replace("Payload(value=", "Payload(now=")
    if imports == "from datetime import datetime":
        source = source.replace('now="ready"', "now=datetime(2026, 1, 1)")
    files["shop/app/payloads.py"] = source
    files["shop/cli/main.py"] = files["shop/cli/main.py"].replace("payload.value", "payload.now")
    return files


_DATETIME_PAYLOAD = Variant(
    id="class-a-boundary-types-datetime",
    section="class_a",
    item="boundary_types:datetime_leaf",
    summary="An owned public DTO's proven datetime.datetime field is a scalar leaf (AD-132). "
    "Other report UNKNOWNs remain visible.",
    files=_datetime_payload("from datetime import datetime", "datetime"),
    expected_violations=(),
    expected_codes=(),
    expected_declared_rules="UNKNOWN",
)

_EXTERNAL_DATETIME_PAYLOAD = Variant(
    id="class-a-boundary-types-datetime-external",
    section="class_a",
    item="boundary_types:external_datetime_unknown",
    summary="Another class imported as datetime cannot use the stdlib leaf proof; "
    "return.now stays UNKNOWN.",
    files=_datetime_payload("from decimal import Decimal as datetime", "datetime"),
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("boundary_type_position", "shop.app.api.make"),),
    expected_declared_rules="UNKNOWN",
)

_OBJECT_PAYLOAD = Variant(
    id="class-a-boundary-types-object-field",
    section="class_a",
    item="boundary_types:broad_object_field",
    summary="An owned public DTO's object field remains a boundary violation at return.now.",
    files=_datetime_payload("", "object"),
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)

_REQUEST_MODEL_MODULE = HEADER + (
    '"""A request model with a broad directly declared field."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.model.entities import Order\n\n\n"
    "class Request:\n"
    "    metadata: dict\n\n\n"
    "def handle(request: Request) -> Order:\n"
    '    return Order(order_id="", lines=())\n'
)


def _request_model_contract() -> str:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["label"] == "app")
    app["public"].extend(["shop.app.requests:handle", "shop.app.requests:Request"])
    return json.dumps(contract, indent=2) + "\n"


_BOUNDARY_TYPES_MODEL_FIELD = Variant(
    id="class-a-boundary-types-model-field",
    section="class_a",
    item="boundary_types:model_field",
    summary="A declared request model carries a directly declared metadata: dict field. "
    "boundary_types reports the broad boundary type at the request's declared field path (AD-93).",
    files={
        "shop/app/requests.py": _REQUEST_MODEL_MODULE,
        "shop/cli/main.py": _CLI_IMPORTS_REPORTS.replace(
            "from shop.app.reports import snapshot", "from shop.app.requests import handle"
        ),
        "architecture-contract.json": _request_model_contract(),
    },
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


def _inherited_generic_service(return_type: str, *, declared: bool = True) -> dict[str, str]:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["label"] == "app")
    app["public"].append("shop.app.service:Child")
    if declared:
        app["public"].append("shop.app.payloads:Payload")
    return {
        "shop/app/payloads.py": HEADER + "class Payload: pass\nclass Noise: pass\n",
        "shop/app/base/__init__.py": HEADER
        + "from shop.app.base.impl import Base\n__all__ = ['Base']\n",
        "shop/app/base/impl.py": HEADER
        + (
            "from typing import Generic, TypeVar\n"
            "T = TypeVar('T')\n"
            "U = TypeVar('U')\n"
            "class Base(Generic[T, U]):\n"
            f"    def get(self) -> {return_type}: ...\n"
            "T = str\n"
        ),
        "shop/app/service.py": HEADER
        + (
            "from shop.app.base import Base\n"
            "from shop.app.payloads import Noise, Payload\n"
            "class Child(Base[Payload, Noise]):\n"
            "    pass\n"
        ),
        "shop/cli/main.py": (FIXTURE_DIR / "shop/cli/main.py")
        .read_text()
        .replace(
            "from pathlib import Path", "from pathlib import Path\nfrom typing import TYPE_CHECKING"
        )
        .replace(
            "from shop.render.text import render_order",
            "from shop.render.text import render_order\n\n"
            "if TYPE_CHECKING:\n"
            "    from shop.app.service import Child",
        ),
        "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
    }


_INHERITED_GENERIC_RETURN = Variant(
    id="class-a-inherited-generic-return",
    section="class_a",
    item="interface_boundary:inherited_generic_return",
    summary="Child inherits Base[Payload, Noise].get() -> list[T] from a re-exported base. "
    "The base's later TypeVar rebind and unused second parameter do not change the published "
    "Payload type.",
    files=_inherited_generic_service("list[T]"),
    expected_violations=(),
    expected_codes=(),
)

_INHERITED_GENERIC_UNDECLARED_RETURN = Variant(
    id="class-a-inherited-generic-undeclared-return",
    section="class_a",
    item="boundary_types:inherited_concrete_return",
    summary="Child.get() -> T resolves to the undeclared shop.app.payloads:Payload. "
    "The finding keeps T and shows that concrete origin (AD-137).",
    files=_inherited_generic_service("T", declared=False),
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


_INHERITED_GENERIC_UNDECLARED_BATCH = Variant(
    id="class-a-inherited-generic-undeclared-batch",
    section="class_a",
    item="boundary_types:inherited_concrete_collection",
    summary="Child.get() -> list[T] exposes the undeclared shop.app.payloads:Payload. "
    "The finding keeps list[T] and its stable identity (AD-137).",
    files=_inherited_generic_service("list[T]", declared=False),
    expected_violations=("APP-TYPES-NOT-DICT",),
    expected_codes=("rule.violated",),
)


_INHERITED_GENERIC_UNUSED = Variant(
    id="class-a-inherited-generic-unused",
    section="class_a",
    item="interface_boundary:irrelevant_generic_argument",
    summary="Child inherits Base[Payload, Noise].get() -> int. Neither generic argument reaches "
    "the public signature, so declaring Payload public is still unused.",
    files=_inherited_generic_service("int"),
    expected_violations=(),
    expected_codes=("interface.unused",),
)

_INHERITED_GENERIC_AMBIGUOUS = Variant(
    id="class-a-inherited-generic-ambiguous",
    section="class_a",
    item="interface_boundary:ambiguous_inherited_generic",
    summary="Two generic bases may expose Payload and Noise, so neither public entry is called "
    "unused or treated as proven facade publication.",
    files={
        **_inherited_generic_service("T"),
        "shop/app/base/impl.py": HEADER
        + (
            "from typing import Generic, TypeVar\n"
            "T = TypeVar('T')\n"
            "U = TypeVar('U')\n"
            "class First(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
            "class Second(Generic[U]):\n"
            "    def get(self) -> U: ...\n"
        ),
        "shop/app/service.py": HEADER
        + (
            "from shop.app.base.impl import First, Second\n"
            "from shop.app.payloads import Noise, Payload\n"
            "class Child(First[Payload], Second[Noise]):\n"
            "    pass\n"
        ),
    },
    expected_violations=(),
    expected_codes=("interface.usage_unknown",),
)


def _public_api_inherited_fields(
    *, declared: bool, unresolved: bool = False, aliased: bool = False
) -> dict[str, str]:
    contract = json.loads(
        contract_component_field_appended("model", "public", "shop.model.public_api:Child")
        if aliased
        else (FIXTURE_DIR / "architecture-contract.json").read_text()
    )
    contract["declarations"]["public_api"] = [
        f"shop.model.public_api:{'Alias' if aliased else 'Child'}"
    ]
    contract["declarations"]["public_api_provenance"] = ["docs/architecture/shop.md"]
    if declared:
        contract["declarations"]["public_api"].append("shop.model.public_api:Payload")
    files = {
        "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
        "shop/model/public_api.py": HEADER + "class Payload:\n    value: str\n"
        "class Base:\n    payload: Payload\n"
        f"class Child({'Missing' if unresolved else 'Base'}):"
        + ("\n    own: Payload\n" if aliased else " pass\n")
        + ("Alias = Child\n" if aliased else ""),
    }
    if aliased:
        files["shop/app/orders.py"] = (FIXTURE_DIR / "shop/app/orders.py").read_text().replace(
            "    from shop.store.sqlite import Connection",
            "    from shop.store.sqlite import Connection\n"
            "    from shop.model.public_api import Child",
        ) + "\n\ndef _read_payload(payload: Child) -> str:\n    return payload.own.value\n"
    return files


_PUBLIC_API_INHERITED_MISSING = Variant(
    id="public-api-inherited-missing",
    section="validation",
    item="public_api:inherited_field_missing",
    summary="Child inherits Base.payload: Payload, which its API declaration omits (AD-131, #243).",
    files=_public_api_inherited_fields(declared=False),
    expected_violations=(),
    expected_codes=("api_surface.missing",),
)

_PUBLIC_API_INHERITED_DECLARED = Variant(
    id="public-api-inherited-declared",
    section="clean",
    item="public_api:inherited_field_declared",
    summary="Declaring Child and the inherited Payload closes the public field exposure (AD-131).",
    files=_public_api_inherited_fields(declared=True),
    expected_violations=(),
    expected_codes=(),
)

_PUBLIC_API_INHERITED_UNKNOWN = Variant(
    id="public-api-inherited-unknown",
    section="validation",
    item="public_api:unresolved_inheritance",
    summary="An unresolved Child base retains API UNKNOWN with source evidence (AD-131).",
    files=_public_api_inherited_fields(declared=False, unresolved=True),
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("api_surface_limit", "shop.model.public_api:Child"),),
    expected_declared_rules="UNKNOWN",
)


_PUBLIC_API_ALIAS_MISSING = Variant(
    id="public-api-alias-missing",
    section="validation",
    item="public_api:class_alias_missing",
    summary="Alias = Child exposes its own and inherited Payload even when Child is a "
    "component facade (AD-131).",
    files=_public_api_inherited_fields(declared=False, aliased=True),
    expected_violations=(),
    expected_codes=("api_surface.missing",),
)

_PUBLIC_API_ALIAS_DECLARED = Variant(
    id="public-api-alias-declared",
    section="clean",
    item="public_api:class_alias_declared",
    summary="Declaring Alias and Payload closes its fields; component.public alone cannot "
    "do that (AD-131).",
    files=_public_api_inherited_fields(declared=True, aliased=True),
    expected_violations=(),
    expected_codes=(),
)

VARIANTS: tuple[Variant, ...] = (
    _SYMBOL_PLACEMENT,
    _BOUNDARY_TYPES,
    _MAPPING_BROAD,
    _MAPPING_ALLOWED,
    _OPAQUE_MAP_VALUES,
    _OPAQUE_MAP_VALUES_MISSING,
    _OPAQUE_MAP_VALUES_UNKNOWN,
    _CONTAINED_MAPPING,
    _CONTAINED_MAPPING_SIBLINGS,
    _CONTAINED_MAPPING_UNKNOWN,
    _BUILTIN_DICT_ALLOWED,
    _DIRECT_POSITION_ALLOWED,
    _DIRECT_POSITION_NEIGHBORS,
    _SHADOWED_DICT_ALLOWED,
    _NATIVE_PAYLOAD_ALLOWED,
    _NATIVE_PAYLOAD_NEIGHBORS,
    _BOUNDARY_TYPES_MIXED_EVIDENCE,
    _BOUNDARY_TYPES_DECLARED,
    _BOUNDARY_TYPES_IN_COLLECTION,
    _BOUNDARY_TYPES_REEXPORT,
    _BOUNDARY_TYPES_REEXPORT_ALIASES,
    _BOUNDARY_TYPES_ORDINARY_REEXPORT,
    _BOUNDARY_TYPES_ORDINARY_REEXPORT_CHAIN_UNKNOWN,
    _BOUNDARY_TYPES_OWNED_PUBLIC_TYPE,
    _BOUNDARY_TYPES_OWNED_PUBLIC_BROAD_FIELD,
    _DATETIME_PAYLOAD,
    _EXTERNAL_DATETIME_PAYLOAD,
    _OBJECT_PAYLOAD,
    _BOUNDARY_TYPES_MODEL_FIELD,
    _INHERITED_GENERIC_RETURN,
    _INHERITED_GENERIC_UNDECLARED_RETURN,
    _INHERITED_GENERIC_UNDECLARED_BATCH,
    _INHERITED_GENERIC_UNUSED,
    _INHERITED_GENERIC_AMBIGUOUS,
    _PUBLIC_API_INHERITED_MISSING,
    _PUBLIC_API_INHERITED_DECLARED,
    _PUBLIC_API_INHERITED_UNKNOWN,
    _PUBLIC_API_ALIAS_MISSING,
    _PUBLIC_API_ALIAS_DECLARED,
)
