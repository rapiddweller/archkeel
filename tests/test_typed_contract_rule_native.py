# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent native intent checks real rule declarations and the actual codec module."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
FIELDS = {
    "ForbiddenDependencyRule.kind": "Literal[ArchitectureRuleKind.FORBIDDEN_DEPENDENCY]",
    "ForbiddenDependencyRule.decided_by": "DecisionMaker",
    "CompatibilityShim.lifetime": "CompatibilityLifetime",
    "NoComponentCyclesRule.level": "Literal[CycleLevel.MODULE] | None",
}
GUARD = "IR-CONTRACT-TYPED-CONTROL"


def _contract():
    authored = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    entities = [
        entity for entity in authored["declarations"]["uml"]["entities"]
        if entity["id"].startswith("IR-RULE-GRAMMAR-")
        or entity["id"] in {
            "IR-DEPENDENCY-model", "IR-DEPENDENCY-model.ForbiddenDependencyRule",
        }
    ]
    return {
        "schema_version": "3.5.0",
        "components": [{
            "id": "TARGET-GOVERNANCE", "label": "governance", "role": "component",
            "packages": ["archkeel.ir"], "responsibilities": ["Own canonical rule intent."],
            "forbidden_responsibilities": [], "provenance": ["docs/architecture/contract-rule-grammar.md"],
        }],
        "rules": [rule for rule in root["rules"] if rule["id"] == GUARD],
        "declarations": {"uml": {"schema_version": "1.0.0", "entities": entities, "relationships": [], "scopes": []}},
    }


def _repository(tmp_path, *, weakened=None, probe=None):
    files = {"archkeel/__init__.py": "", "archkeel/ir/__init__.py": ""}
    for module in ("model", "architecture_graph", "dependency", "facts", "state_facts", "type_shapes", "host_records", "measurements", "contract_version", "codec_contract"):
        source = (ROOT / f"src/archkeel/ir/{module}.py").read_text()
        if module == "model":
            source = (
                "from __future__ import annotations\n"
                "from typing import Literal, TypeAlias\n"
                "from dataclasses import dataclass\nfrom enum import StrEnum\n"
                "from .architecture_graph import ArchitectureRuleKind, DecisionMaker\n"
                "from .dependency import DependencySelector, SelectorMatch\n"
                "from .dependency import DependencyTargetKind\n\n"
                + _source_members("src/archkeel/ir/model.py", {
                    "ForbiddenDependencyRule", "AllowedDependencyRule", "ForbiddenConstructRule", "CompleteAssignmentRule", "CompleteRequiresRule", "LayerOrderRule", "CompleteExternalScopeRule", "NoComponentCyclesRule", "InterfaceBoundaryRule", "SiblingIsolationRule", "SymbolPlacementRule", "BoundaryTypesRule",
                    "ContractComponent", "RequiredComponent", "CompatibilityShim",
                    "CompatibilityLifetime", "CycleLevel",
                })
            )
        if module == "model" and weakened is not None:
            annotation = FIELDS[weakened]
            owner, name = weakened.split(".")
            start = source.index(f"class {owner}:")
            end = source.find("\n@dataclass", start)
            if end < 0:
                end = len(source)
            segment = source[start:end]
            assert f"{name}: {annotation}" in segment
            source = source[:start] + segment.replace(f"{name}: {annotation}", f"{name}: str", 1) + source[end:]
        if module == "codec_contract" and probe is not None:
            marker = '    value = _nonempty(raw, label)\n'
            assert marker in source
            source = source.replace(marker, probe + marker, 1)
        files[f"archkeel/ir/{module}.py"] = source
    files["contract.json"] = json.dumps(_contract())
    files["docs/architecture/contract-rule-grammar.md"] = (ROOT / "docs/architecture/contract-rule-grammar.md").read_text()
    files["docs/architecture/dependency-selector-target.md"] = (ROOT / "docs/architecture/dependency-selector-target.md").read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_authored_rule_api_and_codec_grammar_controls_pass(tmp_path):
    root, config = _repository(tmp_path)
    result = _model(root, config)
    rows = rule_assessments(result, undecided_by_rule={})
    assert all(row.status == "PASS" and row.evaluation_proven for row in rows), rows
    assert not trace_valid_violations(result)


@pytest.mark.parametrize("field", FIELDS)
def test_native_rule_type_widening_fails_the_same_authored_target(tmp_path, field):
    root, config = _repository(tmp_path, weakened=field)
    before = (root / "contract.json").read_bytes()
    result = _model(root, config)
    assert any(row.kind == "uml_conformance" and row.data.get("aspect") == "annotation" for row in trace_valid_violations(result))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize("probe", [
    '    if raw == "architect":\n        pass\n',
    '    if raw in ("architect", "agent"):\n        pass\n',
    '    match raw:\n        case "architect":\n            pass\n',
    (
        '    from typing import Final\n    value_tag: Final[str] = "architect"\n'
        '    if raw == value_tag:\n        pass\n'
    ),
    '    if "architect" in raw:\n        pass\n',
], ids=["equality", "membership", "match", "final-alias", "needle"])
def test_native_codec_grammar_rejects_raw_source_controls(tmp_path, probe):
    root, config = _repository(tmp_path, probe=probe)
    before = (root / "contract.json").read_bytes()
    result = _model(root, config)
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(result))
    assert (root / "contract.json").read_bytes() == before
