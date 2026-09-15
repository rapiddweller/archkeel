# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 forbidden_dependency, external_dependency_scope, complete_assignment,
no_component_cycles and closed_world rows.

`REPOSITORY_WITH_MONEY_IMPORT` and `SHOP_EXTRA` are public so `demo_catalog_showcase` can
reuse this family's file content instead of duplicating it.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import (
    CLEAN_SHOP_MD,
    HEADER,
    Variant,
    contract_rule_field,
    contract_with_rule,
    contract_without_rule,
)

_FORBIDDEN_DEPENDENCY_PAIR = Variant(
    id="class-a-forbidden-dependency-pair",
    section="class_a",
    item="forbidden_dependency:pair",
    summary="shop.render imports shop.store's declared OrderRepository. The new edge is "
    "simultaneously a rule.violated (DEP-RENDER-NO-STORE), an observed-yet-forbidden "
    "closed-world pair, and a graph drift against the marked Mermaid graph.",
    files={
        "shop/render/text.py": HEADER
        + (
            '"""Text projection of an order."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.model.entities import Order\n"
            "from shop.store import OrderRepository\n\n"
            "_REPOSITORY_LABEL = OrderRepository.__name__\n\n\n"
            "def render_order(order: Order) -> str:\n"
            '    lines = [f"Order {order.order_id}"]\n'
            "    lines.extend(\n"
            '        _indent(f"{line.quantity} x {line.description}") for line in order.lines\n'
            "    )\n"
            '    lines.append(_indent(f"Total: {order.total()}"))\n'
            '    return "\\n".join(lines)\n\n\n'
            "def _indent(text: str) -> str:\n"
            '    return f"  {text}"\n'
        )
    },
    expected_violations=("DEP-RENDER-NO-STORE",),
    expected_codes=("closed_world.observed_forbidden", "graph.drift", "rule.violated"),
)
REPOSITORY_WITH_MONEY_IMPORT = HEADER + (
    '"""Persist orders as one JSON file per order id."""\n\n'
    "from __future__ import annotations\n\n"
    "import json\n"
    "from pathlib import Path\n\n"
    "from shop.model.entities import Money, Order\n\n\n"
    "class OrderRepository:\n"
    "    def __init__(self, root: Path) -> None:\n"
    "        self._root = root\n\n"
    "    def save(self, order: Order) -> None:\n"
    "        self._path(order.order_id).write_text(json.dumps(order.to_dict()))\n\n"
    "    def load(self, order_id: str) -> Order:\n"
    "        return Order.from_dict(json.loads(self._path(order_id).read_text()))\n\n"
    "    def total_due(self, order_id: str) -> Money:\n"
    '        """Demonstrates the forbidden Money import for the architecture demo."""\n'
    "        return self.load(order_id).total()\n\n"
    "    def _path(self, order_id: str) -> Path:\n"
    '        return self._root / f"{order_id}.json"\n'
)
_FORBIDDEN_DEPENDENCY_TARGET_SYMBOL = Variant(
    id="class-a-forbidden-dependency-target-symbol",
    section="class_a",
    item="forbidden_dependency:target_symbol",
    summary="shop.store additionally imports shop.model.entities.Money, firing the "
    "target_symbol-scoped DEP-STORE-NO-MONEY rule.",
    files={"shop/store/repository.py": REPOSITORY_WITH_MONEY_IMPORT},
    expected_violations=("DEP-STORE-NO-MONEY",),
    expected_codes=("rule.violated",),
)
_FORBIDDEN_DEPENDENCY_TYPE_CHECKING = Variant(
    id="class-a-forbidden-dependency-include-type-checking",
    section="class_a",
    item="forbidden_dependency:include_type_checking",
    summary="Flipping DEP-APP-NO-STORE-SQLITE's include_type_checking to true makes the "
    "existing TYPE_CHECKING import in shop.app.orders a violation.",
    files={
        "architecture-contract.json": contract_rule_field(
            "DEP-APP-NO-STORE-SQLITE", include_type_checking=True
        )
    },
    expected_violations=("DEP-APP-NO-STORE-SQLITE",),
    expected_codes=("rule.violated",),
)
_FORBIDDEN_DEPENDENCY_ALLOWED_SOURCES = Variant(
    id="class-a-forbidden-dependency-allowed-sources",
    section="class_a",
    item="forbidden_dependency:allowed_sources",
    summary="Removing DEP-APP-NO-STORE-SQLITE's allowed_sources exposes the maintenance use "
    "case's own runtime import of Connection and vacuum: two symbols, two violations.",
    files={
        "architecture-contract.json": contract_rule_field(
            "DEP-APP-NO-STORE-SQLITE", allowed_sources=[]
        )
    },
    expected_violations=("DEP-APP-NO-STORE-SQLITE", "DEP-APP-NO-STORE-SQLITE"),
    expected_codes=("rule.violated", "rule.violated"),
)
_EXTERNAL_DEPENDENCY_SCOPE = Variant(
    id="class-a-external-dependency-scope",
    section="class_a",
    item="external_dependency_scope",
    summary="shop.app imports json outside EXTERNAL-JSON-STORE's allowed shop.store scope.",
    files={
        "shop/app/reporting.py": HEADER
        + (
            '"""Order reporting helper; imports json only to demonstrate scope drift."""\n\n'
            "from __future__ import annotations\n\n"
            "import json\n\n"
            "from shop.model.entities import Order\n\n\n"
            "def as_json(order: Order) -> str:\n"
            "    return json.dumps(order.to_dict())\n"
        )
    },
    expected_violations=("EXTERNAL-JSON-STORE",),
    expected_codes=("rule.violated",),
)
SHOP_EXTRA = HEADER + (
    '"""An unowned module demonstrating a complete_assignment violation."""\n\n'
    "from __future__ import annotations\n\n"
    'NOTE = "This module belongs to no shop component package."\n'
)
_COMPLETE_ASSIGNMENT = Variant(
    id="class-a-complete-assignment",
    section="class_a",
    item="complete_assignment",
    summary="shop/extra.py has no owning component package.",
    files={"shop/extra.py": SHOP_EXTRA},
    expected_violations=("ASSIGNMENT-COMPLETE",),
    expected_codes=("rule.violated",),
)
_NO_COMPONENT_CYCLES = Variant(
    id="class-a-no-component-cycles",
    section="class_a",
    item="no_component_cycles",
    summary="shop.model imports shop.render, closing a two-component cycle with the "
    "existing render->model edge. DEP-MODEL-NO-RENDER is removed and the marked graph "
    "gains the new edge, so only the cycle rule fires.",
    files={
        "shop/model/uses_render.py": HEADER
        + (
            '"""Cycle probe: model reaching into render, paired with a contract and graph '
            'edit."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n\n"
            "describe_order = render_order\n"
        ),
        "architecture-contract.json": contract_without_rule("DEP-MODEL-NO-RENDER"),
        "docs/architecture/shop.md": CLEAN_SHOP_MD.replace(
            "    render --> model\n", "    render --> model\n    model --> render\n", 1
        ),
    },
    expected_violations=("COMPONENT-NO-CYCLES",),
    expected_codes=("rule.violated",),
)
_CLOSED_WORLD_MISSING = Variant(
    id="class-a-closed-world-missing",
    section="class_a",
    item="closed_world:missing",
    summary="Removing DEP-CLI-NO-MODEL leaves shop.cli -> shop.model neither observed nor "
    "forbidden.",
    files={"architecture-contract.json": contract_without_rule("DEP-CLI-NO-MODEL")},
    expected_violations=(),
    expected_codes=("closed_world.missing",),
)
_CLOSED_WORLD_DUPLICATE = Variant(
    id="class-a-closed-world-duplicate",
    section="class_a",
    item="closed_world:duplicate",
    summary="A second forbidden_dependency rule repeats the shop.cli -> shop.model pair "
    "already covered by DEP-CLI-NO-MODEL.",
    files={
        "architecture-contract.json": contract_with_rule(
            {
                "id": "DEP-CLI-NO-MODEL-2",
                "kind": "forbidden_dependency",
                "source": "shop.cli",
                "target": "shop.model",
                "include_type_checking": True,
                "rationale": "A second, deliberately duplicate boundary for the architecture "
                "demo's closed-world coverage.",
                "provenance": ["docs/architecture/shop.md"],
            }
        )
    },
    expected_violations=(),
    expected_codes=("closed_world.duplicate",),
)

VARIANTS: tuple[Variant, ...] = (
    _FORBIDDEN_DEPENDENCY_PAIR,
    _FORBIDDEN_DEPENDENCY_TARGET_SYMBOL,
    _FORBIDDEN_DEPENDENCY_TYPE_CHECKING,
    _FORBIDDEN_DEPENDENCY_ALLOWED_SOURCES,
    _EXTERNAL_DEPENDENCY_SCOPE,
    _COMPLETE_ASSIGNMENT,
    _NO_COMPONENT_CYCLES,
    _CLOSED_WORLD_MISSING,
    _CLOSED_WORLD_DUPLICATE,
)
