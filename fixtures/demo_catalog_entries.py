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
            "def read_catalog_option() -> str:\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
            '    return read_option("unlisted-option")',
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
            "read_option(OptionKey.PAGE_SIZE)",
            "read_option(OptionKey.RETIRED)",
        )
    },
    expected_violations=("APP-OPTION-KEY-USED",),
    expected_codes=("rule.violated",),
)

_APP_MAINTENANCE = (FIXTURE_DIR / "shop/app/maintenance.py").read_text()
_READ_OPTION_CALL = "read_option(OptionKey.PAGE_SIZE)"
_READ_OPTION_KEYWORD = "read_option(key=OptionKey.PAGE_SIZE)"

_CATALOG_ARGUMENT_KEYWORD = Variant(
    id="class-a-catalog-argument-keyword",
    section="class_a",
    item="catalog_argument:keyword_member",
    summary="The application passes the declared member to the selected store reader by keyword.",
    files={"shop/app/orders.py": _APP_ORDERS.replace(_READ_OPTION_CALL, _READ_OPTION_KEYWORD)},
    expected_violations=(),
    expected_codes=(),
    absent_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

_CATALOG_ARGUMENT_KEYWORD_UNLISTED = Variant(
    id="class-a-catalog-argument-keyword-unlisted",
    section="class_a",
    item="catalog_argument:keyword_unlisted_literal",
    summary="The application passes an undeclared option literal to the store reader by keyword.",
    files={
        "shop/app/orders.py": _APP_ORDERS.replace(
            "def read_catalog_option() -> str:\n    return " + _READ_OPTION_CALL,
            "def read_catalog_option() -> str:\n"
            f"    {_READ_OPTION_KEYWORD}\n"
            '    return read_option(key="unlisted-option")',
        )
    },
    expected_violations=("APP-OPTION-KEY",),
    expected_codes=("rule.violated",),
)

_CATALOG_ARGUMENT_ESCAPE_INSIDE = Variant(
    id="class-a-catalog-argument-escape-inside",
    section="class_a",
    item="catalog_argument:member_escape_in_source",
    summary="The selected read also passes the declared member to print, an unselected call.",
    files={
        "shop/app/orders.py": _APP_ORDERS.replace(
            "def read_catalog_option() -> str:\n    return " + _READ_OPTION_CALL,
            "def read_catalog_option() -> str:\n"
            "    print(OptionKey.PAGE_SIZE)\n"
            "    return " + _READ_OPTION_CALL,
        )
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

_CATALOG_ARGUMENT_ESCAPE_OUTSIDE = Variant(
    id="class-a-catalog-argument-escape-outside",
    section="class_a",
    item="catalog_argument:member_escape_outside_source",
    summary="Another application module passes the declared member to print, outside the source.",
    files={
        "shop/app/maintenance.py": _APP_MAINTENANCE.replace(
            "from shop.store.sqlite import",
            "from shop.app.catalog import OptionKey\nfrom shop.store.sqlite import",
        )
        + "\n\ndef show_option() -> None:\n    print(OptionKey.PAGE_SIZE)\n"
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

VARIANTS: tuple[Variant, ...] = (
    _CATALOG_ARGUMENT,
    _CATALOG_USE,
    _CATALOG_ARGUMENT_KEYWORD,
    _CATALOG_ARGUMENT_KEYWORD_UNLISTED,
    _CATALOG_ARGUMENT_ESCAPE_INSIDE,
    _CATALOG_ARGUMENT_ESCAPE_OUTSIDE,
)
