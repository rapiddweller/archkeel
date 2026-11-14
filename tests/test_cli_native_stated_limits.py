# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-496: a stated unsupported feature holds only the rules that read it.

The linked Python collector states that it reads no dependency symbol and no module interface.
Each plant adds one reader of one feature: that rule stays UNKNOWN, and each rule that reads
only module-level import edges is decided, also when its edge is a violation.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, RULE, project, rows, rules, verdict

EDGE_RULES = ("FORBID", "ASSIGN", "CYCLES", "EXTERNAL")
VIOLATION = {**BASE, "src/app/client.py": "from app.service import VALUE\n"}


def symbol_rule(contract: dict[str, Any]) -> str:
    contract["rules"].append(
        {
            **RULE,
            "id": "SYMBOL",
            "kind": "forbidden_dependency",
            "source": "app.client",
            "target": "app.service",
            "target_symbol": "OTHER",
            "include_type_checking": True,
        }
    )
    return "SYMBOL"


def symbol_port(contract: dict[str, Any]) -> str:
    client = next(c for c in contract["components"] if c["label"] == "client")
    client["requires"][0]["through"] = ["app.service:VALUE"]
    contract["rules"].append({**RULE, "id": "REQUIRES", "kind": "complete_requires"})
    return "REQUIRES"


def interface_rule(contract: dict[str, Any]) -> str:
    contract["rules"].append({**RULE, "id": "BOUNDARY", "kind": "interface_boundary"})
    return "BOUNDARY"


def symbol_public(contract: dict[str, Any]) -> str:
    service = next(c for c in contract["components"] if c["label"] == "service")
    service["public"] = ["app.service:VALUE"]
    return interface_rule(contract)


PLANTS: dict[str, Callable[[dict[str, Any]], str]] = {
    "dependency_symbols-target_symbol": symbol_rule,
    "dependency_symbols-through_port": symbol_port,
    "dependency_symbols-public_entry": symbol_public,
    "interface_boundary-rule": interface_rule,
}


def planted(root: Path, files: dict[str, str], plant: Callable[[dict[str, Any]], str]) -> str:
    project(root, files, contract_rules=rules())
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    reader = plant(contract)
    path.write_text(json.dumps(contract))
    names = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env = {**os.environ, **names, "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "plant"], check=True, env=env)
    return reader


@pytest.mark.parametrize("name", PLANTS)
def test_a_stated_limit_holds_its_reader_and_no_edge_rule(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    reader = planted(tmp_path, BASE, PLANTS[name])
    result = verdict(release_core, tmp_path, "report")
    found = rows(result)
    assert found[reader] == "UNKNOWN", result
    assert {rule: found[rule] for rule in EDGE_RULES} == dict.fromkeys(EDGE_RULES, "PASS")
    assert result["status"] != "PASS" and result["exit_code"] != 0


@pytest.mark.parametrize("name", PLANTS)
def test_a_stated_limit_hides_no_edge_violation(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    reader = planted(tmp_path, VIOLATION, PLANTS[name])
    found = rows(verdict(release_core, tmp_path, "report"))
    assert found[reader] == "UNKNOWN"
    assert found["FORBID"] == "FAIL"


def test_a_symbol_public_entry_without_a_reader_holds_no_rule(
    release_core: Path, tmp_path: Path
) -> None:
    def public_only(contract: dict[str, Any]) -> str:
        symbol_public(contract)
        contract["rules"].pop()
        return "FORBID"

    planted(tmp_path, BASE, public_only)
    result = verdict(release_core, tmp_path)
    assert rows(result) == dict.fromkeys(EDGE_RULES, "PASS")
    # AD-466 hygiene can still hold the status; no profile limit may hold it.
    assert result["frame"]["scope"] == "complete", result
    assert "profile" not in json.dumps(result["frame"]["unsupported"])
