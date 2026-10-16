# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The actual predicate decoder satisfies fixed native type and dispatch intent."""

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
SOURCE = "src/archkeel/analyzer/python/constructs.py"
GUARD = "TARGET-PYTHON-PREDICATE-TYPED-CONTROL"


def _repository(tmp_path, changed=None):
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    )
    contract.pop("$schema", None)
    source = (ROOT / SOURCE).read_text() if changed is None else changed
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/analyzer/__init__.py": "",
            "archkeel/analyzer/python/__init__.py": "",
            "archkeel/analyzer/python/constructs.py": source,
            "contract.json": json.dumps(contract),
            "docs/architecture/language-adapter-target.md": (
                ROOT / "docs/architecture/language-adapter-target.md"
            ).read_text(),
            "docs/architecture/python-string-predicates.md": (
                ROOT / "docs/architecture/python-string-predicates.md"
            ).read_text(),
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_predicate_enum_and_decoder_satisfy_independent_native_target(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    target = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target.status == "PASS" and target.evaluation_proven
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("class _StringPredicate(Enum):", "class _StringPredicate:"),
        ("-> _StringPredicate | None:", "-> str | None:"),
    ],
    ids=["enum-kind", "nominal-return"],
)
def test_actual_decoder_type_widening_fails_fixed_native_target(tmp_path, old, new):
    source = (ROOT / SOURCE).read_text()
    assert old in source
    root, config = _repository(tmp_path, source.replace(old, new, 1))
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL", comparison
    target = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target.status == "FAIL"
    assert any(target.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "probe",
    [
        '    if node.func.attr == "startswith":\n        return None\n',
        '    if node.func.attr.startswith("start"):\n        return None\n',
    ],
    ids=["equality", "predicate"],
)
def test_actual_decoder_raw_dispatch_fails_fixed_native_guard(tmp_path, probe):
    source = (ROOT / SOURCE).read_text()
    marker = "    try:\n        return _StringPredicate(node.func.attr)"
    assert marker in source
    root, config = _repository(tmp_path, source.replace(marker, probe + marker, 1))
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL"
    assert any(guard.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent
