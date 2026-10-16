# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native source controls for the independently authored dependency API Target."""

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
TARGET_PREFIX = "IR-DEPENDENCY-"


def _source_members(path, names):
    source = (ROOT / path).read_text()
    tree = ast.parse(source)
    return "\n\n".join(
        ast.get_source_segment(source, node)
        if not isinstance(node, ast.ClassDef)
        else "\n".join(
            source.splitlines()[
                min([node.lineno, *(d.lineno for d in node.decorator_list)]) - 1 : node.end_lineno
            ]
        )
        for node in tree.body
        if (
            isinstance(node, (ast.FunctionDef, ast.ClassDef))
            and node.name in names
            or isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in names
        )
    )


def _dependency_contract():
    """Filter authored intent only; observations never contribute expected declarations."""
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    contract = copy.deepcopy(contract)
    contract.pop("$schema", None)
    contract["rules"] = [
        rule
        for rule in contract["rules"]
        if rule["kind"] in {"interface_boundary", "boundary_types"}
        and (rule.get("source") is None or rule["source"] == "archkeel.ir.dependency")
    ]
    contract["declarations"]["uml"]["entities"] = [
        entity
        for entity in contract["declarations"]["uml"]["entities"]
        if entity["id"].startswith(TARGET_PREFIX)
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"].extend(
        rule
        for rule in root_contract["rules"]
        if rule["kind"] == "forbidden_construct" and rule.get("source") == "archkeel.ir.dependency"
    )
    contract["components"].append(
        {
            "id": "DEPENDENCY-CONSUMER",
            "label": "consumer",
            "role": "component",
            "packages": ["archkeel.consumer"],
            "public": ["archkeel.consumer"],
            "responsibilities": ["Consume the declared dependency API."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/archkeel.md"],
        }
    )
    return contract


def _dependency_repository(
    tmp_path, *, dependency_source=None, model_source=None, consumer_source=None
):
    """Observe real Python declarations in a disposable archkeel-named repository."""
    dependency = (ROOT / "src/archkeel/ir/dependency.py").read_text()
    model = (
        "from dataclasses import dataclass\nfrom typing import Literal, TypeAlias\n"
        "from .dependency import (ComponentOwnership, DependencyOwner, DependencySelection, "
        "DependencySelector, "
        "DependencyTargetKind, ModuleSelection, SelectorMatch)\n\n"
        + _source_members(
            "src/archkeel/ir/model.py",
            {
                "ForbiddenDependencyRule",
                "dependency_owners",
                "PackageComponentOwnership",
                "ComponentOwnershipInput",
                "declared_package_pair",
                "forbidden_dependency_scopes",
            },
        )
    )
    facts = _source_members("src/archkeel/ir/facts.py", {"in_scope"})
    codec = (
        "from .facts import Record\nfrom .dependency import DependencySelector\n"
        + _source_members("src/archkeel/ir/codec_contract.py", {"parse_dependency_selector"})
    )
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/dependency.py": dependency
            if dependency_source is None
            else dependency_source,
            "archkeel/ir/model.py": model if model_source is None else model_source,
            "archkeel/ir/facts.py": facts,
            "archkeel/ir/codec_contract.py": codec,
            "archkeel/consumer.py": consumer_source
            or "from .ir.dependency import DependencySelector\n",
            "contract.json": json.dumps(_dependency_contract()),
            "docs/architecture/archkeel.md": (ROOT / "docs/architecture/archkeel.md").read_text(),
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison(model):
    comparison = architecture_report(model).comparison
    assert comparison is not None
    return comparison


def _assert_dependency_boundary_positions(model, rule_id):
    boundary = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.id == rule_id
    )
    assert boundary.status == "PASS" and boundary.evaluation_proven, boundary
    receipt = next(
        row
        for row in model.records("scope_observations")
        if row.kind == "rule_evaluation" and row.rule_ids == (rule_id,)
    )
    for method in ("component_pair", "select"):
        name = f"archkeel.ir.dependency.DependencySelector.{method}"
        symbol = next(
            row for row in model.records("symbols") if row.data.get("qualified_name") == name
        )
        parameter = next(
            row for row in symbol.data.get("parameters") if row.get("name") == "components"
        )
        assert parameter.get("annotation") == "tuple[DependencyOwner, ...]"
        assert symbol.id in receipt.fact_ids, (name, receipt)
        assert not [
            row
            for row in model.records("unknowns")
            if row.data.get("qualified_name") == name and row.data.get("position") == "components"
        ]


def test_own_native_dependency_boundary_covers_both_ownership_parameters(self_observation):
    _assert_dependency_boundary_positions(self_observation, "ir:TARGET-DEPENDENCY-BOUNDARY-TYPES")


def test_native_dependency_api_matches_the_independent_target(tmp_path):
    root, config = _dependency_repository(tmp_path)
    model = _model(root, config)
    comparison = _comparison(model)
    assert comparison.assessments, "The bounded dependency API Target must be authored"
    assert comparison.status == "PASS", comparison
    rule = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert rule.status == "PASS" and rule.evaluation_proven
    protected = {
        "archkeel.ir.dependency.DependencyOwner.identity": "annotation",
        "archkeel.ir.dependency.DependencyOwner.modules": "annotation",
        "archkeel.ir.dependency.DependencySelector.source_match": "annotation",
        "archkeel.ir.dependency.DependencySelector.target_kind": "annotation",
        "archkeel.ir.dependency.DependencySelector.select": "signature",
        "archkeel.ir.model.dependency_owners": "signature",
        "archkeel.ir.model.declared_package_pair": "signature",
        "archkeel.ir.model.forbidden_dependency_scopes": "signature",
        "archkeel.ir.model.ForbiddenDependencyRule.selector": "signature",
        "archkeel.ir.codec_contract.parse_dependency_selector": "signature",
    }
    target = _dependency_contract()["declarations"]["uml"]["entities"]
    for name, aspect in protected.items():
        entity = next(item for item in target if item["qualified_name"] == name)
        assert any(
            row.subject_id == entity["id"] and row.aspect == aspect and row.status == "PASS"
            for row in comparison.assessments
        ), (name, aspect, comparison)
    _assert_dependency_boundary_positions(model, "TARGET-DEPENDENCY-BOUNDARY-TYPES")
    assert not trace_valid_violations(model)


@pytest.mark.parametrize("mutation", ["field", "parameter", "selection", "property"])
def test_native_source_type_widening_fails_with_the_target_unchanged(tmp_path, mutation):
    root, config = _dependency_repository(tmp_path)
    before = (root / "contract.json").read_bytes()
    if mutation == "field":
        path, old, new = "dependency.py", "source_match: SelectorMatch", "source_match: str"
    elif mutation == "parameter":
        path, old, new = (
            "model.py",
            "source_match: SelectorMatch = SelectorMatch.PREFIX,",
            "source_match: str = SelectorMatch.PREFIX,",
        )
    elif mutation == "selection":
        path, old, new = "model.py", ") -> DependencySelection:", ") -> tuple:"
    else:
        path, old, new = (
            "model.py",
            "def selector(self) -> DependencySelector:",
            "def selector(self) -> str:",
        )
    source = root / "archkeel/ir" / path
    assert old in source.read_text()
    source.write_text(source.read_text().replace(old, new, 1))
    model = _model(root, config)
    assert (root / "contract.json").read_bytes() == before
    assert any(row.status == "FAIL" for row in _comparison(model).assessments)
    rules = [
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    ]
    assert len(rules) == 1 and rules[0].status == "FAIL"
    assert any(row.rule_ids == (rules[0].id,) for row in trace_valid_violations(model))


def test_native_consumer_must_use_the_declared_dependency_api(tmp_path):
    root, config = _dependency_repository(
        tmp_path,
        consumer_source="from .ir.dependency import in_scope\n",
    )
    model = _model(root, config)
    assert any("TARGET-INTERFACE_BOUNDARY" in row.rule_ids for row in trace_valid_violations(model))


def test_native_incomplete_member_proof_stays_unknown(tmp_path):
    root, config = _dependency_repository(tmp_path)
    source = root / "archkeel/ir/dependency.py"
    source.write_text(source.read_text().replace("def select(", "def unavailable_select(", 1))
    model = _model(root, config)
    entity = next(
        item
        for item in _dependency_contract()["declarations"]["uml"]["entities"]
        if item["qualified_name"] == "archkeel.ir.dependency.DependencySelector.select"
    )
    # Calls leave this class's member inventory partial. An absent method cannot
    # gain a closed-scope absence proof from this limited collector evidence.
    assert any(
        row.subject_id == entity["id"] and row.aspect == "existence" and row.status == "UNKNOWN"
        for row in _comparison(model).assessments
    )
