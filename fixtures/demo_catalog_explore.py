# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: the contract-free explore demo, a repository with no ArchKeel file."""

from __future__ import annotations

from pathlib import Path

from fixtures.demo_catalog_support import Variant
from fixtures.demo_catalog_typescript import TYPESCRIPT_FIXTURE_DIR

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
        id="explore-root-package-with-rust-src",
        section="showcase",
        item="explore:root-package-with-rust-src",
        summary="explore selects the root Python package when src contains only a Rust crate.",
        files={
            "src/rust_crate/Cargo.toml": '[package]\nname = "rust-crate"\nversion = "0.1.0"\n',
            "src/rust_crate/src/main.rs": "fn main() {}\n",
        },
        expected_violations=(),
        expected_codes=(),
        fixture=EXPLORE_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
    ),
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
    Variant(
        id="explore-excludes-test-sources",
        section="showcase",
        item="explore:test-source-exclusion",
        summary=(
            "Explore includes production `shop/latest.py` while excluding "
            "`shop/tests/test_latest.py` inside the selected source root."
        ),
        files={
            "shop/latest.py": "VALUE = 1\n",
            "shop/tests/test_latest.py": (
                "from shop.latest import VALUE\n\n\n"
                "def test_value() -> None:\n"
                "    assert VALUE == 1\n"
            ),
        },
        expected_violations=(),
        expected_codes=(),
        fixture=EXPLORE_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
    ),
    Variant(
        id="explore-typescript-explicit-output-limit",
        section="showcase",
        item="explore:typescript-output-limit",
        summary="explore accepts an explicit finite TypeScript stdout limit; larger values can "
        "need more memory.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=TYPESCRIPT_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
        explore_options=(
            "--language",
            "typescript",
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
            "--collector-output-limit-bytes",
            str(96 * 1024 * 1024),
        ),
    ),
    Variant(
        id="explore-typescript-v8-8kib",
        section="showcase",
        item="explore:typescript-v8-8kib",
        summary="Built-in TypeScript collection fits under 8 KiB with V8 compression; the same "
        "fixture sent as V3 exceeds that limit.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=TYPESCRIPT_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
        explore=True,
        explore_options=(
            "--language",
            "typescript",
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
            "--collector-output-limit-bytes",
            str(8 * 1024),
        ),
    ),
)
