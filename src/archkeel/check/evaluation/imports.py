# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Projection of source import facts into the existing observation vocabulary."""

from collections.abc import Sequence

from archkeel.ir.facts_codec import RawRecord


def strip_internal_reexport_facts(imports: Sequence[RawRecord]) -> None:
    """Keep reexport-route bookkeeping private, while retaining publisher uniqueness."""
    for item in imports:
        data = item["data"]
        if "ordinary_module" in data:
            del data["ordinary_module"]
        if "origin_member_binding_static" in data:
            del data["origin_member_binding_static"]
        if "origin_binding_unique" in data:
            del data["origin_binding_unique"]
        if "reexport_candidate" in data:
            del data["reexport_candidate"]
        if "module_level_import" in data:
            del data["module_level_import"]
