# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-105: source-root relocation needs historical layout evidence."""

from __future__ import annotations

import json
import py_compile
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo
from test_renames import _git

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.ir.model import RunResult


def _relocated_root(tmp_path: Path, *, keep_old_copy: bool) -> tuple[Path, str]:
    root = _prepare_repo(tmp_path, {})
    for source in (root / "shop").rglob("*.py"):
        target = root / "src" / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source.unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "move source root")
    base = _git(root, "rev-parse", "HEAD")

    old_text = (root / "src/shop/render/text.py").read_text()
    shutil.copytree(root / "src/shop", root / "lib/shop")
    shutil.rmtree(root / "src/shop")
    shutil.move(root / "lib/shop/render", root / "lib/shop/view")
    main = root / "lib/shop/cli/main.py"
    main.write_text(main.read_text().replace("shop.render", "shop.view"))
    contract = root / "architecture-contract.json"
    contract.write_text(contract.read_text().replace("shop.render", "shop.view"))

    if keep_old_copy:
        old_source = root / "src/shop/render/text.py"
        old_source.parent.mkdir(parents=True)
        old_source.write_text(old_text)
    return root, base


def _validate_relocated(root: Path, base: str) -> RunResult:
    return run_validate(
        root,
        replace(SHOP_CONFIG, roots=("lib",)),
        observe,
        against=base,
        against_config=replace(SHOP_CONFIG, roots=("src",)),
    )[0]


def _nested_layout_rename(tmp_path: Path, *, keep_old_bytecode: bool) -> tuple[Path, str]:
    root = _prepare_repo(tmp_path, {})
    for source in (root / "shop").rglob("*.py"):
        target = root / "src/old" / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)
    config = root / "archkeel.toml"
    config.write_text(config.read_text().replace('roots = ["shop"]', 'roots = ["src"]'))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "move source into nested root")
    base = _git(root, "rev-parse", "HEAD")

    if keep_old_bytecode:
        py_compile.compile(
            str(root / "src/old/shop/render/text.py"),
            cfile=str(root / "src/old/shop/render/legacy.pyc"),
            doraise=True,
        )
    for source in (root / "src/old/shop").rglob("*.py"):
        target = root / "src/new" / source.relative_to(root / "src/old")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)
    shutil.move(root / "src/new/shop/render", root / "src/new/shop/view")
    for source in (root / "src/new/shop").rglob("*.py"):
        source.write_text(source.read_text().replace("shop.render", "shop.view"))
    contract = root / "architecture-contract.json"
    contract.write_text(contract.read_text().replace("shop.render", "shop.view"))
    return root, base


def test_true_package_rename_and_physical_root_relocation_is_recognized(
    tmp_path: Path,
) -> None:
    root, base = _relocated_root(tmp_path, keep_old_copy=False)

    result = _validate_relocated(root, base)

    assert (result.exit_code, result.failures) == (0, ()), result.diagnostics
    assert result.renames == (("shop.render", "shop.view"),)


def test_old_source_copy_in_the_previous_physical_root_blocks_the_rename(
    tmp_path: Path,
) -> None:
    root, base = _relocated_root(tmp_path, keep_old_copy=True)

    result = _validate_relocated(root, base)

    assert result.exit_code == 1, result.diagnostics
    assert result.renames == ()
    assert any("component 'render'.packages changed" in failure for failure in result.failures)


def test_cli_proves_same_config_nested_layout_move_from_historical_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, base = _nested_layout_rename(tmp_path, keep_old_bytecode=False)

    assert main(["validate", "--root", str(root), "--against", base, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["renames"] == [["shop.render", "shop.view"]]


def test_cli_rejects_same_config_move_with_sourceless_old_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, base = _nested_layout_rename(tmp_path, keep_old_bytecode=True)

    assert main(["validate", "--root", str(root), "--against", base, "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["renames"] == []
