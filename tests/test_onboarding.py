# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import main
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import (
    ArchitectureContract,
    CompleteAssignmentRule,
    ForbiddenDependencyRule,
    NoComponentCyclesRule,
)

ROOT = Path(__file__).parents[1]


def _contract(path: Path) -> ArchitectureContract:
    return parse_contract(decode_json(path.read_bytes()))


def _repository(root: Path, packages: tuple[str, ...] = ("archkeel",)) -> Path:
    for package in packages:
        shutil.copytree(
            ROOT / "src/archkeel",
            root / "src" / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    for args in (
        ("init", "-q"),
        ("config", "user.email", "init@example.invalid"),
        ("config", "user.name", "Archkeel init"),
        ("add", "."),
        ("commit", "-qm", "snapshot"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def test_init_reproduces_the_closed_world_of_archkeel_and_validate_lists_the_rationales(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    assert main(["init", "--root", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] == "architecture-contract.json"

    own = _contract(ROOT / "architecture-contract.json")
    draft = _contract(root / "architecture-contract.json")
    packages = {component.packages[0] for component in own.components}
    assert {component.packages for component in draft.components} == {
        component.packages for component in own.components
    }
    assert {
        (rule.source, rule.target)
        for rule in draft.rules
        if isinstance(rule, ForbiddenDependencyRule)
    } == {
        (rule.source, rule.target)
        for rule in own.rules
        if isinstance(rule, ForbiddenDependencyRule)
        and rule.source in packages
        and rule.target in packages
    }
    assert any(isinstance(rule, CompleteAssignmentRule) for rule in draft.rules)
    assert any(isinstance(rule, NoComponentCyclesRule) for rule in draft.rules)

    assert main(["validate", "--root", str(root), "--json"]) == 2
    pointers = {item["pointer"] for item in json.loads(capsys.readouterr().out)["diagnostics"]}
    assert pointers == {f"/rules/{index}/rationale" for index in range(len(draft.rules))}

    contract = root / "architecture-contract.json"
    contract.write_text(contract.read_text().replace("TODO: explain why", "The owners decided"))
    assert main(["validate", "--root", str(root), "--json"]) == 0


def test_init_never_replaces_existing_files_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    (root / "archkeel.toml").write_text("[scan]\n")
    assert main(["init", "--root", str(root), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "existing_files" and diagnostic["subject"] == "archkeel.toml"
    assert (root / "archkeel.toml").read_text() == "[scan]\n"
    assert main(["init", "--root", str(root), "--json", "--force"]) == 0


def test_init_asks_for_the_source_when_the_package_is_ambiguous(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path, ("alpha", "beta"))
    assert main(["init", "--root", str(root), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert (
        diagnostic["kind"] == "scope_empty" and "src/alpha, src/beta" in diagnostic["unknown_claim"]
    )
    assert not (root / "archkeel.toml").exists()
