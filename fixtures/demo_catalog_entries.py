# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 examples for catalog-bound arguments and required catalog reads."""

from __future__ import annotations

from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, contract_with_rule

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

_CATALOG_ARGUMENT_UNICODE_ALIAS = Variant(
    id="class-a-catalog-argument-unicode-alias",
    section="class_a",
    item="catalog_argument:non_ascii_alias",
    summary="The application reaches the declared member through a non-ASCII import alias.",
    files={
        "shop/app/orders.py": _APP_ORDERS.replace(
            "from shop.app.catalog import OptionKey, read_option",
            "from shop.app.catalog import OptionKey as Clé, read_option",
        ).replace(_READ_OPTION_CALL, "read_option(Clé.PAGE_SIZE)")
    },
    expected_violations=(),
    expected_codes=(),
    absent_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

_CATALOG_ARGUMENT_VALUE_LOOKUP = Variant(
    id="class-a-catalog-argument-value-lookup",
    section="class_a",
    item="catalog_argument:member_from_value_lookup",
    summary="Another application module gets the member by value and returns it to any caller.",
    files={
        "shop/app/maintenance.py": _APP_MAINTENANCE.replace(
            "from shop.store.sqlite import",
            "from shop.app.catalog import OptionKey\nfrom shop.store.sqlite import",
        )
        + "\n\ndef parse_option(raw: str) -> OptionKey:\n    return OptionKey(raw)\n"
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

_CATALOG_USE_MEMBER_VALUE = Variant(
    id="class-a-catalog-use-member-value",
    section="class_a",
    item="catalog_use:member_value_read",
    summary="The application returns the value of the RETIRED member; `.value` reads the member.",
    files={
        "shop/app/orders.py": _APP_ORDERS
        + "\n\ndef retired_option_value() -> str:\n    return OptionKey.RETIRED.value\n",
        "architecture-contract.json": contract_with_rule(
            {
                "id": "APP-RETIRED-OPTION-USED",
                "kind": "catalog_use",
                "source": "shop.app.orders.retired_option_value",
                "catalog": "shop.app.catalog.OptionKey",
                "member": "RETIRED",
                "rationale": "The retired option stays readable for old orders.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
                "source_match": "exact",
            }
        ),
    },
    expected_violations=(),
    expected_codes=(),
    absent_unknowns=(("catalog_limit", "shop.app.orders.retired_option_value"),),
)

_MAINTENANCE_WITH_OPTION_KEY = _APP_MAINTENANCE.replace(
    "from shop.store.sqlite import",
    "from shop.app.catalog import OptionKey\nfrom shop.store.sqlite import",
)

_CATALOG_ARGUMENT_STAR_REEXPORT = Variant(
    id="class-a-catalog-argument-star-reexport",
    section="class_a",
    item="catalog_argument:member_from_star_reexport",
    summary="A module re-exports the catalog with a star import; another module calls the enum.",
    files={
        "shop/app/options.py": "from shop.app.catalog import *  # noqa: F403\n",
        "shop/app/maintenance.py": _APP_MAINTENANCE.replace(
            "from shop.store.sqlite import",
            "from shop.app.options import OptionKey\nfrom shop.store.sqlite import",
        )
        + "\n\ndef parse_option(raw: str) -> OptionKey:\n    return OptionKey(raw)\n",
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("catalog_limit", "shop.app.orders.read_catalog_option"),),
)

# Known cost of #731: the one-line excerpt of a wrapped signature line does not parse, so the
# collector cannot tell that `key: OptionKey,` is an annotation. The check stays UNKNOWN.
_CATALOG_ARGUMENT_WRAPPED_ANNOTATION = Variant(
    id="class-a-catalog-argument-wrapped-annotation",
    section="class_a",
    item="catalog_argument:wrapped_annotation_cost",
    summary="Known cost: an enum annotation on a wrapped signature line keeps the check UNKNOWN.",
    files={
        "shop/app/maintenance.py": _MAINTENANCE_WITH_OPTION_KEY
        + "\n\ndef handle_option(\n    request_id: int,\n    key: OptionKey,\n) -> None:\n"
        "    del request_id, key\n"
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
    _CATALOG_ARGUMENT_UNICODE_ALIAS,
    _CATALOG_ARGUMENT_VALUE_LOOKUP,
    _CATALOG_USE_MEMBER_VALUE,
    _CATALOG_ARGUMENT_STAR_REEXPORT,
    _CATALOG_ARGUMENT_WRAPPED_ANNOTATION,
)
