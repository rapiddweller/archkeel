# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 examples for catalog-bound arguments and required catalog reads."""

from __future__ import annotations

from fixtures.demo_catalog_support import FIXTURE_DIR, Variant

_APP_ORDERS = (FIXTURE_DIR / "shop/app/orders.py").read_text()

_CATALOG_ARGUMENT = Variant(
    id="class-a-catalog-argument",
    section="class_a",
    item="catalog_argument:unlisted_literal",
    summary="An application read passes an undeclared option literal to the selected store reader.",
    files={
        "shop/app/orders.py": _APP_ORDERS.replace(
            "def read_catalog_option() -> str:\n    return read_option(OptionKey.PAGE_SIZE)",
            'def read_catalog_option() -> str:\n    return read_option("unlisted-option")',
        )
    },
    expected_violations=("APP-OPTION-KEY",),
    expected_codes=("rule.violated",),
)

_CATALOG_USE = Variant(
    id="class-a-catalog-use",
    section="class_a",
    item="catalog_use:unused_page_size",
    summary="The application stops reading the declared PAGE_SIZE catalog member.",
    files={
        "shop/app/orders.py": _APP_ORDERS.replace(
            "read_option(OptionKey.PAGE_SIZE)", "read_option(OptionKey.RETIRED)"
        )
    },
    expected_violations=("APP-OPTION-KEY-USED",),
    expected_codes=("rule.violated",),
)

VARIANTS: tuple[Variant, ...] = (_CATALOG_ARGUMENT, _CATALOG_USE)
