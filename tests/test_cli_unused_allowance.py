# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1070: an exception entry that no subject of its rule uses is a named gap `unused_allowance`.

Consumer: a CI job that reads the exit code and the gaps. The entry protects nothing and can hide a
new violation later, so the run reads UNKNOWN (exit 2) until a person deletes or corrects it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from boundary_types_plants import PLANTS
from boundary_types_sources import project as boundary_project
from core_support import ROOT
from test_cli_core_only_scan import command
from test_cli_native_python_imports import BASE, RULE, project, rows, verdict

from tools.fixture_tree import fixture_tree

FORBID = {
    **RULE,
    "id": "FORBID",
    "kind": "forbidden_dependency",
    "source": "app.client",
    "target": "app.service",
    "include_type_checking": True,
}
IMPORTS = {**BASE, "src/app/client.py": "import app.service\n"}
EXTERNAL = {
    **RULE,
    "id": "EXTERNAL",
    "kind": "external_dependency_scope",
    "dependency": "requests",
}
PLACEMENT = {
    **RULE,
    "id": "PLACEMENT",
    "kind": "symbol_placement",
    "source": "app",
    "class_kinds": ["class"],
}
CONSTRUCT = {
    **RULE,
    "id": "NO-GETATTR",
    "kind": "forbidden_construct",
    "source": "app",
    "constructs": ["getattr"],
}
DEMO = ROOT / "fixtures/python-newer-syntax-demo"


def unused(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [gap for gap in result["gaps"] if gap["kind"] == "unused_allowance"]


def run(
    release_core: Path, tmp_path: Path, rule: dict[str, Any], files: Mapping[str, str | bytes]
) -> Any:
    return verdict(release_core, project(tmp_path, files, contract_rules=[rule]))


def test_an_entry_that_matches_nothing_is_one_named_gap(release_core: Path, tmp_path: Path) -> None:
    rule = {**FORBID, "allowed_sources": ["app.does_not_exist"]}
    root = project(tmp_path, IMPORTS, contract_rules=[rule])
    result = verdict(release_core, root)
    (gap,) = unused(result)
    assert 'FORBID allowed_sources "app.does_not_exist"' in gap["subject"], gap
    assert "/rules/0/allowed_sources/0" in gap["subject"], gap
    # The contract is stale, not the code: the rule still finds the forbidden import.
    assert rows(result)["FORBID"] == "FAIL", result
    text = command(release_core, root, "--text").stdout
    assert 'FORBID allowed_sources "app.does_not_exist"' in text, text
    assert "an exception of a rule that matches nothing" in text, text


def test_a_stale_entry_in_a_clean_run_is_unknown_and_not_fail(
    release_core: Path, tmp_path: Path
) -> None:
    rule = {**FORBID, "allowed_sources": ["app.does_not_exist"]}
    result = run(release_core, tmp_path, rule, BASE)
    assert len(unused(result)) == 1, result["gaps"]
    assert (result["status"], result["exit_code"]) == ("UNKNOWN", 2), result


def test_an_entry_that_matches_a_real_import_is_no_defect(
    release_core: Path, tmp_path: Path
) -> None:
    rule = {**FORBID, "allowed_sources": ["app.client"]}
    result = run(release_core, tmp_path, rule, IMPORTS)
    assert unused(result) == [], result["gaps"]
    assert rows(result)["FORBID"] == "PASS", result


def test_a_real_module_without_the_import_is_a_defect(release_core: Path, tmp_path: Path) -> None:
    # `app.client` exists, but it no longer imports the target: the entry protects nothing.
    rule = {**FORBID, "allowed_sources": ["app.client"]}
    (gap,) = unused(run(release_core, tmp_path, rule, BASE))
    assert 'FORBID allowed_sources "app.client"' in gap["subject"], gap


@pytest.mark.parametrize(
    ("field", "entry", "files", "expected"),
    [
        ("allowed_sources", "app", {"src/app/client.py": "import requests\n"}, 0),
        ("allowed_sources", "app.other", {"src/app/client.py": "import requests\n"}, 1),
        ("exact_sources", "app.client", {"src/app/client.py": "import requests\n"}, 0),
        ("exact_sources", "app.client", {"src/app/client.py": "import os\n"}, 1),
    ],
)
def test_external_dependency_scope_checks_both_entry_fields(
    release_core: Path, tmp_path: Path, field: str, entry: str, files: dict[str, str], expected: int
) -> None:
    rule = {**EXTERNAL, field: [entry]}
    found = unused(run(release_core, tmp_path, rule, {**BASE, **files}))
    assert len(found) == expected, found
    assert all(f'EXTERNAL {field} "{entry}"' in gap["subject"] for gap in found), found


@pytest.mark.parametrize(
    ("field", "entry", "expected"),
    [
        ("allowed_sources", "app.service", 0),
        ("allowed_sources", "app.nowhere", 1),
        ("exact_sources", "app.service", 0),
        ("exact_sources", "app.nowhere", 1),
    ],
)
def test_symbol_placement_checks_both_entry_fields(
    release_core: Path, tmp_path: Path, field: str, entry: str, expected: int
) -> None:
    files = {**BASE, "src/app/service.py": "class Allowed: pass\n"}
    found = unused(run(release_core, tmp_path, {**PLACEMENT, field: [entry]}, files))
    assert len(found) == expected, found
    assert all(f'PLACEMENT {field} "{entry}"' in gap["subject"] for gap in found), found


@pytest.mark.parametrize(
    ("field", "entry", "expected"),
    [
        ("allowed_sources", "app.client", 0),
        ("allowed_sources", "app.nowhere", 1),
        ("exact_sources", "app.client", 0),
        ("exact_sources", "app.nowhere", 1),
    ],
)
def test_forbidden_construct_checks_both_entry_fields(
    release_core: Path, tmp_path: Path, field: str, entry: str, expected: int
) -> None:
    files = {**BASE, "src/app/client.py": "VALUE = getattr(object, 'x')\n"}
    found = unused(run(release_core, tmp_path, {**CONSTRUCT, field: [entry]}, files))
    assert len(found) == expected, found
    assert all(f'NO-GETATTR {field} "{entry}"' in gap["subject"] for gap in found), found


def test_call_owner_reports_an_entry_that_no_call_uses_and_accepts_one_that_does(
    release_core: Path,
) -> None:
    # The fixture lets `sample.maintenance` purge, and `sweep` there makes the call.
    assert unused(verdict(release_core, DEMO)) == []
    with fixture_tree(DEMO) as root:
        path = root / "docs/architecture/architecture-contract.json"
        contract = json.loads(path.read_text())
        rule = next(
            rule for rule in contract["rules"] if rule["id"] == "CALL-PURGE-MAINTENANCE-ONLY"
        )
        rule["allowed_sources"].append("sample.gone")
        path.write_text(json.dumps(contract))
        (gap,) = unused(verdict(release_core, root))
        assert 'CALL-PURGE-MAINTENANCE-ONLY allowed_sources "sample.gone"' in gap["subject"], gap


def test_a_reviewed_type_ignore_that_no_written_ignore_matches_is_a_defect(
    release_core: Path,
) -> None:
    with fixture_tree(DEMO) as root:
        path = root / "docs/architecture/architecture-contract.json"
        contract = json.loads(path.read_text())
        rule = next(
            rule for rule in contract["rules"] if rule["id"] == "CONSTRUCT-EXACT-TYPE-IGNORE"
        )
        assert unused(verdict(release_core, root)) == []
        rule["allowed_type_ignores"][0]["statement"] = "handle.gone()"
        path.write_text(json.dumps(contract))
        (gap,) = unused(verdict(release_core, root))
        assert "CONSTRUCT-EXACT-TYPE-IGNORE allowed_type_ignores" in gap["subject"], gap


@pytest.mark.parametrize(
    ("field", "entry", "expected"),
    [
        ("allowed_sources", "app.api", 0),
        ("allowed_sources", "app.nowhere", 1),
        ("exact_sources", "app.api", 0),
        ("exact_sources", "app.nowhere", 1),
    ],
)
def test_boundary_types_checks_both_entry_fields(
    release_core: Path, tmp_path: Path, field: str, entry: str, expected: int
) -> None:
    root = boundary_project(tmp_path, PLANTS["primitives"])
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"][0][field] = [entry]
    path.write_text(json.dumps(contract))
    found = unused(verdict(release_core, root))
    assert len(found) == expected, found
    assert all(f'API-TYPES {field} "{entry}"' in gap["subject"] for gap in found), found


def test_placement_keeps_the_entry_of_a_module_with_an_unread_class(
    release_core: Path, tmp_path: Path
) -> None:
    # The collector reads no decorated class, so `app.service` can hold the class that the entry names.
    rule = {**PLACEMENT, "class_kinds": ["class", "dataclass"], "allowed_sources": ["app.service"]}
    files = {
        **BASE,
        "src/app/client.py": "class Plain: pass\n",
        "src/app/service.py": "from dataclasses import dataclass\n\n@dataclass\nclass Data: pass\n",
    }
    assert unused(run(release_core, tmp_path, rule, files)) == []


def test_call_owner_keeps_the_entries_while_a_call_has_no_exact_target(
    release_core: Path, tmp_path: Path
) -> None:
    # `purge` in `app.client` is a parameter, so its call has no exact target and can be the one.
    rule = {
        **RULE,
        "id": "CALL-PURGE",
        "kind": "call_owner",
        "source": "app",
        "target": "app.service.purge",
        "allowed_sources": ["app.service", "app.client"],
    }
    files = {
        **BASE,
        "src/app/service.py": "def purge(): pass\n\ndef run():\n    purge()\n",
        "src/app/client.py": "def run(purge):\n    purge()\n",
    }
    assert unused(run(release_core, tmp_path, rule, files)) == []
