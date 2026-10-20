# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Contract schema identity is nominal; historical wire versions stay exact."""

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.codec_contract import ContractVersionError
from archkeel.ir.model import ArchitectureContract

VERSIONS = (
    "2.1.0",
    "2.2.0",
    "2.3.0",
    "3.0.0",
    "3.1.0",
    "3.2.0",
    "3.3.0",
    "3.4.0",
    "3.5.0",
    "3.6.0",
    "3.7.0",
    "3.8.0",
    "3.9.0",
    "3.10.0",
    "3.11.0",
    "3.12.0",
    "3.13.0",
    "3.14.0",
)


@pytest.mark.parametrize("version", VERSIONS)
def test_parser_normalizes_each_historical_version_to_a_nominal_owner(version):
    raw = {"schema_version": version, "components": [], "rules": []}
    contract = parse_contract(raw)
    assert isinstance(contract.schema_version, StrEnum)
    assert str(contract.schema_version) == version
    expected = (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode()
    assert contract_bytes(contract) == expected
    assert parse_contract(raw) == contract


@pytest.mark.parametrize("version", VERSIONS)
def test_direct_valid_legacy_version_is_normalized_at_model_ingress(version):
    contract = ArchitectureContract(version, (), ())
    assert isinstance(contract.schema_version, StrEnum)
    assert str(contract.schema_version) == version


def test_contract_version_field_has_a_concrete_nominal_type():
    annotation = get_type_hints(ArchitectureContract)["schema_version"]
    assert isinstance(annotation, type) and issubclass(annotation, StrEnum)


@pytest.mark.parametrize("invalid", [None, True, 1, {}, [], "", "2.0.0", "3.15.0"])
def test_parser_keeps_rejecting_unsupported_or_nontext_versions(invalid):
    with pytest.raises(ContractVersionError):
        parse_contract({"schema_version": invalid, "components": [], "rules": []})


@pytest.mark.parametrize(
    "feature,before,first",
    [
        ("UML", "2.1.0", "2.2.0"),
        ("LAYERS", "2.2.0", "2.3.0"),
        ("ALIAS_BODY", "2.3.0", "3.0.0"),
        ("KEY_ALIAS_BODY", "3.0.0", "3.1.0"),
        ("LITERAL_MAPPING_ARM", "3.1.0", "3.2.0"),
        ("NATIVE_MAPPING", "3.2.0", "3.3.0"),
        ("MODULE_SELECTORS", "3.3.0", "3.4.0"),
        ("IMPORT_NAMESPACES", "3.4.0", "3.5.0"),
        ("MODULE_OBJECT_GRANTS", "3.5.0", "3.6.0"),
        ("CALL_OWNER", "3.6.0", "3.7.0"),
        ("BOUNDED_NUMERIC_OPERAND", "3.7.0", "3.8.0"),
        ("PROTOCOL_DECLARATIONS", "3.8.0", "3.9.0"),
        ("FORBIDDEN_CALL_ARGUMENT", "3.9.0", "3.10.0"),
        ("CATALOG_ARGUMENT", "3.13.0", "3.14.0"),
        ("CATALOG_USE", "3.13.0", "3.14.0"),
        ("CONSTRUCT_SELECTOR", "3.10.0", "3.11.0"),
        ("SOURCE_OWNERSHIP", "3.11.0", "3.12.0"),
    ],
)
def test_feature_policy_keeps_each_existing_introduction_boundary(feature, before, first):
    from archkeel.ir.contract_version import ContractFeature, ContractVersion, supports_feature

    choice = ContractFeature[feature]
    assert not supports_feature(ContractVersion(before), choice)
    assert supports_feature(ContractVersion(first), choice)


def _version_repository(tmp_path):
    from archkeel.check.ports import ScanConfig

    root = Path(__file__).parents[1]
    contract = copy.deepcopy(json.loads((root / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["rules"] = [
        rule
        for rule in json.loads((root / "architecture-contract.json").read_text())["rules"]
        if rule["id"] == "CONTRACT-VERSION-TYPED-CONTROL"
    ]
    contract["declarations"]["uml"]["entities"] = [
        entity
        for entity in contract["declarations"]["uml"]["entities"]
        if entity["id"].startswith("IR-VERSION-") or entity["id"] == "IR-DEPENDENCY-model"
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/contract_version.py": (
            root / "src/archkeel/ir/contract_version.py"
        ).read_text(),
        "archkeel/ir/model.py": (
            "from __future__ import annotations\nimport builtins\n"
            "from dataclasses import dataclass\n"
            "from .contract_version import ContractVersion\n\n"
            + _source_members("src/archkeel/ir/model.py", {"ArchitectureContract"})
        ),
        "contract.json": json.dumps(contract),
        "docs/architecture/contract-version-types.md": "Contract version intent.\n",
    }
    fixture = _prepare_repo(tmp_path, files)
    return fixture, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison(model):
    from archkeel.ir.report_graph import architecture_report

    comparison = architecture_report(model).comparison
    assert comparison is not None
    return comparison


def test_native_version_api_matches_independent_intent_and_guard(tmp_path):
    from archkeel.ir.decisions import rule_assessments
    from archkeel.ir.trace import trace_valid_violations

    root, config = _version_repository(tmp_path)
    model = _model(root, config)
    assert _comparison(model).status == "PASS", _comparison(model)
    rows = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    guard = rows["CONTRACT-VERSION-TYPED-CONTROL"]
    assert guard.status == "PASS" and guard.evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "path,before,after",
    [
        ("model.py", "schema_version: ContractVersion", "schema_version: str"),
        ("contract_version.py", "feature: ContractFeature", "feature: str"),
        ("contract_version.py", "version: ContractVersion", "version: str"),
        ("contract_version.py", ") -> bool:", ") -> str:"),
    ],
)
def test_native_version_type_widening_fails_under_unchanged_intent(tmp_path, path, before, after):
    from archkeel.ir.trace import trace_valid_violations

    root, config = _version_repository(tmp_path)
    source = root / "archkeel/ir" / path
    text = source.read_text()
    assert before in text
    source.write_text(text.replace(before, after, 1))
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in _comparison(model).assessments
    )
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "3.6.0"\n',
        'def _probe(value):\n    return value in ("3.5.0", "3.6.0")\n',
        'def _probe(value):\n    return "3.6.0" in value\n',
        (
            'def _probe(value):\n    match value:\n        case "3.6.0":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nVERSION: Final[str] = "3.6.0"\n'
            "def _probe(value):\n    return value == VERSION\n"
        ),
    ],
)
def test_native_version_guard_rejects_raw_protocol_control(tmp_path, probe):
    from archkeel.ir.trace import trace_valid_violations

    root, config = _version_repository(tmp_path)
    path = root / "archkeel/ir/contract_version.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert any(
        "CONTRACT-VERSION-TYPED-CONTROL" in row.rule_ids for row in trace_valid_violations(model)
    )
