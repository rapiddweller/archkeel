# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An authored Badge boundary constrains real source and cannot bless a widening."""

import ast
import copy
import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARD = "RENDER-BADGE-TYPED-CONTROL"


def _badge_contract():
    render = json.loads((ROOT / "docs/architecture/contracts/render.json").read_text())
    component = copy.deepcopy(
        next(row for row in render["components"] if row["label"] == "summary")
    )
    component["exact_modules"] = ["archkeel.render.summary_badges"]
    component["provenance"] = ["docs/architecture/summary-badges.md"]
    component["public"] = [
        port for port in component["public"] if port.startswith("archkeel.render.summary_badges:")
    ]
    return {
        "schema_version": render["schema_version"],
        "components": [component],
        "declarations": {
            "uml": {
                "schema_version": "1.2.0",
                "entities": [
                    row
                    for row in render["declarations"]["uml"]["entities"]
                    if row["id"].startswith("RENDER-BADGE-")
                ],
                "relationships": [],
                "scopes": [],
            }
        },
        "rules": [row for row in render["rules"] if row["id"] == GUARD],
    }


def _badge_repository(tmp_path):
    source_root = ROOT / "src/archkeel"
    graph = (source_root / "ir/architecture_graph.py").read_text()
    assessment = next(
        node
        for node in ast.parse(graph).body
        if isinstance(node, ast.ClassDef) and node.name == "AssessmentStatus"
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/render/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/architecture_graph.py": "from enum import StrEnum\n\n"
        + ast.get_source_segment(graph, assessment),
        "contract.json": json.dumps(_badge_contract()),
        "docs/architecture/summary-badges.md": (
            ROOT / "docs/architecture/summary-badges.md"
        ).read_text(),
    }
    source = source_root / "render/summary_badges.py"
    if source.is_file():
        files["archkeel/render/summary_badges.py"] = source.read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _guard(model, rule_id=GUARD):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == rule_id)


def test_actual_badge_source_fulfills_authored_types_and_complete_module_guard(tmp_path):
    root, config = _badge_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("state: BadgeState", "state: str"),
        ("def badge(value: str) -> Badge:", "def badge(value: str) -> str:"),
    ],
    ids=["actual-state-field", "actual-factory-return"],
)
def test_badge_source_widening_fails_without_changing_authored_target(tmp_path, old, new):
    root, config = _badge_repository(tmp_path)
    intent = (root / "contract.json").read_bytes()
    source = root / "archkeel/render/summary_badges.py"
    assert old in source.read_text()
    source.write_text(source.read_text().replace(old, new, 1))
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and any(row.status == "FAIL" for row in comparison.assessments)
    target_rule = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target_rule.status == "FAIL"
    assert any(target_rule.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    ("prefix", "replacement"),
    [
        ("", 'value == "PASS"'),
        ("", 'value in ("PASS", "FAIL")'),
        ("", '"PASS" in value'),
        ('from typing import Final\n_PASS: Final[str] = "PASS"\n', "value == _PASS"),
        ("", "value == local_status"),
    ],
    ids=["equality", "membership", "literal-needle", "final-alias", "local-alias"],
)
def test_badge_real_control_mutation_fails_native_guard_with_target_unchanged(
    tmp_path, prefix, replacement
):
    root, config = _badge_repository(tmp_path)
    intent = (root / "contract.json").read_bytes()
    source = root / "archkeel/render/summary_badges.py"
    content = source.read_text()
    assert "status is AssessmentStatus.PASS" in content
    if replacement == "value == local_status":
        content = content.replace(
            "    if status is AssessmentStatus.PASS:",
            '    local_status = "PASS"\n    if status is AssessmentStatus.PASS:',
            1,
        )
    content = content.replace("status is AssessmentStatus.PASS", replacement, 1)
    source.write_text(content + "\n" + prefix)
    model = _model(root, config)
    assert _guard(model).status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


def test_badge_real_match_control_fails_native_guard_with_target_unchanged(tmp_path):
    root, config = _badge_repository(tmp_path)
    intent = (root / "contract.json").read_bytes()
    source = root / "archkeel/render/summary_badges.py"
    old = (
        "    if status is AssessmentStatus.PASS:\n"
        '        return Badge(BadgeState.PASS, "✓", "PASS")'
    )
    new = (
        '    match value:\n        case "PASS":\n'
        '            return Badge(BadgeState.PASS, "✓", "PASS")'
    )
    assert old in source.read_text()
    source.write_text(source.read_text().replace(old, new, 1))
    model = _model(root, config)
    assert _guard(model).status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


def test_badge_guard_accepts_nominal_controls_and_arbitrary_data_comparison(tmp_path):
    root, config = _badge_repository(tmp_path)
    source = root / "archkeel/render/summary_badges.py"
    source.write_text(
        source.read_text() + "\n\ndef _display_probe(value: BadgeState) -> bool:\n"
        "    return value is BadgeState.INFO\n"
        "\n\ndef _data_probe(actual: str, expected: str) -> bool:\n"
        "    return actual == expected\n"
    )
    model = _model(root, config)
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not any(GUARD in row.rule_ids for row in trace_valid_violations(model))


def test_own_badge_guard_is_scoped_to_the_real_complete_badge_module(self_observation):
    own_guard = _guard(self_observation, "render:" + GUARD)
    assert own_guard.status == "PASS" and own_guard.evaluation_proven, own_guard
    contract_guard = _badge_contract()["rules"][0]
    assert contract_guard["source"] == "archkeel.render.summary_badges"
    assert not contract_guard.get("exact_sources") and not contract_guard.get("allowed_sources")


def test_own_badge_target_pins_actual_state_and_factory(self_observation):
    comparison = architecture_report(self_observation).comparison
    assert comparison is not None
    for name, aspect in (("Badge.state", "annotation"), ("badge", "signature")):
        target_id = "render:RENDER-BADGE-" + name
        assert any(
            row.subject_id == target_id and row.aspect == aspect and row.status == "PASS"
            for row in comparison.assessments
        ), (target_id, aspect)
