# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the rules of the native contract are pinned, so deleting or changing one fails here."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "native/architecture-contract.json"
EXPECTED_RULES = [
    ("NATIVE-ASSIGNMENT-COMPLETE", "complete_assignment"),
    ("NATIVE-REQUIRES-COMPLETE", "complete_requires"),
    ("NATIVE-NO-COMPONENT-CYCLES", "no_component_cycles"),
    ("NATIVE-NO-MODULE-CYCLES", "no_component_cycles"),
    ("NATIVE-EXTERNAL-TREE-SITTER", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-TREE-SITTER-TYPESCRIPT", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SYN", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-TREE-SITTER-LANGUAGE", "external_dependency_scope"),
]


def test_the_native_contract_keeps_its_eight_rules() -> None:
    rules = json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]
    assert [(rule["id"], rule["kind"]) for rule in rules] == EXPECTED_RULES


def test_the_module_cycle_rule_judges_modules_in_every_component() -> None:
    rules = {r["id"]: r for r in json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]}
    rule = rules["NATIVE-NO-MODULE-CYCLES"]
    assert rule["level"] == "module"
    assert "components" not in rule
