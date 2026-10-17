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
from test_architecture_projection import _repository as _projection_repository
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_projection import PermissionProjection, PermissionStatus
from archkeel.ir.codec import decode_canonical_model, parse_observation, result_bytes
from archkeel.ir.command_view import architecture_command_envelope
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.atlas import atlas_payload

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


@pytest.mark.parametrize("closed", [False, True])
def test_real_permission_producer_preserves_states_wire_and_atlas_balance(tmp_path, closed):
    root, config = _projection_repository(tmp_path, closed=closed)
    result, architecture = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert architecture is not None and result.architecture_projection is not None
    view = result.architecture_projection
    core = next(row for row in view.components if row.id == "CORE")
    assert all(type(row.status) is PermissionStatus for row in core.permissions)
    expected = {
        "IDLE": "forbidden" if closed else "undecided",
        "OTHER": "forbidden",
        "STORE": "allowed",
    }
    assert {row.target_id: row.status.value for row in core.permissions} == expected
    envelope = architecture_command_envelope(result)
    grouped = next(row for row in envelope.architecture_projection.components if row.id == "CORE")
    assert all(type(row.status) is PermissionStatus for row in grouped.permissions)
    encoded = json.loads(result_bytes(result))
    wire_core = next(
        row for row in encoded["architecture_projection"]["components"] if row["id"] == "CORE"
    )
    assert {target: row["status"] for row in wire_core["permissions"] for target in row["target_ids"]} == expected
    assert all(type(row["status"]) is str for row in wire_core["permissions"])
    model = parse_observation(decode_canonical_model(json.loads(architecture)))
    payload = atlas_payload(
        model,
        architecture_report(model),
        view,
        result,
        repository="same fixture",
        architecture_href="architecture.json",
    )
    top = next(row for row in view.levels if row.parent_id is None)
    assert payload["balance"] == {
        "declared": top.declared,
        "used": top.used,
        "allowed_unused": top.unused,
        "undeclared": top.undeclared,
    }
    assert core.status == ("FAIL" if closed else "UNKNOWN")


def _native_repository(tmp_path):
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    component = copy.deepcopy(
        next(row for row in contract["components"] if row["id"] == "TARGET-GOVERNANCE")
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


def test_actual_permission_owner_fulfills_independent_native_intent(tmp_path):
    root, config = _native_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(model)


def test_whole_permission_value_owner_has_native_control_receipt(tmp_path):
    root, config = _native_repository(tmp_path)
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven, guard


def test_actual_permission_field_widening_fails_fixed_native_intent(tmp_path):
    root, config = _native_repository(tmp_path)
    assert architecture_report(_model(root, config)).comparison.status == "PASS"
    intent = (root / "contract.json").read_bytes()
    path = root / "archkeel/ir/architecture_projection.py"
    source = path.read_text()
    assert source.count("status: PermissionStatus") == 1
    path.write_text(source.replace("status: PermissionStatus", "status: str", 1))
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and any(row.status == "FAIL" for row in comparison.assessments)
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "control",
    [
        '        if self.status == "allowed":\n            pass\n',
        '        if self.status in ("allowed", "forbidden"):\n            pass\n',
        '        marker = "allowed"\n        if self.status == marker:\n            pass\n',
        '        match self.status:\n            case "allowed":\n                pass\n',
    ],
    ids=["equality", "membership", "local-alias", "match"],
)
def test_real_permission_constructor_raw_control_fails_native_guard(tmp_path, control):
    root, config = _native_repository(tmp_path)
    intent = (root / "contract.json").read_bytes()
    path = root / "archkeel/ir/architecture_projection.py"
    source = path.read_text()
    marker = "    def __post_init__(self) -> None:\n"
    assert source.count(marker) == 1
    path.write_text(source.replace(marker, marker + control, 1))
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent
