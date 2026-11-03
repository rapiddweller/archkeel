# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: the contract-free explore demo, a repository with no ArchKeel file."""

from __future__ import annotations

from pathlib import Path

from fixtures.demo_catalog_support import Variant

EXPLORE_FIXTURE_DIR = Path(__file__).resolve().parent / "N-explore"


def nested_engine_files() -> dict[str, str]:
    """A deep `shop.engine` of 54 modules: explore splits it down to `engine.io.clients.rdbms`."""
    files: dict[str, str] = {}
    for package, modules in (
        ("shop/engine", 0),
        ("shop/engine/core", 4),
        ("shop/engine/io", 1),
        ("shop/engine/io/clients", 0),
        ("shop/engine/io/clients/rdbms", 24),
        ("shop/engine/io/clients/mongo", 19),
    ):
        files[f"{package}/__init__.py"] = ""
        files.update((f"{package}/m{index:02d}.py", "VALUE = 1\n") for index in range(modules))
    files["shop/engine/io/clients/rdbms/m00.py"] = "from shop.engine.core import m00\n"
    return files


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="explore-contract-free",
        section="showcase",
        item="explore:contract-free",
        summary="explore shows four layout components; the 54-module engine opens level by "
        "level down to engine.io.clients.rdbms. No rule is declared, so the target is "
        "unavailable and no rule passes or fails.",
        files=nested_engine_files(),
        expected_violations=(),
        expected_codes=(),
        fixture=EXPLORE_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
    ),
)
