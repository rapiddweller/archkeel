# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested declaration fields must be evaluated or rejected, never silently ignored."""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics, run_validate
from archkeel.ir.codec import declaration_paths, parse_contract

_DECLARATIONS: dict[str, list[object]] = {
    "capabilities": [
        {
            "id": "CAP-ONE",
            "name": "one",
            "label": "One",
            "review_order": 1,
            "provenance": ["docs/sample.md"],
        }
    ],
    "review_scopes": [
        {
            "id": "SCOPE-ONE",
            "label": "One",
            "parent_id": "app",
            "subjects": ["sample"],
            "provenance": ["docs/sample.md"],
        }
    ],
    "public_api": ["sample.api:run"],
    "public_api_provenance": ["docs/sample.md"],
    "public_commands": [
        {
            "id": "CMD-ONE",
            "command": "archkeel report",
            "description": "Report.",
            "provenance": ["docs/sample.md"],
        }
    ],
    "context_roots": ["sample"],
    "context_roots_provenance": ["docs/sample.md"],
    "paths": [
        {
            "id": "PATH-ONE",
            "label": "One",
            "kind": "read",
            "steps": ["sample"],
            "provenance": ["docs/sample.md"],
        }
    ],
    "spot_owners": [
        {
            "id": "OWNER-ONE",
            "label": "One",
            "owner": "team",
            "responsibility": "Own it.",
            "provenance": ["docs/sample.md"],
        }
    ],
    "compat": [{"module": "sample.old", "target": "sample.new", "lifetime": "permanent"}],
    "measurement_budgets": [{"name": "cycle_edges", "provenance": ["docs/sample.md"]}],
}


def _inside_contract(declarations: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": declarations,
    }


def _diagnostics(tmp_path: Path, declarations: dict[str, object]):
    root_contract = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-APP",
                "label": "app",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/sample.md"],
                "inside": "inside.json",
            }
        ],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(root_contract), encoding="utf-8")
    (tmp_path / "inside.json").write_text(
        json.dumps(_inside_contract(declarations)), encoding="utf-8"
    )
    return inside_diagnostics(
        tmp_path,
        parse_contract(root_contract),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
    )


def test_empty_nested_declaration_fields_remain_supported(tmp_path: Path) -> None:
    diagnostics = _diagnostics(tmp_path, dict.fromkeys(_DECLARATIONS, []))

    assert not diagnostics


@pytest.mark.parametrize("field", tuple(_DECLARATIONS))
def test_nonempty_nested_declaration_field_is_rejected(tmp_path: Path, field: str) -> None:
    diagnostics = _diagnostics(tmp_path, {field: _DECLARATIONS[field]})

    assert any(
        item.code == "contract.invalid" and field in item.unknown_claim for item in diagnostics
    )


def test_validate_fails_on_unmeasured_nested_declaration(tmp_path: Path) -> None:
    _diagnostics(tmp_path, {"public_api": ["sample.api:run"]})
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/sample.md").write_text("Inside contract evidence.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "arch@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Archkeel test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)

    result, _ = run_validate(
        tmp_path,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observe,
    )

    assert result.exit_code == 2
    assert any(
        "unsupported non-empty declarations: public_api" in diagnostic.unknown_claim
        for diagnostic in result.diagnostics
    ), result.diagnostics


def test_report_keeps_unsupported_nested_declaration_as_unknown(tmp_path: Path) -> None:
    _diagnostics(tmp_path, {"public_api": ["sample.api:run"]})
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )

    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )

    assert result.observation is not None
    failures = tuple(result.observation.records("unknowns") or ())
    assert any(
        item.kind == "inside_contract_incomplete"
        and "unsupported non-empty declarations: public_api" in item.title
        for item in failures
    )

    def read_contract(path: str) -> tuple[bytes, str]:
        return (tmp_path / path).read_bytes(), path

    with pytest.raises(ValueError, match="unsupported non-empty declarations: public_api"):
        declaration_paths(
            (tmp_path / "contract.json").read_bytes(),
            "contract.json",
            read_contract=read_contract,
        )
