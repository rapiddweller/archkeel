# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Baseline 1.4.0 compares the three budgets of calls and types (AD-1090, #1919).

Each test runs the real core on a small Python project whose contract declares the budgets.
A budget above its ceiling is red (exit 1), a declared budget without a ceiling is red, and
only a run without any difference gets exit 0 or 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, project, verdict

BUDGETS = ("calls_unresolved", "typing_positions", "untyped_private_accesses")
CLIENT = "import os\n\n\ndef run(value, other):\n    return value.go(other) + value._hidden\n"


def built_project(tmp_path: Path) -> Path:
    root = project(tmp_path, {**BASE, "src/app/client.py": CLIENT})
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.6.0"
    contract["declarations"] = {
        "measurement_budgets": [{"name": name, "provenance": ["p"]} for name in BUDGETS]
    }
    path.write_text(json.dumps(contract))
    return root


def written(core: Path, root: Path) -> dict[str, Any]:
    verdict(core, root, "validate", "--write-baseline", "b.json")
    return json.loads((root / "b.json").read_text())


def compared(core: Path, root: Path, document: dict[str, Any]) -> dict[str, Any]:
    (root / "b.json").write_text(json.dumps(document))
    return verdict(core, root, "validate", "--baseline", "b.json")


def test_a_budget_equal_to_the_file_gives_no_row(release_core: Path, tmp_path: Path) -> None:
    root = built_project(tmp_path)
    document = written(release_core, root)
    assert set(BUDGETS) <= set(document["budgets"])
    assert document["budgets"]["calls_unresolved"] >= 1
    part = compared(release_core, root, document)["baseline"]
    assert part["state"] == "current" and part["new"] == [] and part["gone"] == []
    assert not [gap for gap in part["gaps"] if gap["kind"].startswith("budget")]


@pytest.mark.parametrize("name", BUDGETS)
def test_a_budget_above_the_file_is_red(release_core: Path, tmp_path: Path, name: str) -> None:
    root = built_project(tmp_path)
    document = written(release_core, root)
    measured = document["budgets"][name]
    assert measured > 0
    document["budgets"][name] = measured - 1
    result = compared(release_core, root, document)
    assert result["exit_code"] == 1, result
    [row] = result["baseline"]["new"]
    assert (row["kind"], row["subject"], row["run"], row["file"]) == (
        "budget.exceeded",
        name,
        measured,
        measured - 1,
    )


@pytest.mark.parametrize("name", BUDGETS)
def test_a_declared_budget_missing_in_the_file_is_red(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    root = built_project(tmp_path)
    document = written(release_core, root)
    del document["budgets"][name]
    result = compared(release_core, root, document)
    assert result["exit_code"] == 1, result
    [row] = result["baseline"]["new"]
    assert (row["kind"], row["subject"], row["file"]) == ("budget.unknown", name, 0)


def test_an_older_file_keeps_the_gap_of_the_other_analyzer(
    release_core: Path, tmp_path: Path
) -> None:
    root = built_project(tmp_path)
    document = written(release_core, root)
    older = {
        "schema_version": "1.3.0",
        "violations": document["violations"],
        "budgets": {name: 0 for name in BUDGETS} | {"cycle_edges": 0, "private_crossings": 0},
    }
    result = compared(release_core, root, older)
    kinds = {gap["kind"] for gap in result["baseline"]["gaps"]}
    assert kinds == {"baseline.older_schema", "baseline.budget_of_older_schema"}
    assert result["exit_code"] != 0
    assert result["baseline"]["new"] == []


def test_a_run_with_declared_budgets_and_no_file_keeps_its_named_row(
    release_core: Path, tmp_path: Path
) -> None:
    result = verdict(release_core, built_project(tmp_path), "validate")
    assert result["status"] != "PASS"
    assert "budget.unknown" in {gap["kind"] for gap in result["gaps"]}
