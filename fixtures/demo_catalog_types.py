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
            '    return Payload(value="ready")\n'
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
    "The typed field is a proven same-owner public boundary and stays clean.",
    files=_owned_public_payload("str"),
    expected_violations=(),
    expected_codes=(),
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

VARIANTS: tuple[Variant, ...] = (
    _SYMBOL_PLACEMENT,
    _BOUNDARY_TYPES,
    _BOUNDARY_TYPES_DECLARED,
    _BOUNDARY_TYPES_IN_COLLECTION,
    _BOUNDARY_TYPES_REEXPORT,
    _BOUNDARY_TYPES_REEXPORT_ALIASES,
    _BOUNDARY_TYPES_ORDINARY_REEXPORT,
    _BOUNDARY_TYPES_ORDINARY_REEXPORT_CHAIN_UNKNOWN,
    _BOUNDARY_TYPES_OWNED_PUBLIC_TYPE,
    _BOUNDARY_TYPES_OWNED_PUBLIC_BROAD_FIELD,
    _BOUNDARY_TYPES_MODEL_FIELD,
)
