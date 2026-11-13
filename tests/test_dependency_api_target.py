# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native source controls for the independently authored dependency API Target."""

import ast
import copy
import json
from pathlib import Path

from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report

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
