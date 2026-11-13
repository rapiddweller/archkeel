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

from archkeel.check.ports import ScanConfig
from archkeel.ir import architecture_graph as graph
from archkeel.ir.graph_codec import (
    graph_bytes,
    parse_comparison,
    parse_component_intent,
    parse_graph,
    parse_report,
)
from archkeel.ir.model import RuleVerdict, Verdict
from archkeel.ir.report_graph import architecture_report
from tools.architecture_graph_schema import comparison_schema, graph_schema, report_schema

ROOT = Path(__file__).parents[1]
VOCABULARIES = (
    "EntityKind",
    "GraphSchemaVersion",
    "RelationshipKind",
    "VisibilityKind",
    "VisibilityBasis",
    "ParameterKind",
    "ModifierKind",
    "DefinitionContextKind",
    "DefinitionBranchKind",
    "CoverageStatus",
    "OriginKind",
    "PresenceKind",
    "ResolutionKind",
    "CompletenessMode",
    "AssessmentStatus",
    "RuleAssessmentStatus",
    "AssessmentAspect",
    "AssessmentChange",
    "ReportSchemaVersion",
    "DecisionMaker",
    "ArchitectureRuleKind",
)
MODULES = (
    "archkeel.ir.architecture_graph",
    "archkeel.ir.graph_codec",
    "archkeel.ir.target_graph",
    "archkeel.check.uml_compare",
)


@pytest.mark.parametrize("name", VOCABULARIES)
def test_graph_control_vocabulary_is_nominal_and_owned(name):
    control = getattr(graph, name)
    assert isinstance(control, type) and issubclass(control, StrEnum), (name, control)


def test_shared_rule_verdict_has_one_owner_and_declared_status_stays_distinct():
    assert RuleVerdict is graph.AssessmentStatus
    assert graph.RuleAssessmentStatus is not graph.AssessmentStatus
    assert Verdict is not graph.AssessmentStatus
    assert tuple(Verdict) == (Verdict.PASS, Verdict.FAIL)
    with pytest.raises(ValueError):
        Verdict("UNKNOWN")
    assert isinstance(graph.AssessmentStatus.PASS, StrEnum)
    assert graph.RuleAssessmentStatus.DECLARATION.value == "DECLARATION"


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0"])
def test_graph_parser_converts_closed_values_once_and_preserves_legacy_bytes(version):
    raw = {
        "origin": "declared",
        "schema_version": version,
        "entities": [
            {
                "id": "module",
                "kind": "module",
                "qualified_name": "sample",
                "language": "future-language",
                "presence": "planned",
                "responsibilities": ["Own the sample module."],
                "provenance": ["target.md"],
            }
        ],
    }
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


def test_component_layer_presence_preserves_missing_and_explicit_null_distinction():
    raw = {"component_id": "root", "role": "component"}
    assert parse_component_intent(raw).layer is None
    with pytest.raises(ValueError, match="component_intent.layer"):
        parse_component_intent({**raw, "layer": None})


def test_graph_codecs_keep_comparison_and_report_version_boundaries():
    comparison = parse_comparison({"status": "UNKNOWN", "schema_version": "1.0.0"})
    assert comparison.status is graph.AssessmentStatus.UNKNOWN
    for version in ("1.0.0", "1.2.0"):
        report = parse_report(
            {
                "observed": None,
                "target": None,
                "unavailable": "No source.",
                "schema_version": version,
            }
        )
        assert isinstance(report.schema_version, StrEnum)
    for version in ("1.1.0", "future", None):
        with pytest.raises(ValueError, match="report schema_version"):
            parse_report(
                {
                    "observed": None,
                    "target": None,
                    "unavailable": "No source.",
                    "schema_version": version,
                }
            )


@pytest.mark.parametrize(
    "factory,path",
    [
        (graph_schema, "schema/architecture-graph.schema.json"),
        (comparison_schema, "schema/architecture-comparison.schema.json"),
        (report_schema, "schema/architecture-report.schema.json"),
    ],
)
def test_nominal_graph_control_types_preserve_historical_schema(factory, path):
    assert factory() == json.loads((ROOT / path).read_text())


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        item
        for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith(("IR-GRAPH-", "IR-UML-architecture_graph"))
        or item["id"] in {"IR-DEPENDENCY-model", "archkeel.ir.facts"}
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        item
        for item in root["rules"]
        if item.get("source") in MODULES and item["kind"] == "forbidden_construct"
    ]
    contract["components"].append(
        {
            "id": "GRAPH-CHECK",
            "label": "graph-check",
            "role": "component",
            "packages": ["archkeel.check"],
            "public": ["archkeel.check.uml_compare"],
            "responsibilities": ["Compare independent graph intent with observed proof."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/typed-graph-vocabulary.md"],
        }
    )
    return contract


def _repository(tmp_path):
    facts = (
        "from __future__ import annotations\nimport hashlib\nfrom dataclasses import dataclass\n"
        "from enum import StrEnum\nfrom typing import Literal, TypeAlias\n\n"
        + _source_members(
            "src/archkeel/ir/facts.py",
            {
                "Evidence",
                "Language",
                "ParameterKind",
                "DefinitionContextKind",
                "DefinitionBranchKind",
                "stable_id",
            },
        )
    )
    model = (
        "from __future__ import annotations\nfrom collections.abc import Mapping, Sequence\n"
        "from typing import TypeAlias\nfrom dataclasses import dataclass\n"
        "from .facts import stable_id\nfrom .architecture_graph import AssessmentStatus\n\n"
        + _source_members("src/archkeel/ir/model.py", {"RawJson", "RunResult"})
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/ir/facts.py": facts,
        "archkeel/ir/model.py": model,
        "contract.json": json.dumps(_contract()),
        "docs/architecture/typed-graph-vocabulary.md": "Owned graph intent.\n",
        "docs/architecture/shared-parameter-kind.md": "Shared calling convention.\n",
        "docs/architecture/definition-context-ports.md": (
            ROOT / "docs/architecture/definition-context-ports.md"
        ).read_text(),
        "docs/architecture/language-adapter-target.md": "Source-only facts.\n",
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


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0", "1.3.0"])
def test_the_macro_entity_kind_needs_graph_schema_1_3(version):
    """AD-351: a released graph version has no kind macro, and the 4.0.1 host rejects it."""
    from jsonschema import Draft202012Validator

    entity = {
        "id": "m",
        "kind": "macro",
        "qualified_name": "sample.m",
        "language": "rust",
        "presence": "defined",
    }
    raw = {"origin": "observed", "schema_version": version, "entities": [entity]}
    accepted = Draft202012Validator(graph_schema()).is_valid(raw)
    assert accepted is (version == "1.3.0")
