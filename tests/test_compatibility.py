# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import ArchitectureContract, CompatibilityShim, ContractDeclarations
from archkeel.ir.widening import contract_widenings
from fixtures.demo_catalog_compatibility import VARIANTS


def _run(variant_id: str, tmp_path: Path):
    variant = next(item for item in VARIANTS if item.id == variant_id)
    root = _prepare_repo(tmp_path, variant.files)
    result, report = run_report(root, config=CONFIG, analyzer=observe)
    return root, result, report


def test_migration_shim_exposes_sorted_remaining_work(tmp_path: Path) -> None:
    _root, result, report = _run("class-a-compatibility-migration", tmp_path)
    assert result.exit_code == 0
    assert report is not None
    observation = observe(
        _root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="0" * 40,
        dirty=False,
        contract_root=_root,
    ).observation
    assert observation is not None
    work = next(
        item
        for item in observation.records("declarations") or ()
        if item.kind == "compatibility_migration_work"
    )
    assert work.data.get("count") == 1
    assert work.data.get("modules") == ("shop.model.legacy",)


def test_permanent_shim_has_no_remaining_work_record(tmp_path: Path) -> None:
    _root, result, _report = _run("class-a-compatibility-clean", tmp_path)
    assert result.exit_code == 0
    observation = observe(
        _root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="0" * 40,
        dirty=False,
        contract_root=_root,
    ).observation
    assert observation is not None
    assert not any(
        item.kind == "compatibility_migration_work"
        for item in observation.records("declarations") or ()
    )


@pytest.mark.parametrize(
    "body",
    (
        'from shop.model.entities import Money\n__all__ = make_exports()\n__all__ = ["Money"]\n',
        'from shop.model.entities import Money\nside = __all__ = ["Money"]\n',
    ),
)
def test_shim_rejects_non_literal_or_chained_all(body: str, tmp_path: Path) -> None:
    variant = next(item for item in VARIANTS if item.id == "class-a-compatibility-clean")
    files = {**variant.files, "shop/model/legacy.py": body}
    root = _prepare_repo(tmp_path, files)

    result, _report = run_validate(root, CONFIG, observe)

    assert result.exit_code == 2
    assert "compatibility.invalid" in {item.code for item in result.diagnostics}


def test_shim_rejects_exports_from_another_module(tmp_path: Path) -> None:
    variant = next(item for item in VARIANTS if item.id == "class-a-compatibility-clean")
    files = {
        **variant.files,
        "shop/model/legacy.py": (
            "from shop.model.entities import Money\n"
            "from shop.model.other import Other\n"
            '__all__ = ["Other"]\n'
        ),
        "shop/model/other.py": "class Other:\n    pass\n",
    }
    root = _prepare_repo(tmp_path, files)

    result, _report = run_validate(root, CONFIG, observe)

    assert result.exit_code == 2
    assert "compatibility.invalid" in {item.code for item in result.diagnostics}


def test_shim_rejects_export_with_two_distinct_origins(tmp_path: Path) -> None:
    variant = next(item for item in VARIANTS if item.id == "class-a-compatibility-clean")
    files = {
        **variant.files,
        "shop/model/legacy.py": (
            "from shop.model.entities import Money\n"
            "from os import path as Money\n"
            '__all__ = ["Money"]\n'
        ),
    }
    root = _prepare_repo(tmp_path, files)

    result, _report = run_validate(root, CONFIG, observe)

    assert result.exit_code == 2
    assert "compatibility.invalid" in {item.code for item in result.diagnostics}


def test_shim_rejects_two_symbols_from_target_under_one_export(tmp_path: Path) -> None:
    variant = next(item for item in VARIANTS if item.id == "class-a-compatibility-clean")
    files = {
        **variant.files,
        "shop/model/legacy.py": (
            "from shop.model.entities import Money as Legacy\n"
            "from shop.model.entities import Order as Legacy\n"
            '__all__ = ["Legacy"]\n'
        ),
    }
    root = _prepare_repo(tmp_path, files)

    result, _report = run_validate(root, CONFIG, observe)

    assert result.exit_code == 2
    assert "compatibility.invalid" in {item.code for item in result.diagnostics}


def test_shim_accepts_two_paths_to_the_same_origin(tmp_path: Path) -> None:
    variant = next(item for item in VARIANTS if item.id == "class-a-compatibility-clean")
    files = {
        **variant.files,
        "shop/model/legacy.py": (
            "from shop.model.entities import Money\n"
            "from shop.model.entities import Money\n"
            '__all__ = ["Money"]\n'
        ),
    }
    root = _prepare_repo(tmp_path, files)

    result, _report = run_validate(root, CONFIG, observe)

    assert result.exit_code == 0


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
