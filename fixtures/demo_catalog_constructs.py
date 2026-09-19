# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 forbidden_construct rows: one probe module per ForbiddenConstructKind value."""

from __future__ import annotations

from archkeel.ir.model import ForbiddenConstructKind
from fixtures.demo_catalog_support import HEADER, Variant, contract_rule_field

_CONSTRUCT_SOURCE: dict[ForbiddenConstructKind, str] = {
    ForbiddenConstructKind.GETATTR: HEADER
    + (
        '"""Getattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def read_value() -> object:\n"
        '    return getattr(_Box(), "value")\n'
    ),
    ForbiddenConstructKind.HASATTR: HEADER
    + (
        '"""Hasattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def has_value() -> bool:\n"
        '    return hasattr(_Box(), "value")\n'
    ),
    ForbiddenConstructKind.CAST: HEADER
    + (
        '"""Cast probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import cast\n\n\n"
        "def as_int(value: object) -> int:\n"
        "    return cast(int, value)\n"
    ),
    ForbiddenConstructKind.EVAL: HEADER
    + (
        '"""Eval probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def compute() -> int:\n"
        '    return eval("1 + 1")\n'
    ),
    ForbiddenConstructKind.EXEC: HEADER
    + (
        '"""Exec probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def run() -> None:\n"
        '    exec("pass")\n'
    ),
    ForbiddenConstructKind.DYNAMIC_IMPORT: HEADER
    + (
        '"""Dynamic import probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "import importlib\n\n\n"
        "def load_json_module() -> object:\n"
        '    return importlib.import_module("json")\n'
    ),
    ForbiddenConstructKind.TYPE_IGNORE: HEADER
    + (
        '"""Type-ignore probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def broken() -> None:\n"
        '    value: int = "oops"  # type: ignore\n'
        "    del value\n"
    ),
    ForbiddenConstructKind.ANY_ANNOTATION: HEADER
    + (
        '"""Any-annotation probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "def widen(value: Any) -> str:\n"
        "    return str(value)\n"
    ),
    ForbiddenConstructKind.PLACEHOLDER_BODY: HEADER
    + (
        '"""Placeholder-body probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def apply_discount(amount: int) -> int:\n"
        "    pass\n"
    ),
    ForbiddenConstructKind.ASSERT: HEADER
    + (
        '"""Assert probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def check(value: int) -> int:\n"
        "    assert value > 0\n"
        "    return value\n"
    ),
    ForbiddenConstructKind.BROAD_EXCEPT: HEADER
    + (
        '"""Broad-except probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def guard() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return 0\n"
    ),
    ForbiddenConstructKind.SETATTR: HEADER
    + (
        '"""Setattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def write_value() -> None:\n"
        '    setattr(_Box(), "value", 2)\n'
    ),
    ForbiddenConstructKind.DELATTR: HEADER
    + (
        '"""Delattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def drop_value() -> None:\n"
        '    delattr(_Box, "value")\n'
    ),
    ForbiddenConstructKind.VARS: HEADER
    + (
        '"""Vars probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def fields() -> dict[str, object]:\n"
        "    return vars(_Box())\n"
    ),
    ForbiddenConstructKind.DUNDER_DICT: HEADER
    + (
        '"""Dunder-dict probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def fields() -> dict[str, object]:\n"
        "    return _Box().__dict__\n"
    ),
    ForbiddenConstructKind.STRING_LITERAL_COMPARE: HEADER
    + (
        '"""String-literal-compare probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def shipping_cents(method: str) -> int:\n"
        '    if method == "express":\n'
        "        return 900\n"
        "    return 300\n"
    ),
}
_CONSTRUCT_RULE: dict[ForbiddenConstructKind, str] = {
    kind: (
        "CONSTRUCT-NO-ASSERT"
        if kind is ForbiddenConstructKind.ASSERT
        else "CONSTRUCT-NO-BROAD-EXCEPT"
        if kind is ForbiddenConstructKind.BROAD_EXCEPT
        else "CONSTRUCT-NO-ANY"
        if kind is ForbiddenConstructKind.ANY_ANNOTATION
        else "CONSTRUCT-NO-PLACEHOLDER"
        if kind is ForbiddenConstructKind.PLACEHOLDER_BODY
        else "CONSTRUCT-NO-STRING-LITERAL-COMPARE"
        if kind is ForbiddenConstructKind.STRING_LITERAL_COMPARE
        else "CONSTRUCT-NO-DYNAMIC"
    )
    for kind in ForbiddenConstructKind
}
_CONSTRUCT_VARIANTS = tuple(
    Variant(
        id=f"class-a-construct-{kind.value}",
        section="class_a",
        item=f"forbidden_construct:{kind.value}",
        summary=f"A new shop.model probe module uses {kind.value}, firing {_CONSTRUCT_RULE[kind]}.",
        files={f"shop/model/probe_{kind.value}.py": _CONSTRUCT_SOURCE[kind]},
        expected_violations=(_CONSTRUCT_RULE[kind],),
        expected_codes=("rule.violated",),
    )
    for kind in ForbiddenConstructKind
)
# One scope below the boundary: `parse_quantity`'s owner is shop.cli.main.main.parse_quantity.
_MAIN_WITH_NESTED_HANDLER = HEADER + (
    '"""Argument parsing and composition; the single broad error boundary lives here."""\n\n'
    "from __future__ import annotations\n\n"
    "from pathlib import Path\n\n"
    "from shop.app.orders import place_order\n"
    "from shop.render.text import render_order\n\n\n"
    "def main(argv: list[str]) -> int:\n"
    "    def parse_quantity(text: str) -> int:\n"
    "        try:\n"
    "            return int(text)\n"
    "        except Exception:\n"
    "            return 1\n\n"
    "    try:\n"
    "        order_id, description, quantity, unit_price_cents, store_dir = argv\n"
    "        order = place_order(\n"
    "            Path(store_dir), order_id, description, parse_quantity(quantity), "
    "int(unit_price_cents)\n"
    "        )\n"
    "        print(render_order(order))\n"
    "        return 0\n"
    "    except Exception:\n"
    "        return 1\n"
)
_BROAD_EXCEPT_EXACT = Variant(
    id="class-a-broad-except-exact",
    section="class_a",
    item="forbidden_construct:exact_sources",
    summary="The clean contract names shop.cli.main.main in CONSTRUCT-NO-BROAD-EXCEPT's "
    "exact_sources. A helper nested inside main catches every exception too: its handler is "
    "reported, main's own is not (AD-49).",
    files={"shop/cli/main.py": _MAIN_WITH_NESTED_HANDLER},
    expected_violations=("CONSTRUCT-NO-BROAD-EXCEPT",),
    expected_codes=("rule.violated",),
)
_BROAD_EXCEPT_PREFIX = Variant(
    id="class-a-broad-except-prefix",
    section="class_a",
    item="forbidden_construct:allowed_sources",
    summary="The same code with shop.cli.main.main moved to allowed_sources: as a prefix the "
    "name also exempts the nested helper, so nothing is reported. Only the list differs from "
    "class-a-broad-except-exact.",
    files={
        "shop/cli/main.py": _MAIN_WITH_NESTED_HANDLER,
        "architecture-contract.json": contract_rule_field(
            "CONSTRUCT-NO-BROAD-EXCEPT", allowed_sources=["shop.cli.main.main"], exact_sources=[]
        ),
    },
    expected_violations=(),
    expected_codes=(),
)

VARIANTS: tuple[Variant, ...] = (*_CONSTRUCT_VARIANTS, _BROAD_EXCEPT_EXACT, _BROAD_EXCEPT_PREFIX)
