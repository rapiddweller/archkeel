# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The actual predicate decoder satisfies fixed native nominal type intent."""

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


def _repository(tmp_path, changed=None):
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    )
    contract.pop("$schema", None)
    # This fixture copies only constructs.py; the complete self target retains every owner.
    predicate_ids = {
        "PYTHON-PREDICATE-MODULE",
        "PYTHON-PREDICATE-KIND",
        "PYTHON-PREDICATE-DECODE",
        "PYTHON-PREDICATE-QUERY",
    }
    uml = contract["declarations"]["uml"]
    uml["entities"] = [entity for entity in uml["entities"] if entity["id"] in predicate_ids]
    assert {entity["id"] for entity in uml["entities"]} == predicate_ids
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
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("class _StringPredicate(Enum):", "class _StringPredicate:"),
        ("-> _StringPredicate | None:", "-> str | None:"),
        (
            "def _predicate_matches(literals: _LiteralComparisons, node: ast.expr) -> bool:",
            "def _predicate_matches(literals: str, node: ast.expr) -> bool:",
        ),
        (
            "def _predicate_matches(literals: _LiteralComparisons, node: ast.expr) -> bool:",
            "def _predicate_matches(literals: _LiteralComparisons, node: ast.expr) -> str:",
        ),
    ],
    ids=["enum-kind", "nominal-return", "query-context", "query-result"],
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


def test_actual_query_raw_token_is_observed_without_claiming_a_function_guard(tmp_path):
    source = (ROOT / SOURCE).read_text()
    signature = "def _predicate_matches(literals: _LiteralComparisons, node: ast.expr) -> bool:\n"
    assert source.count(signature) == 1
    changed = source.replace(signature, signature + '    if node == "raw_protocol":\n        return False\n', 1)
    root, config = _repository(tmp_path, changed)
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    records = [
        row
        for row in model.records("constructs")
        if row.kind == "string_literal_compare"
        and row.data.get("owner") == "archkeel.analyzer.python.constructs._predicate_matches"
    ]
    assert len(records) == 1 and records[0].data.get("form") == "compare"
    evidence = {row.id: row for row in model.evidence}
    [site] = [evidence[identity] for identity in records[0].evidence_ids]
    assert (site.line, site.excerpt) == (
        source[: source.index(signature)].count("\n") + 2,
        '    if node == "raw_protocol":',
    )
    assert (root / "contract.json").read_bytes() == intent
