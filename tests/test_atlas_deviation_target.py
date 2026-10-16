# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent authored intent checks the actual deviation value owner."""

import copy

import pytest
import json
from pathlib import Path

from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
OWNER = "archkeel.render.atlas_deviations"
GUARD = "RENDER-DEVIATION-TYPED-CONTROL"
SPEC = "docs/superpowers/specs/2026-10-16-atlas-deviation-boundary.md"


def _contract(*, include_guard=False):
    render = json.loads((ROOT / "docs/architecture/contracts/render.json").read_text())
    component = copy.deepcopy(
        next(row for row in render["components"] if row["label"] == "atlas-payload")
    )
    component["exact_modules"] = [OWNER]
    component["public"] = [port for port in component["public"] if port.startswith(OWNER + ":")]
    component["provenance"] = [SPEC]
    return {
        "schema_version": render["schema_version"],
        "components": [component],
        "declarations": {
            "uml": {
                "schema_version": "1.2.0",
                "entities": [
                    row
                    for row in render["declarations"]["uml"]["entities"]
                    if row["id"].startswith("RENDER-DEVIATION-")
                ],
                "relationships": [],
                "scopes": [],
            }
        },
        "rules": [row for row in render["rules"] if include_guard and row["id"] == GUARD],
    }


def _repository(tmp_path, *, include_guard=False):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/render/__init__.py": "",
        "contract.json": json.dumps(_contract(include_guard=include_guard)),
        SPEC: (ROOT / SPEC).read_text(),
    }
    owner = ROOT / "src/archkeel/render/atlas_deviations.py"
    if owner.is_file():
        files["archkeel/render/atlas_deviations.py"] = owner.read_text()
    else:
        files["archkeel/render/atlas.py"] = (ROOT / "src/archkeel/render/atlas.py").read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_deviation_owner_fulfills_fixed_types(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(model)


def test_actual_deviation_owner_whole_module_guard_is_proven(tmp_path):
    assert (ROOT / "src/archkeel/render/atlas_deviations.py").is_file(), "The actual owner is absent"
    root, config = _repository(tmp_path, include_guard=True)
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven, guard
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("kind: AtlasDeviationKind", "kind: str"),
        (") -> tuple[AtlasDeviation, ...]:", ") -> tuple[str, ...]:"),
    ],
    ids=["actual-kind-field", "actual-producer-return"],
)
def test_actual_deviation_type_widening_fails_fixed_native_intent(tmp_path, before, after):
    root, config = _repository(tmp_path)
    original = _model(root, config)
    assert architecture_report(original).comparison.status == "PASS"
    intent = (root / "contract.json").read_bytes()
    path = root / "archkeel/render/atlas_deviations.py"
    source = path.read_text()
    assert source.count(before) == 1
    path.write_text(source.replace(before, after, 1))
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and any(row.status == "FAIL" for row in comparison.assessments)
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "control",
    [
        '        if self.kind == "undeclared":\n            pass\n',
        '        if self.kind in ("undeclared", "allowed_unused"):\n            pass\n',
        '        marker = "undeclared"\n        if self.kind == marker:\n            pass\n',
        '        match self.kind:\n            case "undeclared":\n                pass\n',
    ],
    ids=["equality", "membership", "local-alias", "match"],
)
def test_real_deviation_constructor_raw_control_fails_native_guard(tmp_path, control):
    root, config = _repository(tmp_path, include_guard=True)
    intent = (root / "contract.json").read_bytes()
    path = root / "archkeel/render/atlas_deviations.py"
    source = path.read_text()
    marker = "    def __post_init__(self) -> None:\n"
    assert source.count(marker) == 1
    path.write_text(source.replace(marker, marker + control, 1))
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent
