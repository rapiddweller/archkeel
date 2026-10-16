# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Graph controls retain wire grammar and independent native type evidence."""

import copy
import json
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import architecture_graph as graph
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.graph_codec import graph_bytes, parse_comparison, parse_graph, parse_report
from archkeel.ir.model import RuleVerdict
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations
from tools.architecture_graph_schema import comparison_schema, graph_schema, report_schema

ROOT = Path(__file__).parents[1]
VOCABULARIES = (
    "EntityKind", "GraphSchemaVersion", "RelationshipKind", "VisibilityKind",
    "VisibilityBasis", "ParameterKind", "ModifierKind", "DefinitionContextKind",
    "DefinitionBranchKind", "CoverageStatus", "OriginKind", "PresenceKind",
    "ResolutionKind", "CompletenessMode", "AssessmentStatus",
    "RuleAssessmentStatus", "AssessmentAspect", "AssessmentChange",
)
MODULES = (
    "archkeel.ir.architecture_graph", "archkeel.ir.graph_codec",
    "archkeel.ir.target_graph", "archkeel.check.uml_compare",
)


@pytest.mark.parametrize("name", VOCABULARIES)
def test_graph_control_vocabulary_is_nominal_and_owned(name):
    control = getattr(graph, name)
    assert isinstance(control, type) and issubclass(control, StrEnum), (name, control)


def test_shared_rule_verdict_has_one_owner_and_declared_status_stays_distinct():
    assert RuleVerdict is graph.AssessmentStatus
    assert graph.RuleAssessmentStatus is not graph.AssessmentStatus
    assert isinstance(graph.AssessmentStatus.PASS, StrEnum)
    assert graph.RuleAssessmentStatus.DECLARATION.value == "DECLARATION"


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0"])
def test_graph_parser_converts_closed_values_once_and_preserves_legacy_bytes(version):
    raw = {"origin": "declared", "schema_version": version, "entities": [{
        "id": "module", "kind": "module", "qualified_name": "sample",
        "language": "future-language", "presence": "planned",
        "responsibilities": ["Own the sample module."], "provenance": ["target.md"],
    }]}
    value = parse_graph(raw)
    assert isinstance(value.origin, StrEnum)
    assert isinstance(value.schema_version, StrEnum)
    entity = value.entities[0]
    assert isinstance(entity.kind, StrEnum) and isinstance(entity.presence, StrEnum)
    assert entity.language == "future-language"
    encoded = graph_bytes(value)
    assert parse_graph(json.loads(encoded)) == value
    assert json.loads(encoded)["entities"][0]["kind"] == "module"
    assert json.loads(encoded)["schema_version"] == version


def test_legacy_direct_construction_normalizes_to_nominal_graph_controls():
    entity = graph.Entity("m", "module", "sample", "python", provenance=("target.md",))
    value = graph.ArchitectureGraph("declared", (entity,))
    assert isinstance(entity.kind, StrEnum)
    assert isinstance(value.origin, StrEnum)
    value.validate()
    item = graph.GraphAssessment("a", "m", "existence", "UNKNOWN", "unavailable", "No proof.")
    comparison = graph.GraphComparison.from_assessments((item,))
    assert isinstance(item.status, StrEnum)
    assert comparison.status is graph.AssessmentStatus.UNKNOWN


def test_graph_codecs_keep_comparison_and_report_version_boundaries():
    comparison = parse_comparison({"status": "UNKNOWN", "schema_version": "1.0.0"})
    assert comparison.status is graph.AssessmentStatus.UNKNOWN
    for version in ("1.0.0", "1.2.0"):
        report = parse_report({
            "observed": None, "target": None, "unavailable": "No source.",
            "schema_version": version,
        })
        assert isinstance(report.schema_version, StrEnum)
    for version in ("1.1.0", "future", None):
        with pytest.raises(ValueError, match="report schema_version"):
            parse_report({
                "observed": None, "target": None, "unavailable": "No source.",
                "schema_version": version,
            })


@pytest.mark.parametrize("factory,path", [
    (graph_schema, "schema/architecture-graph.schema.json"),
    (comparison_schema, "schema/architecture-comparison.schema.json"),
    (report_schema, "schema/architecture-report.schema.json"),
])
def test_nominal_graph_control_types_preserve_historical_schema(factory, path):
    assert factory() == json.loads((ROOT / path).read_text())


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        item for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith("IR-GRAPH-")
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        item for item in root["rules"] if item.get("source") in MODULES
        and item["kind"] == "forbidden_construct"
    ]
    contract["components"].append({
        "id": "GRAPH-CHECK", "label": "graph-check", "role": "component",
        "packages": ["archkeel.check"], "public": ["archkeel.check.uml_compare"],
        "responsibilities": ["Compare independent graph intent with observed proof."],
        "forbidden_responsibilities": [], "provenance": ["docs/architecture/typed-graph-vocabulary.md"],
    })
    return contract


def _repository(tmp_path):
    facts = (
        "from __future__ import annotations\nimport hashlib\nfrom dataclasses import dataclass\n"
        "from enum import StrEnum\nfrom typing import Literal, TypeAlias\n\n"
        + _source_members("src/archkeel/ir/facts.py", {"Evidence", "Language", "stable_id"})
    )
    model = (
        "from __future__ import annotations\nfrom collections.abc import Mapping, Sequence\n"
        "from typing import TypeAlias\nfrom .facts import stable_id\n\n"
        + _source_members("src/archkeel/ir/model.py", {"RawJson"})
    )
    files = {
        "archkeel/__init__.py": "", "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/ir/facts.py": facts, "archkeel/ir/model.py": model,
        "contract.json": json.dumps(_contract()),
        "docs/architecture/typed-graph-vocabulary.md": "Owned graph intent.\n",
    }
    for module in MODULES:
        path = module.replace(".", "/") + ".py"
        files[path] = (ROOT / "src" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None
    return comparison


def test_native_graph_api_matches_independent_intent_and_all_migrated_module_guards(tmp_path):
    root, config = _repository(tmp_path)
    assert _contract()["declarations"]["uml"]["entities"]
    value = _model(root, config)
    assert _comparison(value).status == "PASS", _comparison(value)
    assessments = {row.id: row for row in rule_assessments(value, undecided_by_rule={})}
    for module in MODULES:
        guard = next(item for item in _contract()["rules"] if item["source"] == module)
        assert assessments[guard["id"]].status == "PASS"
        assert assessments[guard["id"]].evaluation_proven
    assert not trace_valid_violations(value)


@pytest.mark.parametrize("old,new", [
    ("status: AssessmentStatus", "status: str"),
    (") -> GraphComparison:", ") -> str:"),
])
def test_native_graph_enum_field_and_return_widening_fail_with_fixed_target(tmp_path, old, new):
    root, config = _repository(tmp_path)
    path = root / "archkeel/ir/architecture_graph.py"
    assert old in path.read_text()
    contract = (root / "contract.json").read_bytes()
    path.write_text(path.read_text().replace(old, new, 1))
    value = _model(root, config)
    assert any(
        row.status == "FAIL" for row in _comparison(value).assessments
        if row.aspect in {"annotation", "signature"}
    )
    assert trace_valid_violations(value)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize("probe", [
    'def _probe(value):\n    return value == "declared"\n',
    'def _probe(value):\n    return value in ("declared", "observed")\n',
    ('def _probe(value):\n    match value:\n        case "declared":\n'
     "            return True\n        case _:\n            return False\n"),
    ('from typing import Final\nDECLARED: Final[str] = "declared"\n'
     "\ndef _probe(value):\n    return value == DECLARED\n"),
], ids=["equality", "membership", "match", "final-string"])
def test_native_graph_parser_has_no_string_control_exception(tmp_path, probe):
    root, config = _repository(tmp_path)
    path = root / "archkeel/ir/graph_codec.py"
    path.write_text(path.read_text() + "\n" + probe)
    value = _model(root, config)
    guard = next(item for item in _contract()["rules"]
                 if item["source"] == "archkeel.ir.graph_codec")
    assert any(guard["id"] in row.rule_ids for row in trace_valid_violations(value))
