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
from archkeel.ir.codec import parse_contract
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
        entity
        for entity in authored["declarations"]["uml"]["entities"]
        if entity["id"].startswith(("IR-RULE-GRAMMAR-", "IR-RULE-OWNER-"))
        or entity["id"]
        in {
            "IR-DEPENDENCY-model",
            "IR-UML-architecture_graph",
            "IR-DEPENDENCY-model.ForbiddenDependencyRule",
            "IR-MODULE-OBJECT-InterfaceBoundaryRule",
        }
    ]
    return {
        "schema_version": "3.5.0",
        "components": [
            {
                "id": "TARGET-GOVERNANCE",
                "label": "governance",
                "role": "component",
                "packages": ["archkeel.ir"],
                "responsibilities": ["Own canonical rule intent."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/contract-rule-grammar.md"],
            }
        ],
        "rules": [rule for rule in root["rules"] if rule["id"] == GUARD],
        "declarations": {
            "uml": {
                "schema_version": "1.0.0",
                "entities": entities,
                "relationships": [],
                "scopes": [],
            }
        },
    }


def _repository(tmp_path, *, weakened=None, probe=None):
    files = {"archkeel/__init__.py": "", "archkeel/ir/__init__.py": ""}
    for module in (
        "model",
        "architecture_graph",
        "dependency",
        "facts",
        "state_facts",
        "type_shapes",
        "host_records",
        "measurements",
        "contract_version",
        "codec_contract",
    ):
        source = (ROOT / f"src/archkeel/ir/{module}.py").read_text()
        if module == "model":
            source = (
                "from __future__ import annotations\nimport builtins\n"
                "from typing import Literal, TypeAlias\n"
                "from dataclasses import dataclass\nfrom enum import StrEnum\n"
                "from .architecture_graph import ArchitectureRuleGrammar\n"
                "from .architecture_graph import ArchitectureRuleKind, DecisionMaker\n"
                "from .dependency import DependencySelector, SelectorMatch\n"
                "from .dependency import DependencyTargetKind\n\n"
                + _source_members(
                    "src/archkeel/ir/model.py",
                    {
                        "ForbiddenDependencyRule",
                        "AllowedDependencyRule",
                        "ForbiddenConstructRule",
                        "CompleteAssignmentRule",
                        "CompleteRequiresRule",
                        "LayerOrderRule",
                        "CompleteExternalScopeRule",
                        "NoComponentCyclesRule",
                        "InterfaceBoundaryRule",
                        "SiblingIsolationRule",
                        "SymbolPlacementRule",
                        "BoundaryTypesRule",
                        "ContractComponent",
                        "RequiredComponent",
                        "CompatibilityShim",
                        "CompatibilityLifetime",
                        "CycleLevel",
                    },
                )
            )
        if module == "model" and weakened is not None:
            annotation = FIELDS[weakened]
            owner, name = weakened.split(".")
            start = source.index(f"class {owner}")
            end = source.find("\n@dataclass", start)
            if end < 0:
                end = len(source)
            segment = source[start:end]
            assert f"{name}: {annotation}" in segment
            source = (
                source[:start]
                + segment.replace(f"{name}: {annotation}", f"{name}: str", 1)
                + source[end:]
            )
        if module == "codec_contract" and probe is not None:
            marker = "    value = _nonempty(raw, label)\n"
            assert marker in source
            source = source.replace(marker, probe + marker, 1)
        files[f"archkeel/ir/{module}.py"] = source
    parse_contract(_contract())
    files["contract.json"] = json.dumps(_contract())
    files["docs/architecture/contract-rule-grammar.md"] = (
        ROOT / "docs/architecture/contract-rule-grammar.md"
    ).read_text()
    files["docs/architecture/dependency-selector-target.md"] = (
        ROOT / "docs/architecture/dependency-selector-target.md"
    ).read_text()
    files["docs/architecture/module-object-grants.md"] = (
        ROOT / "docs/architecture/module-object-grants.md"
    ).read_text()
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
    assert any(
        row.kind == "uml_conformance" and row.data.get("aspect") == "annotation"
        for row in trace_valid_violations(result)
    )
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize(
    "probe",
    [
        '    if raw == "architect":\n        pass\n',
        '    if raw in ("architect", "agent"):\n        pass\n',
        '    match raw:\n        case "architect":\n            pass\n',
        (
            '    from typing import Final\n    value_tag: Final[str] = "architect"\n'
            "    if raw == value_tag:\n        pass\n"
        ),
        '    if "architect" in raw:\n        pass\n',
    ],
    ids=["equality", "membership", "match", "final-alias", "needle"],
)
def test_native_codec_grammar_rejects_raw_source_controls(tmp_path, probe):
    root, config = _repository(tmp_path, probe=probe)
    before = (root / "contract.json").read_bytes()
    result = _model(root, config)
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(result))
    assert (root / "contract.json").read_bytes() == before


DECLARATION_GUARDS = {
    "IR-DECLARATION-OWNER-CONTROL", "IR-RULE-SELECTOR-CONTROL",
    "GRAPH-TYPED-ARCHITECTURE-GRAPH", "TYPES-ENUM-IN-MODEL",
}


def _declaration_repository(tmp_path, *, changed=None, relocate=False):
    authored = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    policy = json.loads((ROOT / "architecture-contract.json").read_text())
    contract = _contract()
    contract["declarations"]["uml"]["entities"] = [
        row for row in authored["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-DECLARATION-")
        or row["id"] == "IR-UML-architecture_graph"
    ]
    contract["rules"] = [row for row in policy["rules"] if row["id"] in DECLARATION_GUARDS]
    assert {row["id"] for row in contract["rules"]} == DECLARATION_GUARDS
    files = {"archkeel/__init__.py": "", "archkeel/ir/__init__.py": ""}
    for module in (
        "architecture_graph", "model", "facts", "state_facts", "type_shapes",
        "dependency", "interfaces", "duplication", "module_explore",
    ):
        source = (ROOT / f"src/archkeel/ir/{module}.py").read_text()
        if changed is not None and module == changed[0]:
            _, old, new = changed
            assert source.count(old) == 1
            source = source.replace(old, new, 1)
        if relocate and module == "architecture_graph":
            start = source.index("class ArchitectureDeclarationKind(StrEnum):")
            end = source.index("\n\n", start)
            # Include all member lines, stopping at the next top-level declaration.
            block = source[start:end]
            assert block.count(" = ") == 8
            source = source[:start] + source[end + 2:]
            files["archkeel/ir/misplaced_declaration.py"] = "from enum import StrEnum\n\n" + block + "\n"
        files[f"archkeel/ir/{module}.py"] = source
    provenance = {
        name for rule in contract["rules"] for name in rule["provenance"]
    } | {"docs/architecture/contract-rule-grammar.md"}
    files.update({name: (ROOT / name).read_text() for name in provenance})
    files["contract.json"] = json.dumps(contract)
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_actual_rule_and_declaration_selectors_use_the_owned_api(tmp_path):
    from archkeel.ir.report_graph import architecture_report

    root, config = _declaration_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assessments = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    print("ACTUAL_DECLARATION_GUARDS=" + json.dumps({
        key: {"status": row.status, "proven": row.evaluation_proven}
        for key, row in assessments.items() if key in DECLARATION_GUARDS
    }))
    assert comparison is not None and comparison.status == "PASS", comparison
    for rule_id in DECLARATION_GUARDS:
        assert assessments[rule_id].status == "PASS" and assessments[rule_id].evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "old,new",
    [
        ("value: JsonValue | RawJson) -> ArchitectureRuleKind | None:",
         "value: JsonValue | RawJson) -> str | None:"),
        ("value: JsonValue | RawJson,\n) -> ArchitectureRuleKind | ArchitectureDeclarationKind | None:",
         "value: JsonValue | RawJson,\n) -> str | None:"),
        ("class ArchitectureDeclarationKind(StrEnum):", "class ArchitectureDeclarationKind:"),
    ],
    ids=["rule-result", "declaration-result", "declaration-kind"],
)
def test_fixed_authored_declaration_target_rejects_weakened_ports(tmp_path, old, new):
    root, config = _declaration_repository(
        tmp_path, changed=("architecture_graph", old, new)
    )
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(row.kind == "uml_conformance" for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


def test_actual_placement_rejects_relocating_declaration_vocabulary(tmp_path):
    root, config = _declaration_repository(tmp_path, relocate=True)
    model = _model(root, config)
    assert any("TYPES-ENUM-IN-MODEL" in row.rule_ids for row in trace_valid_violations(model))


@pytest.mark.parametrize(
    "module,old,new,guard",
    [
        ("duplication", "parse_architecture_declaration_kind(record.kind) is ArchitectureDeclarationKind.SPOT_OWNER",
         'record.kind == "spot_owner"', "IR-DECLARATION-OWNER-CONTROL"),
        ("module_explore", "kind is ArchitectureRuleKind.FORBIDDEN_DEPENDENCY:",
         'assessment.kind == "forbidden_dependency":', "IR-RULE-SELECTOR-CONTROL"),
        ("module_explore", "kind is ArchitectureRuleKind.FORBIDDEN_DEPENDENCY:",
         "kind.value == ArchitectureRuleKind.FORBIDDEN_DEPENDENCY.value:",
         "IR-RULE-SELECTOR-CONTROL"),
    ],
    ids=["declaration-raw", "rule-raw", "rule-value-evasion"],
)
def test_native_actual_declaration_control_mutations_remain_traceable(
    tmp_path, module, old, new, guard
):
    # The first rule branch is the consumer's actual pre-loop allowed-source decision.
    if module == "module_explore":
        old = "\n    if " + old
        new = "\n    if " + new
    root, config = _declaration_repository(tmp_path, changed=(module, old, new))
    model = _model(root, config)
    assert any(guard in row.rule_ids for row in trace_valid_violations(model))
