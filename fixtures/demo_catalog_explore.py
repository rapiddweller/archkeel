# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: the contract-free explore demo, a repository with no ArchKeel file."""

from __future__ import annotations

from pathlib import Path

from fixtures.demo_catalog_support import Variant

EXPLORE_FIXTURE_DIR = Path(__file__).resolve().parent / "N-explore"

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="explore-contract-free",
        section="showcase",
        item="explore:contract-free",
        summary="explore shows three layout components and their inventory; no rule is "
        "declared, so the target is unavailable and no rule passes or fails.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=EXPLORE_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
    ),
)
