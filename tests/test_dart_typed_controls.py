# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nominal Dart API intent and actual Python implementation control proofs."""

from __future__ import annotations

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.dart import parse, resolve, snapshot
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
FIELDS = (
    (parse.Parameter, "kind", "ParameterKind"),
    (parse.Member, "kind", "MemberKind"),
    (parse.Member, "visibility", "Visibility"),
    (parse.Definition, "kind", "DefinitionKind"),
    (parse.Definition, "visibility", "Visibility"),
    (parse.Directive, "kind", "DirectiveKind"),
    (parse.Site, "kind", "SiteKind"),
    (parse.Site, "use", "SiteUse"),
    (resolve.ResolvedSite, "status", "ResolutionStatus"),
    (resolve.ConstructionResolution, "status", "ResolutionStatus"),
    (resolve.ResolvedParameter, "kind", "ParameterKind"),
    (snapshot.Snapshot, "sdk_constraint_state", "RuntimeRequirementState"),
)
GUARDS = tuple(
    (f"DART-{name.upper()}-TYPED-CONTROL", f"archkeel.analyzer.dart.{name}")
    for name in ("parse", "resolve", "snapshot", "collect")
)


@pytest.mark.parametrize("owner,field,expected", FIELDS)
def test_dart_control_fields_have_owned_nominal_types(owner, field, expected):
    actual = get_type_hints(owner)[field]
    assert isinstance(actual, type) and issubclass(actual, StrEnum), (owner, field, actual)
    assert actual.__name__ == expected


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/dart.json").read_text()))
    contract.pop("$schema", None)
    contract["rules"] = [
        {
            "id": identifier,
            "kind": "forbidden_construct",
            "source": module,
            "constructs": ["string_literal_compare"],
            "rationale": "Closed Dart implementation controls have nominal owners.",
            "decided_by": "agent",
            "provenance": ["docs/architecture/dart-nominal-controls.md"],
        }
        for identifier, module in GUARDS
    ]
    fields = {
        f"{owner.__module__}.{owner.__name__}.{field}": expected
        for owner, field, expected in FIELDS
    }
    selected = set(fields)
    for name in fields:
        selected.add(name.rsplit(".", 1)[0])
        selected.add(name.rsplit(".", 2)[0])
    uml = contract["declarations"]["uml"]
    uml["entities"] = [
        entity for entity in uml["entities"] if entity["qualified_name"] in selected
    ]
    for entity in uml["entities"]:
        if entity["qualified_name"] in fields:
            entity["annotation"] = fields[entity["qualified_name"]]
    uml["relationships"] = []
    uml["scopes"] = []
    return contract


def _repository(tmp_path):
    paths = [
        *sorted((ROOT / "src/archkeel/analyzer/dart").glob("*.py")),
        ROOT / "src/archkeel/ir/facts.py",
        ROOT / "src/archkeel/ir/protocol.py",
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(_contract()),
        "docs/architecture/dart-nominal-controls.md": "Owned Dart control boundaries.\n",
    }
    for path in paths:
        files[path.relative_to(ROOT / "src").as_posix()] = path.read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_dart_control_api_matches_independent_nominal_target(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessments = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    for identifier, _ in GUARDS:
        assert assessments[identifier].status == "PASS" and assessments[identifier].evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "probe",
    [
        'def _control_probe(value):\n    return value == "import"\n',
        'def _control_probe(value):\n    return value in ("import", "export")\n',
        'def _control_probe(value):\n    return "import" in value\n',
        'def _control_probe(value):\n    match value:\n        case "import":\n            return True\n        case _:\n            return False\n',
        'from typing import Final\nCONTROL: Final[str] = "import"\ndef _control_probe(value):\n    return value == CONTROL\n',
    ],
    ids=["equality", "membership", "needle", "match", "final"],
)
def test_native_dart_control_guard_rejects_actual_source_string_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    path = root / "archkeel/analyzer/dart/parse.py"
    path.write_text(path.read_text() + "\n" + probe)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    probes = {
        row.id for row in model.records("constructs")
        if "_control_probe" in str(row.data.get("owner", ""))
        and row.data.get("construct") == "string_literal_compare"
    }
    assert probes
    assert any(probes.intersection(row.fact_ids) for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


def test_native_dart_nominal_annotation_widening_fails_without_target_change(tmp_path):
    root, config = _repository(tmp_path)
    path = root / "archkeel/analyzer/dart/parse.py"
    source = path.read_text()
    assert "kind: ParameterKind" in source
    path.write_text(source.replace("kind: ParameterKind", "kind: str", 1))
    before = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.aspect == "annotation" and row.status == "FAIL" for row in comparison.assessments
    )
    assert (root / "contract.json").read_bytes() == before
