# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import ArchitectureContract, CompatibilityShim, ContractDeclarations
from archkeel.ir.widening import contract_widenings
from fixtures.demo_catalog_compatibility import VARIANTS


def _run(variant_id: str, tmp_path: Path):
    variant = next(item for item in VARIANTS if item.id == variant_id)
    root = _prepare_repo(tmp_path, variant.files)
    result, report = run_report(root, config=CONFIG, analyzer=observe)
    return root, result, report


def test_shim_module_and_target_must_differ() -> None:
    with pytest.raises(ValueError, match="module and target must differ"):
        parse_contract(
            {
                "schema_version": "2.1.0",
                "components": [],
                "rules": [],
                "declarations": {
                    "compat": [
                        {"module": "pkg.same", "target": "pkg.same", "lifetime": "permanent"}
                    ]
                },
            }
        )


def test_target_change_remains_widening_when_lifetime_narrows() -> None:
    before = ArchitectureContract(
        "2.1.0",
        (),
        (),
        declarations=ContractDeclarations(
            compat=(CompatibilityShim("pkg.old", "pkg.current", "permanent"),)
        ),
    )
    after = ArchitectureContract(
        "2.1.0",
        (),
        (),
        declarations=ContractDeclarations(
            compat=(CompatibilityShim("pkg.old", "pkg.other", "migration"),)
        ),
    )

    assert contract_widenings(before, after) == (
        "compat module 'pkg.old' changed from 'pkg.current' to 'pkg.other'",
    )
