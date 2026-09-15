# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 interface_boundary rows.

`MAIN_WITH_UNDERSCORE_IMPORT` is public so `demo_catalog_showcase` can reuse this family's
file content instead of duplicating it.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant

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

VARIANTS: tuple[Variant, ...] = (
    _INTERFACE_UNDERSCORE,
    _INTERFACE_UNDECLARED_SYMBOL,
    _INTERFACE_WHOLE_MODULE,
    _INTERFACE_ALL_GATE,
    _INTERFACE_ACCEPTED_REEXPORT,
)
