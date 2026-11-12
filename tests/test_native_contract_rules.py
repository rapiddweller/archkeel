# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the rules of the native contract are pinned, so deleting or changing one fails here."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "native/architecture-contract.json"
EXPECTED_RULES = [
    ("NATIVE-PY-SYMBOLS-NO-SURVEY", "forbidden_dependency"),
    ("NATIVE-PY-UNPARSE-NO-SURVEY", "forbidden_dependency"),
    ("NATIVE-PY-UNPARSE-NO-SYMBOLS", "forbidden_dependency"),
    ("NATIVE-PY-MODULE-NO-SURVEY", "forbidden_dependency"),
    ("NATIVE-PY-MODULE-NO-SYMBOLS", "forbidden_dependency"),
    ("NATIVE-PY-MODULE-NO-UNPARSE", "forbidden_dependency"),
    ("NATIVE-PY-TREE-NO-SURVEY", "forbidden_dependency"),
    ("NATIVE-PY-TREE-NO-SYMBOLS", "forbidden_dependency"),
    ("NATIVE-PY-TREE-NO-UNPARSE", "forbidden_dependency"),
    ("NATIVE-PY-PARSE-NO-SURVEY", "forbidden_dependency"),
    ("NATIVE-PY-PARSE-NO-SYMBOLS", "forbidden_dependency"),
    ("NATIVE-PY-PARSE-NO-UNPARSE", "forbidden_dependency"),
    ("NATIVE-ASSIGNMENT-COMPLETE", "complete_assignment"),
    ("NATIVE-REQUIRES-COMPLETE", "complete_requires"),
    ("NATIVE-NO-COMPONENT-CYCLES", "no_component_cycles"),
    ("NATIVE-NO-MODULE-CYCLES", "no_component_cycles"),
    ("NATIVE-EXTERNAL-TREE-SITTER", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-TREE-SITTER-TYPESCRIPT", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SYN", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-TREE-SITTER-LANGUAGE", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-RUFF-PYTHON-PARSER", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-RUFF-PYTHON-AST", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-TOML", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-PROC-MACRO2", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-RUFF-TEXT-SIZE", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-CC", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-FLATE2", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SCHEMARS", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-UNICODE-IDENT", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SHA2", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SERDE", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-SERDE-JSON", "external_dependency_scope"),
    ("NATIVE-EXTERNAL-COMPLETE", "complete_external_scope"),
    ("NATIVE-NO-EVAL-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-CONTRACT-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-CONTRACT-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-CONTRACT-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-CONTRACT-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-EVAL-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-REPORT-TO-CORE", "forbidden_dependency"),
]


def test_the_native_contract_keeps_its_pinned_rules() -> None:
    rules = json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]
    assert [(rule["id"], rule["kind"]) for rule in rules] == EXPECTED_RULES


def test_the_module_cycle_rule_judges_modules_in_every_component() -> None:
    rules = {r["id"]: r for r in json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]}
    rule = rules["NATIVE-NO-MODULE-CYCLES"]
    assert rule["level"] == "module"
    assert "components" not in rule
