# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the rules of the native contract are pinned, so deleting or changing one fails here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACT = Path(__file__).parents[1] / "native/architecture-contract.json"
EXPECTED_RULES = [
    ("NATIVE-LAYER-ORDER", "layer_order"),
    ("NATIVE-INTERFACE-BOUNDARY", "interface_boundary"),
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
    ("NATIVE-EXTERNAL-SAPHYR", "external_dependency_scope"),
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
    # AD-406: only archkeel-collect links a collector, and only the core uses archkeel-collect.
    ("NATIVE-NO-CORE-TO-TYPESCRIPT", "forbidden_dependency"),
    ("NATIVE-NO-EVAL-TO-TYPESCRIPT", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-TYPESCRIPT", "forbidden_dependency"),
    ("NATIVE-NO-REPORT-TO-TYPESCRIPT", "forbidden_dependency"),
    ("NATIVE-NO-CORE-TO-RUST", "forbidden_dependency"),
    ("NATIVE-NO-EVAL-TO-RUST", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-RUST", "forbidden_dependency"),
    ("NATIVE-NO-REPORT-TO-RUST", "forbidden_dependency"),
    ("NATIVE-NO-EVAL-TO-COLLECT", "forbidden_dependency"),
    ("NATIVE-NO-MODEL-TO-COLLECT", "forbidden_dependency"),
    ("NATIVE-NO-REPORT-TO-COLLECT", "forbidden_dependency"),
    # AD-406 review F4: collect uses only facts, store, wire and the collectors; a collector uses
    # no store and no crate of the core side.
    ("NATIVE-NO-COLLECT-TO-CONTRACT", "forbidden_dependency"),
    ("NATIVE-NO-COLLECT-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-COLLECT-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-COLLECT-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-COLLECT-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-STORE", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-TYPESCRIPT-TO-COLLECT", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-STORE", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-RUST-TO-COLLECT", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-STORE", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-PYTHON-TO-COLLECT", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-STORE", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-MODEL", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-EVAL", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-REPORT", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-CORE", "forbidden_dependency"),
    ("NATIVE-NO-DART-TO-COLLECT", "forbidden_dependency"),
    # AD-668: a neutral crate names no language (its known places stay FAIL, #1384).
    ("NATIVE-NEUTRAL-STORE-NO-PROFILE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-MODEL-NO-PROFILE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-EVAL-NO-PROFILE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-REPORT-NO-PROFILE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-CORE-NO-PROFILE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-STORE-NO-PYTHON-MODULE", "forbidden_dependency"),
    ("NATIVE-NEUTRAL-STORE-NO-DART-MODULE", "forbidden_dependency"),
]


def test_the_native_contract_keeps_its_pinned_rules() -> None:
    rules = json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]
    assert [(rule["id"], rule["kind"]) for rule in rules] == EXPECTED_RULES


def test_the_module_cycle_rule_judges_modules_in_every_component() -> None:
    rules = {r["id"]: r for r in json.loads(CONTRACT.read_text(encoding="utf-8"))["rules"]}
    rule = rules["NATIVE-NO-MODULE-CYCLES"]
    assert rule["level"] == "module"
    assert "components" not in rule


def _minimal(ports: set[str] | list[str]) -> list[str]:
    """A port is a module prefix, so a port below another port of the list says nothing more."""
    return sorted(
        port for port in ports if not any(port.startswith(f"{other}.") for other in ports)
    )


def _claims(component: dict[str, Any], module: str) -> bool:
    packages = component["packages"]
    exact = module in component.get("exact_modules", [])
    return exact or any(module == name or module.startswith(f"{name}.") for name in packages)


def test_each_requirement_names_its_ports() -> None:
    """AD-588: a requirement without `through` permits each module of its target.

    `NATIVE-REQUIRES-COMPLETE` judges the ports. A module port is a prefix, so a crate root port
    permits the whole crate; a use of a name at the root is a symbol port instead (AD-616).
    """
    components = {
        c["label"]: c for c in json.loads(CONTRACT.read_text(encoding="utf-8"))["components"]
    }
    for label, component in components.items():
        for required in component.get("requires", []):
            target = components[required["component"]]
            ports = required.get("through", [])
            where = f"{label} -> {target['label']}"
            assert ports, f"{where} has no port"
            assert ports == _minimal(ports), f"{where}: the ports are not sorted and minimal"
            modules = [port.partition(":")[0] for port in ports]
            assert all(_claims(target, module) for module in modules), f"{where}: another part"
            # AD-616: a crate root is a port only for an import of the whole crate (a manifest
            # dependency); each other use of the root is a symbol port `root:Name`.
            symbols = {port.partition(":")[0] for port in ports if ":" in port}
            assert not symbols & set(ports), f"{where}: a root port and its symbol ports"


def test_each_component_lists_the_names_that_it_publishes() -> None:
    """AD-604: every component states `public` as `module:Name` entries of its own modules.

    An empty list publishes no name: a use of the component from another one fails.
    """
    components = json.loads(CONTRACT.read_text(encoding="utf-8"))["components"]
    for component in components:
        public = component["public"]
        assert public == sorted(set(public)), component["label"]
        for entry in public:
            module, _, name = entry.partition(":")
            assert name and "." not in name, entry
            assert _claims(component, module), f"{component['label']}: {entry} is not its module"


def test_a_crate_root_is_the_one_public_path_of_each_name_that_it_publishes() -> None:
    """AD-608: a component that owns a crate root lists a name of the root only at the root.

    A deeper entry of the same name would be a second public path of it, and a use by the deeper
    path would pass. `NATIVE-INTERFACE-BOUNDARY` then fails each use that does not take the root.
    """
    for component in json.loads(CONTRACT.read_text(encoding="utf-8"))["components"]:
        claimed = component["packages"] + component.get("exact_modules", [])
        roots = {module for module in claimed if module.count(".") == 1}
        entries = [entry.partition(":")[::2] for entry in component["public"]]
        at_root = {name for module, name in entries if module in roots}
        deeper = [f"{m}:{n}" for m, n in entries if m not in roots and n in at_root]
        assert deeper == [], f"{component['label']}: {deeper}"
