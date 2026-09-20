# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 forbidden_dependency, allowed_dependency, external_dependency_scope,
complete_assignment, no_component_cycles and closed_world/decision rows.

`REPOSITORY_WITH_MONEY_IMPORT` and `SHOP_EXTRA` are public so `demo_catalog_showcase` can
reuse this family's file content instead of duplicating it.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import (
    CLEAN_SHOP_MD,
    HEADER,
    Variant,
    contract_rule_field,
    contract_rule_replaced,
    contract_with_requires,
    contract_with_rule,
    contract_without_rule,
    inside_requires_replaced,
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
    "existing render->model edge. DEP-MODEL-NO-RENDER is replaced by an allowed_dependency "
    "decision for the same pair and the marked graph gains the new edge, so only the cycle "
    "rule fires.",
    files={
        "shop/model/uses_render.py": HEADER
        + (
            '"""Cycle probe: model reaching into render, paired with a contract and graph '
            'edit."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.render.text import render_order\n\n"
            "describe_order = render_order\n"
        ),
        "architecture-contract.json": contract_rule_replaced(
            "DEP-MODEL-NO-RENDER",
            {
                "id": "DEP-MODEL-ALLOWS-RENDER",
                "kind": "allowed_dependency",
                "source": "shop.model",
                "target": "shop.render",
                "rationale": "Cycle probe: model temporarily allowed to reach render, for the "
                "architecture demo's no_component_cycles coverage.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            },
        ),
        # The permission is added too (AD-57), so both the observed and the target graph
        # gain the edge; `.replace` with no count hits both, since the two currently agree.
        "docs/architecture/shop.md": CLEAN_SHOP_MD.replace(
            "    render --> model\n", "    render --> model\n    model --> render\n"
        ),
    },
    expected_violations=("COMPONENT-NO-CYCLES",),
    expected_codes=("rule.violated",),
)
_DECISION_OPEN = Variant(
    id="class-a-decision-open",
    section="class_a",
    item="decision:open",
    summary="Removing DEP-CLI-NO-MODEL leaves shop.cli -> shop.model neither allowed nor "
    "forbidden: an open decision, unobserved at 0 import sites.",
    files={"architecture-contract.json": contract_without_rule("DEP-CLI-NO-MODEL")},
    expected_violations=(),
    expected_codes=("decision.open",),
)
_ALLOWED_DEPENDENCY_DUPLICATE = Variant(
    id="class-a-allowed-dependency-duplicate",
    section="class_a",
    item="allowed_dependency:duplicate",
    summary="A second allowed_dependency rule repeats the shop.store -> shop.model pair "
    "already covered by DEP-STORE-ALLOWS-MODEL.",
    files={
        "architecture-contract.json": contract_with_rule(
            {
                "id": "DEP-STORE-ALLOWS-MODEL-2",
                "kind": "allowed_dependency",
                "source": "shop.store",
                "target": "shop.model",
                "rationale": "A second, deliberately duplicate decision for the architecture "
                "demo's closed-world coverage.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    },
    expected_violations=(),
    expected_codes=("closed_world.duplicate",),
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
                "decided_by": "architect",
            }
        )
    },
    expected_violations=(),
    expected_codes=("closed_world.duplicate",),
)
_DECISION_CONFLICT = Variant(
    id="class-a-decision-conflict",
    section="class_a",
    item="decision:conflict",
    summary="A new forbidden_dependency rule targets shop.store -> shop.model, the same "
    "observed pair DEP-STORE-ALLOWS-MODEL already allows: three rule.violated findings, one "
    "per imported entity, an observed-yet-forbidden closed-world pair, and an allowed/forbidden "
    "decision.conflict.",
    files={
        "architecture-contract.json": contract_with_rule(
            {
                "id": "DEP-STORE-NO-MODEL-CONFLICT",
                "kind": "forbidden_dependency",
                "source": "shop.store",
                "target": "shop.model",
                "include_type_checking": True,
                "rationale": "A deliberately conflicting boundary for the architecture demo's "
                "decision-conflict coverage.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    },
    expected_violations=(
        "DEP-STORE-NO-MODEL-CONFLICT",
        "DEP-STORE-NO-MODEL-CONFLICT",
        "DEP-STORE-NO-MODEL-CONFLICT",
    ),
    expected_codes=(
        "closed_world.observed_forbidden",
        "decision.conflict",
        "rule.violated",
        "rule.violated",
        "rule.violated",
    ),
)

_SIBLING_ISOLATION = Variant(
    id="class-a-sibling-isolation",
    section="class_a",
    item="sibling_isolation:peer import",
    summary="shop.store.sqlite imports its peer shop.store.repository. Both are declared peers "
    "of one set, and peers reach shared modules, never each other (AD-25). The inside contract "
    "grants api that same edge, so the level below stays silent and this row shows one rule.",
    files={
        "shop/store/architecture-contract.json": inside_requires_replaced(
            "api",
            [
                {
                    "component": "repository",
                    "rationale": "A deliberately granted peer edge, so the architecture demo's "
                    "sibling_isolation row reports the outer rule alone.",
                }
            ],
        ),
        "architecture-contract.json": contract_with_rule(
            {
                "id": "STORE-PEERS-ISOLATED",
                "kind": "sibling_isolation",
                "members": ["shop.store.repository", "shop.store.sqlite"],
                "rationale": "Persistence and maintenance are peers behind the store's entry "
                "point, so neither reaches into the other.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        ),
        "shop/store/sqlite.py": HEADER
        + (
            '"""A maintenance-only view of the JSON store, kept out of ordinary order use '
            'cases."""\n\n'
            "from __future__ import annotations\n\n"
            "from dataclasses import dataclass\n"
            "from pathlib import Path\n\n"
            "from shop.store.repository import OrderRepository\n\n"
            "_OWNER = OrderRepository.__name__\n\n\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class Connection:\n"
            "    path: Path\n\n\n"
            "def vacuum(connection: Connection) -> None:\n"
            '    """Remove empty leftover order files from the store directory."""\n'
            '    for candidate in connection.path.glob("*.json"):\n'
            "        if candidate.stat().st_size == 0:\n"
            "            candidate.unlink()\n"
        ),
    },
    expected_violations=("STORE-PEERS-ISOLATED",),
    expected_codes=("rule.violated",),
)
_INSIDE_COMPLETE_REQUIRES = Variant(
    id="class-a-complete-requires-inside",
    section="class_a",
    item="complete_requires:inside",
    summary="store's inside contract drops repository's requires entry for backend, leaving the "
    "three imports of order_path, read_document and write_document uncovered. The rule fires "
    "inside the level and reports under store:STORE-REQUIRES-COMPLETE, the id the inside's own "
    "rule is recorded as (AD-36).",
    files={
        "shop/store/architecture-contract.json": inside_requires_replaced(
            "repository",
            [
                {
                    "component": "codec",
                    "rationale": "Turning an order into bytes and back is a format decision the "
                    "persistence API delegates, so the format can change without the API "
                    "changing.",
                }
            ],
        )
    },
    expected_violations=(
        "store:STORE-REQUIRES-COMPLETE",
        "store:STORE-REQUIRES-COMPLETE",
        "store:STORE-REQUIRES-COMPLETE",
    ),
    expected_codes=("rule.violated", "rule.violated", "rule.violated"),
)
_COMPLETE_EXTERNAL_SCOPE = Variant(
    id="class-a-complete-external-scope",
    section="class_a",
    item="complete_external_scope",
    summary="A new shop.app module imports shop_analytics, a package no rule declares and no "
    "index carries, which EXTERNAL-COMPLETE reports as an undecided dependency (AD-28).",
    files={
        "shop/app/analytics.py": HEADER
        + (
            '"""Reporting use case that reaches for an undeclared package."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop_analytics import track\n\n\n"
            "def report(total: int) -> str:\n"
            "    track(total)\n"
            '    return f"reported {total}"\n'
        )
    },
    expected_violations=("EXTERNAL-COMPLETE",),
    expected_codes=("rule.violated",),
)
_COMPLETE_REQUIRES = Variant(
    id="class-a-complete-requires",
    section="class_a",
    item="complete_requires",
    summary="Every component but render declares what it requires, so render's single import of "
    "shop.model is the one cross-component edge nobody asked for (AD-32).",
    files={
        "architecture-contract.json": contract_with_requires(
            {
                "store": [
                    {
                        "component": "model",
                        "rationale": "Persistence stores the domain's own entities.",
                    }
                ],
                "app": [
                    {
                        "component": "model",
                        "rationale": "Application services operate on domain entities directly.",
                    },
                    {
                        "component": "store",
                        "rationale": "Application services read and write through the repository.",
                    },
                ],
                "cli": [
                    {
                        "component": "app",
                        "rationale": "The composition root invokes application services.",
                    },
                    {
                        "component": "render",
                        "rationale": "The composition root hands typed results to the renderer.",
                    },
                ],
            },
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "A cross-component import the source never asked for is an accident.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            },
        )
    },
    expected_violations=("REQUIRES-COMPLETE",),
    expected_codes=("rule.violated",),
)
_COMPLETE_REQUIRES_TYPE_CHECKING = Variant(
    id="class-a-complete-requires-type-checking",
    section="class_a",
    item="complete_requires:include_type_checking",
    summary="app no longer requires store, so its four imports of that component are uncovered; "
    "include_type_checking false exempts the one sitting under TYPE_CHECKING, so three remain "
    "beside render's uncovered import of model.",
    files={
        "architecture-contract.json": contract_with_requires(
            {
                "store": [
                    {
                        "component": "model",
                        "rationale": "Persistence stores the domain's own entities.",
                    }
                ],
                "app": [
                    {
                        "component": "model",
                        "rationale": "Application services operate on domain entities directly.",
                    }
                ],
                "cli": [
                    {
                        "component": "app",
                        "rationale": "The composition root invokes application services.",
                    },
                    {
                        "component": "render",
                        "rationale": "The composition root hands typed results to the renderer.",
                    },
                ],
            },
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "include_type_checking": False,
                "rationale": "A type-only edge is a compile-time detail, not a runtime dependency.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            },
        )
    },
    expected_violations=("REQUIRES-COMPLETE",) * 4,
    expected_codes=("rule.violated",) * 4,
)
VARIANTS: tuple[Variant, ...] = (
    _COMPLETE_REQUIRES,
    _COMPLETE_REQUIRES_TYPE_CHECKING,
    _INSIDE_COMPLETE_REQUIRES,
    _COMPLETE_EXTERNAL_SCOPE,
    _FORBIDDEN_DEPENDENCY_PAIR,
    _FORBIDDEN_DEPENDENCY_TARGET_SYMBOL,
    _FORBIDDEN_DEPENDENCY_TYPE_CHECKING,
    _FORBIDDEN_DEPENDENCY_ALLOWED_SOURCES,
    _EXTERNAL_DEPENDENCY_SCOPE,
    _COMPLETE_ASSIGNMENT,
    _NO_COMPONENT_CYCLES,
    _DECISION_OPEN,
    _CLOSED_WORLD_DUPLICATE,
    _ALLOWED_DEPENDENCY_DUPLICATE,
    _DECISION_CONFLICT,
    _SIBLING_ISOLATION,
)
