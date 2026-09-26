# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 interface_boundary rows.

`MAIN_WITH_UNDERSCORE_IMPORT` is public so `demo_catalog_showcase` can reuse this family's
file content instead of duplicating it.
"""

from __future__ import annotations

import json

from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    Variant,
    contract_rule_field,
)

MAIN_WITH_UNDERSCORE_IMPORT = HEADER + (
    '"""Argument parsing and composition; the single broad error boundary lives here."""\n\n'
    "from __future__ import annotations\n\n"
    "from pathlib import Path\n\n"
    "from shop.app.orders import place_order\n"
    "from shop.render.text import _indent, render_order\n\n\n"
    "def main(argv: list[str]) -> int:\n"
    "    try:\n"
    "        order_id, description, quantity, unit_price_cents, store_dir = argv\n"
    "        order = place_order(\n"
    "            Path(store_dir), order_id, description, int(quantity), int(unit_price_cents)\n"
    "        )\n"
    "        print(_indent(render_order(order)))\n"
    "        return 0\n"
    "    except Exception:\n"
    "        return 1\n"
)


def _barrel_contract() -> str:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    store = next(item for item in contract["components"] if item["label"] == "store")
    store["public"] = [
        "shop.store.repository:OrderRepository",
        "shop.store:OrderRepository",
        "shop.store.sqlite:vacuum",
        "shop.store.sqlite:Connection",
    ]
    return json.dumps(contract, indent=2) + "\n"


def _barrel_inside_contract() -> str:
    contract = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    repository = next(item for item in contract["components"] if item["label"] == "repository")
    repository["public"] = ["shop.store.repository:OrderRepository"]
    return json.dumps(contract, indent=2) + "\n"


_INTERFACE_UNDERSCORE = Variant(
    id="class-a-interface-boundary-underscore",
    section="class_a",
    item="interface_boundary:underscore",
    summary="shop.cli imports shop.render.text's private _indent; underscore names never "
    "qualify as public.",
    files={"shop/cli/main.py": MAIN_WITH_UNDERSCORE_IMPORT},
    expected_violations=("INTERFACE-BOUNDARY",),
    expected_codes=("rule.violated",),
)
_INTERFACE_UNDECLARED_SYMBOL = Variant(
    id="class-a-interface-boundary-undeclared-symbol",
    section="class_a",
    item="interface_boundary:undeclared symbol",
    summary="shop.cli additionally imports shop.app.orders.summarize, a real, non-underscore "
    "symbol that COMP-APP never declares public.",
    files={
        "shop/cli/main.py": HEADER
        + (
            '"""Argument parsing and composition; the single broad error boundary lives here."""'
            "\n\n"
            "from __future__ import annotations\n\n"
            "from pathlib import Path\n\n"
            "from shop.app.orders import place_order, summarize\n"
            "from shop.render.text import render_order\n\n\n"
            "def main(argv: list[str]) -> int:\n"
            "    try:\n"
            "        order_id, description, quantity, unit_price_cents, store_dir = argv\n"
            "        order = place_order(\n"
            "            Path(store_dir), order_id, description, int(quantity), "
            "int(unit_price_cents)\n"
            "        )\n"
            "        summarize(Path(store_dir), order_id)\n"
            "        print(render_order(order))\n"
            "        return 0\n"
            "    except Exception:\n"
            "        return 1\n"
        )
    },
    expected_violations=("INTERFACE-BOUNDARY",),
    expected_codes=("rule.violated",),
)
_INTERFACE_WHOLE_MODULE = Variant(
    id="class-a-interface-boundary-whole-module",
    section="class_a",
    item="interface_boundary:whole-module import",
    summary="shop.app imports the shop.store.repository module directly; COMP-STORE "
    "declares only symbol entries, so the bare module import matches none of them.",
    files={
        "shop/app/maintenance_report.py": HEADER
        + (
            '"""Whole-module import probe: shop.store only declares symbol entries."""\n\n'
            "from __future__ import annotations\n\n"
            "import shop.store.repository\n\n\n"
            "def repository_module_name() -> str:\n"
            "    return shop.store.repository.__name__\n"
        )
    },
    expected_violations=("INTERFACE-BOUNDARY",),
    expected_codes=("rule.violated",),
)
_INTERFACE_ALL_GATE = Variant(
    id="class-a-interface-boundary-all-gate",
    section="class_a",
    item="interface_boundary:__all__ gate",
    summary="shop.render imports shop.model.entities.Discount, which entities.py's __all__ "
    "excludes even though it is a non-underscore name.",
    files={
        "shop/render/discount_probe.py": HEADER
        + (
            '"""Discount probe: demonstrates the __all__ interface gate."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.model.entities import Discount\n\n\n"
            "def percent_label(discount: Discount) -> str:\n"
            '    return f"{discount.percent}%"\n'
        )
    },
    expected_violations=("INTERFACE-BOUNDARY",),
    expected_codes=("rule.violated",),
)
_INTERFACE_ACCEPTED_REEXPORT = Variant(
    id="class-a-interface-boundary-accepted-reexport",
    section="class_a",
    item="interface_boundary:accepted re-export",
    summary="shop.app imports OrderRepository through shop.store's declared re-export chain; "
    "the reach is accepted and produces no findings.",
    files={
        "shop/app/accepted_reexport.py": HEADER
        + (
            '"""Accepted re-export probe using shop.store\'s declared OrderRepository."""\n\n'
            "from __future__ import annotations\n\n"
            "from shop.store import OrderRepository\n\n\n"
            "def repository_type_name() -> str:\n"
            "    return OrderRepository.__name__\n"
        )
    },
    expected_violations=(),
    expected_codes=(),
)
_INTERFACE_PROFILE_BARREL = Variant(
    id="class-d-interface-profile-barrel",
    section="class_d",
    item="interface_profile:declared barrel",
    summary="The real shop.store barrel is declared as the public facade; the observation can "
    "measure its export shape and consumers without claiming completeness or enforcing a budget.",
    files={
        "architecture-contract.json": _barrel_contract(),
        "shop/store/__init__.py": (FIXTURE_DIR / "shop/store/__init__.py").read_text(),
        "shop/store/architecture-contract.json": _barrel_inside_contract(),
    },
    expected_violations=(),
    expected_codes=(),
)
_STORE_INIT_WITH_SHADOWED_SQLITE = HEADER + (
    '"""Re-export the store component\'s repository entry point."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.store.repository import OrderRepository\n\n"
    "# AD-53: this attribute wins over the shop.store.sqlite submodule for\n"
    '# "from shop.store import sqlite" -- unrelated to that module\'s Connection and vacuum.\n'
    'sqlite = "shop.db"\n\n'
    '__all__ = ["OrderRepository"]\n'
)
_INTERFACE_PACKAGE_ATTRIBUTE_OVER_SUBMODULE = Variant(
    id="class-a-interface-boundary-package-attribute-over-submodule",
    section="class_a",
    item="interface_boundary:package attribute over submodule",
    summary="shop.store's __init__ binds sqlite to a plain constant, shadowing its own "
    "shop.store.sqlite submodule (AD-53); shop.app's `from shop.store import sqlite` now "
    "resolves to the package attribute shop.store:sqlite, which store never declared public, "
    "so interface_boundary reports it. Before AD-53 the scan alone resolved the same import to "
    "the whole shop.store.sqlite submodule, which DEP-APP-NO-STORE-SQLITE forbids outright, so "
    "the crossing was misreported as that forbidden_dependency (AD-18 supersedes interface_"
    "boundary on the same import) though the code never touches that module.",
    files={
        "shop/store/__init__.py": _STORE_INIT_WITH_SHADOWED_SQLITE,
        "shop/app/sqlite_probe.py": HEADER
        + (
            '"""Package-attribute probe: shop.store binds sqlite ahead of its own submodule."""'
            "\n\n"
            "from __future__ import annotations\n\n"
            "from shop.store import sqlite\n\n\n"
            "def default_database_name() -> str:\n"
            "    return sqlite\n"
        ),
    },
    expected_violations=("INTERFACE-BOUNDARY",),
    expected_codes=("rule.violated",),
)
UNTYPED_PRIVATE_ACCESS = HEADER + (
    '"""A boundary probe with no type evidence for the runtime owner."""\n\n'
    "from __future__ import annotations\n\n"
    "def bump(context):\n"
    "    return context.root._registry\n"
)
_INTERFACE_UNTYPED_PRIVATE_ACCESS = Variant(
    id="class-a-private-attribute-untyped",
    section="class_a",
    item="private_access:untyped parameter",
    summary="An untyped parameter reaches a private attribute; the analyzer records UNKNOWN "
    "with the function, parameter and attribute instead of claiming component ownership.",
    files={"shop/app/untyped_private.py": UNTYPED_PRIVATE_ACCESS},
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("private_attribute_access_limit", "shop.app.untyped_private.bump"),),
)

ANY_PRIVATE_ACCESS = HEADER + (
    '"""A boundary probe distinguishing top-level and nested Any annotations."""\n\n'
    "from __future__ import annotations\n\n"
    "from typing import Any, Optional\n"
    "from typing import Any as Alias\n"
    "import typing\n\n"
    "def bare(context: Any):\n    return context._bare\n\n"
    "def qualified(context: typing.Any):\n    return context._qualified\n\n"
    "def aliased(context: Alias):\n    return context._aliased\n\n"
    "def list_any(context: list[Any]):\n    return context._list\n\n"
    "def dict_any(context: dict[str, Any]):\n    return context._dict\n\n"
    "def optional_list_any(context: Optional[list[Any]]):\n    return context._optional\n"
)
_INTERFACE_ANY_PRIVATE_ACCESS = Variant(
    id="class-a-private-attribute-any-owner",
    section="class_a",
    item="private_access:top-level Any owner",
    summary="Only an untyped, unresolved, or top-level Any owner makes private ownership UNKNOWN; "
    "nested Any keeps the deterministic outer annotation owner.",
    files={
        "architecture-contract.json": contract_rule_field(
            "CONSTRUCT-NO-ANY", allowed_sources=["shop.app.any_private"]
        ),
        "shop/app/any_private.py": ANY_PRIVATE_ACCESS,
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(
        ("private_attribute_access_limit", "shop.app.any_private.bare"),
        ("private_attribute_access_limit", "shop.app.any_private.qualified"),
        ("private_attribute_access_limit", "shop.app.any_private.aliased"),
    ),
)

VARIANTS: tuple[Variant, ...] = (
    _INTERFACE_UNDERSCORE,
    _INTERFACE_UNDECLARED_SYMBOL,
    _INTERFACE_WHOLE_MODULE,
    _INTERFACE_ALL_GATE,
    _INTERFACE_ACCEPTED_REEXPORT,
    _INTERFACE_PROFILE_BARREL,
    _INTERFACE_PACKAGE_ATTRIBUTE_OVER_SUBMODULE,
    _INTERFACE_UNTYPED_PRIVATE_ACCESS,
    _INTERFACE_ANY_PRIVATE_ACCESS,
)
