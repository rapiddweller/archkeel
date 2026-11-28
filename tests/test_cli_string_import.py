# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1440: a string import with a fixed name is a FAIL in every contract.

The built-in rule `STRING-IMPORT` is not in the contract file. Each fixed-name import call of the
scan is a violation. A computed name, `eval` and `exec` are no fixed name: they stay UNKNOWN. A
site that the team checked is a record of `declarations.string_imports`: the rule then reads PASS
under that premise. A record with another target, line or count applies to nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, project, verdict

LOAD = "import importlib\nVALUE = importlib.import_module('app.service')\n"
LOCAL = (
    "import importlib\ndef load():\n    name = 'app.service'\n"
    "    return importlib.import_module(name)\n"
)


def scan(
    core: Path,
    root: Path,
    source: str,
    declared: list[dict[str, Any]] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    path = project(root, {**BASE, "src/app/client.py": source}, contract_rules=rules)
    if declared is not None:
        contract = json.loads((path / "architecture-contract.json").read_text())
        contract["schema_version"] = "3.22.0"
        contract["declarations"] = {"string_imports": declared}
        (path / "architecture-contract.json").write_text(json.dumps(contract))
    return verdict(core, path)


def record(line: int, target: str = "app.service", **more: Any) -> dict[str, Any]:
    return {
        "id": f"SI-{line}",
        "module": "app.client",
        "line": line,
        "target": target,
        "rationale": "Checked: the optional backend is loaded on demand.",
        "provenance": ["p"],
        **more,
    }


def status(result: dict[str, Any]) -> str:
    return result["frame"]["rules"]["STRING-IMPORT"][1]


@pytest.mark.parametrize(
    "source",
    [
        LOAD,
        "VALUE = __import__('app.service')\n",
        "VALUE = __import__('datetime')\n",
        LOCAL,
        "import importlib\ndef later():\n    return importlib.import_module('app.service')\n",
    ],
    ids=["import_module", "dunder", "standard library", "adjacent local", "in a function"],
)
def test_a_fixed_string_import_is_a_fail(release_core: Path, tmp_path: Path, source: str) -> None:
    result = scan(release_core, tmp_path, source)
    assert status(result) == "FAIL"
    assert result["frame"]["violations"]["STRING-IMPORT"] == 1
    assert (result["status"], result["exit_code"]) == ("FAIL", 1)


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nVALUE = importlib.import_module(name)\n",
        "import importlib\nVALUE = importlib.import_module('app.' + name)\n",
        "import importlib\nVALUE = importlib.import_module(f'app.{name}')\n",
        "import importlib\nload = importlib.import_module\nVALUE = load('app.service')\n",
        "VALUE = eval(text)\n",
        "exec(text)\n",
    ],
    ids=["name", "concatenation", "f-string", "stored loader", "eval", "exec"],
)
def test_a_computed_name_eval_and_exec_stay_unknown(
    release_core: Path, tmp_path: Path, source: str
) -> None:
    result = scan(release_core, tmp_path, source)
    assert "STRING-IMPORT" not in result["frame"]["violations"], result["frame"]["details"]
    assert status(result) == "UNKNOWN"


def test_a_scan_without_a_string_import_passes_the_rule(release_core: Path, tmp_path: Path) -> None:
    result = scan(release_core, tmp_path, "import os\n")
    assert status(result) == "PASS"
    assert "STRING-IMPORT" not in result["frame"]["violations"]


def test_a_declared_site_reads_pass_under_its_premise(release_core: Path, tmp_path: Path) -> None:
    result = scan(release_core, tmp_path, LOAD, [record(2)])
    assert status(result) == "PASS"
    assert "STRING-IMPORT" not in result["frame"]["violations"]
    assert result["frame"]["assuming"] == "1 declared string import"
    assert "app.client:2" in json.dumps(result["frame"]["premises"]), result["frame"]["premises"]


@pytest.mark.parametrize(
    ("declared", "claim"),
    [
        ([record(2, "app.other")], "names app.other by a string"),
        ([record(3)], "no call in app.client at line 3"),
        ([record(2, count=2)], "counts 2 but the scan has 1"),
    ],
    ids=["wrong target", "wrong line", "wrong count"],
)
def test_a_record_that_matches_no_site_keeps_the_fail_and_is_a_defect(
    release_core: Path, tmp_path: Path, declared: list[dict[str, Any]], claim: str
) -> None:
    result = scan(release_core, tmp_path, LOAD, declared)
    assert status(result) == "FAIL"
    assert result["frame"]["violations"]["STRING-IMPORT"] == 1
    reasons = " ".join(gap["reason"] for gap in result["gaps"])
    assert "string_imports.unmatched" in reasons and claim in reasons, reasons


def test_two_sites_on_a_line_need_a_count(release_core: Path, tmp_path: Path) -> None:
    call = "importlib.import_module('app.service')"
    two = f"import importlib\nVALUE = ({call}, {call})\n"
    assert status(scan(release_core, tmp_path / "one", two, [record(2)])) == "FAIL"
    assert status(scan(release_core, tmp_path / "two", two, [record(2, count=2)])) == "PASS"


def test_a_contract_that_defines_the_built_in_id_is_refused_by_hygiene(
    release_core: Path, tmp_path: Path
) -> None:
    own = {
        "id": "STRING-IMPORT",
        "kind": "forbidden_dependency",
        "source": "app.client",
        "target": "app.service",
        "include_type_checking": True,
        "allowed_sources": [],
        "rationale": "Mine.",
        "provenance": ["p"],
        "decided_by": "architect",
    }
    result = scan(release_core, tmp_path, "import os\n", rules=[own])
    reasons = " ".join(gap["reason"] for gap in result["gaps"])
    assert "rule.reserved_id" in reasons, reasons
