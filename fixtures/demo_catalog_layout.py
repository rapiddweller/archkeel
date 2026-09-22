# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-86 root layout demos."""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="class-a-root-layout-clean",
        section="clean",
        item="root_layout:clean",
        summary="The shop root contains only its five declared immediate children.",
        files={},
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="class-a-root-layout-violation",
        section="class_a",
        item="root_layout:unexpected-child",
        summary="An unexpected module directly below shop is a root layout violation.",
        files={"shop/rogue.py": HEADER + '"""Unexpected root child."""\n\nVALUE = 1\n'},
        expected_violations=("ASSIGNMENT-COMPLETE", "ROOT-LAYOUT"),
        expected_codes=("rule.violated", "rule.violated"),
    ),
)
