# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested declaration fields must be evaluated or rejected, never silently ignored."""

import json
from pathlib import Path

import pytest

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics
from archkeel.ir.codec import parse_contract

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


def test_validate_checks_nested_contract_provenance_files(tmp_path: Path) -> None:
    _diagnostics(tmp_path, {})
    child = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-CHILD",
                "label": "child",
                "role": "component",
                "packages": ["sample.child"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/absent.md"],
            }
        ],
        "rules": [],
    }
    (tmp_path / "inside.json").write_text(json.dumps(child), encoding="utf-8")

    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_text())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
    )

    assert any(
        item.code == "reference.provenance" and item.subject == "docs/absent.md"
        for item in diagnostics
    )
