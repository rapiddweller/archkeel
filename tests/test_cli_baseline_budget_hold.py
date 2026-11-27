# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A declared budget that a baseline compares is decided, and any other stays UNKNOWN (#2162).

Before, a declared `measurement_budgets` entry held the run UNKNOWN ("the profile cannot decide"),
also when `validate --baseline` compared it. A contract with budgets then never exited 0. The
comparison is the decision: a value within the file lifts the hold, a value over it is `drift`
(exit 1), and a budget that the file lacks, an older file, a write alone or no file keeps the hold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import project, verdict
from test_cli_python_gap_effects import FILES, RULES

BUDGETS = ("private_crossings", "typing_positions", "calls_unresolved")
# Gives the run one unresolved call and one untyped position, so a ceiling can be one below.
EXTRA = {"src/app/client/extra.py": "def run(value):\n    return value.go()\n"}


def declared(tmp_path: Path, names: tuple[str, ...] = BUDGETS) -> Path:
    root = project(tmp_path, {**FILES, **EXTRA}, contract_rules=[*RULES])
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["declarations"] = {
        "measurement_budgets": [{"name": name, "provenance": ["p"]} for name in names]
    }
    path.write_text(json.dumps(contract))
    return root


def written(core: Path, root: Path) -> dict[str, Any]:
    verdict(core, root, "validate", "--write-baseline", "b.json")
    return json.loads((root / "b.json").read_text())


def compared(core: Path, root: Path, document: dict[str, Any]) -> dict[str, Any]:
    (root / "b.json").write_text(json.dumps(document))
    return verdict(core, root, "validate", "--baseline", "b.json")


def held(result: dict[str, Any]) -> str:
    return result["frame"]["scope"]


def test_a_budget_within_the_file_is_decided(release_core: Path, tmp_path: Path) -> None:
    root = declared(tmp_path)
    result = compared(release_core, root, written(release_core, root))
    assert (result["status"], result["exit_code"]) == ("PASS", 0), result["gaps"]
    assert result["baseline"]["state"] == "current"


@pytest.mark.parametrize("name", ("typing_positions", "calls_unresolved"))
def test_a_budget_over_the_file_stays_red(release_core: Path, tmp_path: Path, name: str) -> None:
    root = declared(tmp_path)
    document = written(release_core, root)
    document["budgets"][name] -= 1
    result = compared(release_core, root, document)
    assert (result["exit_code"], result["baseline"]["state"]) == (1, "drift")
    [row] = result["baseline"]["new"]
    assert (row["kind"], row["subject"]) == ("budget.exceeded", name)
    assert result["status"] != "PASS"


@pytest.mark.parametrize("name", BUDGETS)
def test_a_budget_missing_in_the_file_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    root = declared(tmp_path)
    document = written(release_core, root)
    del document["budgets"][name]
    result = compared(release_core, root, document)
    assert (result["exit_code"], result["baseline"]["state"]) == (1, "drift")
    assert result["status"] == "UNKNOWN"
    assert f"declarations.measurement_budgets.{name}" in held(result), held(result)


def test_an_older_file_keeps_the_hold(release_core: Path, tmp_path: Path) -> None:
    root = declared(tmp_path)
    document = written(release_core, root)
    older = {
        "schema_version": "1.3.0",
        "violations": document["violations"],
        "budgets": {name: 0 for name in document["budgets"]},
    }
    result = compared(release_core, root, older)
    assert result["status"] == "UNKNOWN" and result["exit_code"] != 0
    assert "declarations.measurement_budgets" in held(result)


def test_no_file_and_a_write_alone_keep_the_hold(release_core: Path, tmp_path: Path) -> None:
    root = declared(tmp_path)
    assert verdict(release_core, root, "validate")["status"] == "UNKNOWN"
    alone = verdict(release_core, root, "validate", "--write-baseline", "w.json")
    assert (alone["status"], alone["exit_code"]) == ("UNKNOWN", 2)


def test_only_the_budgets_that_the_file_holds_are_decided(
    release_core: Path, tmp_path: Path
) -> None:
    root = declared(tmp_path)
    document = written(release_core, root)
    del document["budgets"]["typing_positions"]
    result = compared(release_core, root, document)
    text = held(result)
    assert "declarations.measurement_budgets.typing_positions" in text, text
    assert "private_crossings" not in text and "calls_unresolved" not in text, text
