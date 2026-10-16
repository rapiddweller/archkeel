# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own dependency policy rejects string dispatch in real source."""

import pytest
from test_dependency_api_target import ROOT, _dependency_contract, _dependency_repository
from test_uml_evaluation import _model

from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations

GUARD = "DEPENDENCY-TYPED-CONTROL"


def _guard(model):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "prefix"\n',
        'def _probe(value):\n    return value in ("prefix", "exact")\n',
        (
            'def _probe(value):\n    match value:\n        case "prefix":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nPREFIX: Final[str] = "prefix"\n'
            "\ndef _probe(value):\n    return value == PREFIX\n"
        ),
    ],
    ids=["equality", "membership", "match", "final-string"],
)
def test_native_dependency_policy_rejects_string_control(tmp_path, probe):
    source = (ROOT / "src/archkeel/ir/dependency.py").read_text()
    root, config = _dependency_repository(tmp_path, dependency_source=source + "\n" + probe)
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert _guard(model).status == "FAIL"
    violations = [row for row in trace_valid_violations(model) if GUARD in row.rule_ids]
    assert len(violations) == 1
    assert violations[0].data.get("construct") == "string_literal_compare"
    assert (root / "contract.json").read_bytes() == contract


def test_native_dependency_policy_accepts_owned_enums_and_name_data(tmp_path):
    source = (ROOT / "src/archkeel/ir/dependency.py").read_text()
    source += (
        "\ndef _enum_probe(value: SelectorMatch) -> bool:\n"
        "    return value is SelectorMatch.PREFIX\n"
        "\ndef _name_probe(module: str, target: str) -> bool:\n"
        "    return module == target\n"
    )
    root, config = _dependency_repository(tmp_path, dependency_source=source)
    model = _model(root, config)
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not [row for row in trace_valid_violations(model) if GUARD in row.rule_ids]


def test_native_wire_comparison_remains_at_the_codec_boundary(tmp_path):
    root, config = _dependency_repository(tmp_path)
    codec = root / "archkeel/ir/codec_contract.py"
    codec.write_text(
        codec.read_text()
        + '\n\ndef _wire_probe(kind: str) -> bool:\n    return kind == "forbidden_dependency"\n'
    )
    model = _model(root, config)
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert any(
        row.kind == "string_literal_compare"
        and row.data.get("owner") == "archkeel.ir.codec_contract._wire_probe"
        for row in model.records("constructs")
    )
    assert not [row for row in trace_valid_violations(model) if GUARD in row.rule_ids]


def test_the_native_guard_comes_from_the_own_contract_without_exemptions():
    rule = next(row for row in _dependency_contract()["rules"] if row["id"] == GUARD)
    assert rule["source"] == "archkeel.ir.dependency"
    assert rule["constructs"] == ["string_literal_compare"]
    assert not rule.get("allowed_sources") and not rule.get("exact_sources")


def test_own_observation_covers_the_protected_domain_without_string_control(self_observation):
    model = self_observation
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not [
        row
        for row in model.records("constructs")
        if row.kind == "string_literal_compare"
        and (
            row.data.get("owner") == "archkeel.ir.dependency"
            or row.data.get("owner", "").startswith("archkeel.ir.dependency.")
        )
    ]
