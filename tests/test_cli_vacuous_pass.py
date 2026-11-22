# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: a rule that names nothing that the scan saw never gives PASS.

Consumer: `archkeel validate` through the release core. A typo in the package of an
`external_dependency_scope` rule, a typo in the `target_symbol` of a `forbidden_dependency`
rule, and an `interface_boundary` rule without any `public` entry each left the rule with nothing
to examine, and the verdict was PASS. Each plant has a control that keeps its verdict.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from test_cli_native_python_imports import BASE, RULE, project, rows, verdict

REQUESTS = {**BASE, "src/app/client.py": "import requests\n"}
YAML = {**BASE, "src/app/client.py": "import yaml\n"}
SYMBOL = {
    **BASE,
    "src/app/client.py": "from app.service import h\n",
    "src/app/service.py": "def g(): return 1\ndef h(): return 2\n",
    "src/app/other.py": "from app.service import g\n",
}


def amend(root: Path, change: Callable[[dict], None]) -> Path:
    """Change the contract of a built project and commit it, so that the tree stays clean."""
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    change(contract)
    path.write_text(json.dumps(contract))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-qam", "amend"], check=True)
    return root


def newer(contract: dict) -> None:
    """`target_symbol` needs a newer schema than the helper writes."""
    contract["schema_version"] = "3.14.0"


def external(dependency: str, allowed: str = "app.service") -> dict:
    return {
        **RULE,
        "id": "R",
        "kind": "external_dependency_scope",
        "dependency": dependency,
        "allowed_sources": [allowed],
    }


def symbol(name: str) -> dict:
    return {
        **RULE,
        "id": "R",
        "kind": "forbidden_dependency",
        "source": "app.client",
        "target": "app.service",
        "target_symbol": name,
        "include_type_checking": True,
    }


def reason(result: dict) -> str:
    return str(result["frame"].get("explained"))


@pytest.mark.parametrize(
    ("files", "dependency", "word"),
    [
        (REQUESTS, "requestz", "UNKNOWN"),
        (YAML, "PyYAML", "UNKNOWN"),
        (REQUESTS, "requests", "FAIL"),
        ({**BASE}, "requests", "UNKNOWN"),
    ],
    ids=["typo", "distribution-name", "control-outside-source", "control-no-import"],
)
def test_an_external_package_that_no_import_names_is_not_pass(
    release_core: Path, tmp_path: Path, files: dict, dependency: str, word: str
) -> None:
    result = verdict(release_core, project(tmp_path, files, contract_rules=[external(dependency)]))
    assert rows(result) == {"R": word}, result["frame"]
    if word == "UNKNOWN":
        assert "the named package matches no import" in str(result), result["frame"]


def test_an_external_package_that_an_allowed_source_imports_keeps_pass(
    release_core: Path, tmp_path: Path
) -> None:
    rule = external("requests", allowed="app.client")
    result = verdict(release_core, project(tmp_path, REQUESTS, contract_rules=[rule]))
    assert rows(result) == {"R": "PASS"}, result["frame"]


@pytest.mark.parametrize(
    ("name", "word"),
    [("gg", "UNKNOWN"), ("g", "PASS")],
    ids=["typo", "control-named-by-another-source"],
)
def test_a_target_symbol_that_no_import_names_is_not_pass(
    release_core: Path, tmp_path: Path, name: str, word: str
) -> None:
    root = amend(project(tmp_path, SYMBOL, contract_rules=[symbol(name)]), newer)
    result = verdict(release_core, root)
    assert rows(result) == {"R": word}, result["frame"]
    if word == "UNKNOWN":
        assert "the target symbol is named by no import and declared in no target module" in str(
            result
        ), result["frame"]


def test_a_target_symbol_that_the_source_imports_still_fails(
    release_core: Path, tmp_path: Path
) -> None:
    files = {**SYMBOL, "src/app/client.py": "from app.service import g\n"}
    root = amend(project(tmp_path, files, contract_rules=[symbol("g")]), newer)
    result = verdict(release_core, root)
    assert rows(result) == {"R": "FAIL"}, result["frame"]


def test_an_interface_boundary_without_a_public_entry_is_not_pass(
    release_core: Path, tmp_path: Path
) -> None:
    rule = {**RULE, "id": "R", "kind": "interface_boundary"}
    files = {**BASE, "src/app/client.py": "import app.service\n"}
    result = verdict(release_core, project(tmp_path, files, contract_rules=[rule]))
    assert rows(result) == {"R": "UNKNOWN"}, result["frame"]
    assert "no component declares a public interface" in str(result), result["frame"]
