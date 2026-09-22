# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compatibility-shim declaration demos for issue #93."""

from __future__ import annotations

from fixtures.demo_catalog_support import (
    HEADER,
    AgainstExpectation,
    Variant,
    contract_compat_replaced,
)

_PERMANENT = {
    "module": "shop.model.legacy",
    "target": "shop.model.entities",
    "lifetime": "permanent",
}
_MIGRATION = {**_PERMANENT, "lifetime": "migration"}
_SHIM = (
    HEADER + '"""Old import path kept as a logic-free compatibility shim."""\n\n'
    'from shop.model.entities import Money\n\n__all__ = ["Money"]\n'
)

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="class-a-compatibility-clean",
        section="clean",
        item="compatibility:clean",
        summary="A declared shim contains only the target import and literal __all__.",
        files={
            "shop/model/legacy.py": _SHIM,
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="class-a-compatibility-migration",
        section="class_a",
        item="compatibility:migration-work",
        summary="A migration shim is clean but exposes deterministic remaining work.",
        files={
            "shop/model/legacy.py": _SHIM,
            "architecture-contract.json": contract_compat_replaced([_MIGRATION]),
        },
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="class-a-compatibility-effectful",
        section="class_a",
        item="compatibility:effectful-shim",
        summary="Definitions in a declared shim fail closed as an invalid compatibility surface.",
        files={
            "shop/model/legacy.py": HEADER
            + '"""Not a logic-free shim."""\n\nclass Legacy:\n    pass\n',
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=("compatibility.invalid", "compatibility.invalid"),
    ),
    Variant(
        id="class-a-compatibility-product-import",
        section="class_a",
        item="compatibility:product-import",
        summary="Product code importing an old path fails the external-only shim rule.",
        files={
            "shop/model/legacy.py": _SHIM,
            "shop/model/legacy_user.py": "from shop.model.legacy import Money\n",
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=("compatibility.invalid",),
    ),
    Variant(
        id="class-a-compatibility-wrong-export",
        section="class_a",
        item="compatibility:wrong-export",
        summary="Every compatibility export must come from the declared target.",
        files={
            "shop/model/legacy.py": HEADER
            + "from shop.model.entities import Money\n"
            + "from shop.model.other import Other\n\n"
            + '__all__ = ["Other"]\n',
            "shop/model/other.py": HEADER + "class Other:\n    pass\n",
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=("compatibility.invalid",),
    ),
    Variant(
        id="against-compatibility-added",
        section="validation",
        item="against:compatibility-added",
        summary="Adding a compatibility shim widens the contract.",
        files={
            "shop/model/legacy.py": _SHIM,
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=(),
        against=AgainstExpectation(
            "compat_added",
            1,
            ("compat module 'shop.model.legacy' added",),
        ),
    ),
    Variant(
        id="against-compatibility-promoted",
        section="validation",
        item="against:compatibility-promoted",
        summary="Promoting a migration shim to permanent widens the contract.",
        files={
            "shop/model/legacy.py": _SHIM,
            "architecture-contract.json": contract_compat_replaced([_PERMANENT]),
        },
        expected_violations=(),
        expected_codes=(),
        against=AgainstExpectation(
            "compat_promoted",
            1,
            ("compat module 'shop.model.legacy' lifetime became permanent",),
            base_files={
                "shop/model/legacy.py": _SHIM,
                "architecture-contract.json": contract_compat_replaced([_MIGRATION]),
            },
        ),
    ),
)
