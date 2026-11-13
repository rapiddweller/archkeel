# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual component-pair permissions use their single nominal value owner."""

import copy
import json
from dataclasses import FrozenInstanceError, asdict
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.ir.architecture_projection import PermissionProjection, PermissionStatus

ROOT = Path(__file__).parents[1]
OWNER = "archkeel.ir.architecture_projection"
SPEC = "docs/superpowers/specs/2026-10-17-permission-status-types.md"
GUARD = "TARGET-PERMISSION-TYPED-CONTROL"


@pytest.mark.parametrize("value", ["allowed", "forbidden", "undecided"])
def test_existing_permission_constructor_normalizes_known_values(value):
    row = PermissionProjection("allowed", value, ("undecided",), "forbidden")
    assert isinstance(row.status, StrEnum) and type(row.status) is PermissionStatus
    assert row.status.value == value
    assert row.target_id == "allowed" and row.rule_ids == ("undecided",)
    assert row.reason == "forbidden"
    assert json.dumps(asdict(row), separators=(",", ":")) == json.dumps(
        {"target_id": "allowed", "status": value, "rule_ids": ["undecided"], "reason": "forbidden"},
        separators=(",", ":"),
    )
    assert PermissionProjection("next", row.status, (), "why").status is row.status
    with pytest.raises(FrozenInstanceError):
        row.status = row.status


@pytest.mark.parametrize("value", ["unsupported", "PASS", 0, None])
def test_existing_permission_constructor_rejects_unknown_states(value):
    with pytest.raises(ValueError):
        PermissionProjection("target", value, (), "reason")


def test_permission_vocabulary_has_exact_existing_wire_values():
    assert isinstance(PermissionStatus, type) and issubclass(PermissionStatus, StrEnum)
    assert [(row.name, row.value) for row in PermissionStatus] == [
        ("ALLOWED", "allowed"),
        ("FORBIDDEN", "forbidden"),
        ("UNDECIDED", "undecided"),
    ]


def _native_repository(tmp_path):
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    component = copy.deepcopy(
        next(row for row in contract["components"] if row["id"] == "TARGET-ARCHITECTURE")
    )
    component.update(
        packages=[],
        exact_modules=[OWNER],
        requires=[],
        public=[OWNER + ":PermissionProjection", OWNER + ":PermissionStatus"],
        provenance=[SPEC],
    )
    intent = {
        "schema_version": contract["schema_version"],
        "components": [component],
        "declarations": {
            "uml": {
                "schema_version": "1.2.0",
                "entities": [
                    row
                    for row in contract["declarations"]["uml"]["entities"]
                    if row["id"].startswith("IR-PERMISSION-")
                ],
                "relationships": [],
                "scopes": [],
            }
        },
        "rules": [row for row in contract["rules"] if row["id"] == GUARD],
    }
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/architecture_projection.py": (
                ROOT / "src/archkeel/ir/architecture_projection.py"
            ).read_text(),
            SPEC: (ROOT / SPEC).read_text(),
            "contract.json": json.dumps(intent),
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)
