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


TS_SYMBOL = {
    "id": "SYMBOL",
    "kind": "forbidden_dependency",
    "source": "app.src.b",
    "target": "app.src.a",
    "target_symbol": "other",
    "include_type_checking": True,
}
TS_PLANTS: dict[str, tuple[list[str], list[str], dict[str, str]]] = {
    # rules, public entries of `a`, expected rows besides ASSIGN
    "symbol-rule": (["SYMBOL"], [], {"SYMBOL": "UNKNOWN"}),
    "symbol-rule-and-interface": (
        ["SYMBOL", "BOUNDARY"],
        [],
        {"SYMBOL": "UNKNOWN", "BOUNDARY": "UNKNOWN"},
    ),
    # The module is public, so the bare import is no violation; the symbol entry holds the rule.
    "symbol-public-and-interface": (
        ["BOUNDARY"],
        ["app.src.a.one_x2e_cts", "app.src.a.one_x2e_cts:one"],
        {"BOUNDARY": "UNKNOWN"},
    ),
}


def typescript(core: Path, root: Path, plant: str) -> dict[str, Any]:
    """A CommonJS file cannot use a browser global and a bare import names no symbol, so the reply
    has no `script-globals-v1` and states `dependency_symbols` as unsupported."""
    from test_cli_core_mounted_receipt import RULE as TS_RULE
    from test_cli_core_mounted_receipt import component as ts_component
    from test_cli_core_only_scan import command

    names, public, _ = TS_PLANTS[plant]
    a = ts_component("a", ["app.src.a"], **({"public": public} if public else {}))
    chosen = {
        "SYMBOL": TS_SYMBOL,
        "BOUNDARY": {"id": "BOUNDARY", "kind": "interface_boundary"},
    }
    contract = {
        "schema_version": "2.2.0",
        "components": [a, ts_component("b", ["app.src.b"], ("a",))],
        "rules": [{**TS_RULE, **chosen[name]} for name in names]
        + [{**TS_RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"}],
    }
    files = {
        "README.md": "x\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
        "src/a/one.cts": "export const one = 1;\nexport const other = 2;\n",
        "src/b/two.cts": "import '../a/one.cjs';\nexport const two = 2;\n",
        "archkeel.toml": '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n',
        "architecture-contract.json": json.dumps(contract),
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    names_env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env = {**os.environ, **names_env, "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    result: dict[str, Any] = json.loads(command(core, root, "--json").stdout)
    return result


@pytest.mark.parametrize("plant", sorted(TS_PLANTS))
def test_typescript_without_the_symbol_feature_holds_only_the_symbol_readers(
    release_core: Path, tmp_path: Path, plant: str
) -> None:
    """Before AD-496 the unsupported statement held each rule of the run, as 4.0.1 does."""
    result = typescript(release_core, tmp_path, plant)
    found = {rule: row[1] for rule, row in result["frame"]["rules"].items()}
    assert found == {**TS_PLANTS[plant][2], "ASSIGN": "PASS"}, result["frame"]["explained"]
    for rule in TS_PLANTS[plant][2]:
        assert "the profile cannot decide" in result["frame"]["explained"][rule]
