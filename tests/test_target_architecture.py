# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the compact target without weakening missing-evidence controls."""

import json
from pathlib import Path

import jsonschema
import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import requires_covers

ROOT = Path(__file__).parents[1]
CONTRACTS = [
    ROOT / "architecture-contract.json",
    *sorted((ROOT / "docs/architecture/contracts").glob("*.json")),
]


@pytest.mark.parametrize("path", CONTRACTS, ids=lambda path: path.stem)
def test_target_contract_schema_roundtrip_and_closed_owners(path):
    raw = json.loads(path.read_bytes())
    jsonschema.validate(raw, json.loads((ROOT / "schema" / Path(raw["$schema"]).name).read_bytes()))
    encoded = contract_bytes(parse_contract(raw))
    assert encoded == contract_bytes(parse_contract(json.loads(encoded)))
    assert {
        "complete_assignment",
        "complete_requires",
        "interface_boundary",
        "no_component_cycles",
    } <= {rule["kind"] for rule in raw["rules"]}


@pytest.mark.parametrize(
    "module,symbol,allowed",
    [
        ("archkeel.ir.codec", "decode_json", True),
        ("archkeel.ir.codec", "result_bytes", False),
        ("archkeel.ir.codec", None, False),
        ("archkeel.ir.command_view", "decode_json", False),
    ],
)
def test_report_reader_permission_is_symbol_specific(module, symbol, allowed):
    contract = parse_contract(json.loads(CONTRACTS[0].read_bytes()))
    api = next(component for component in contract.components if component.label == "api")
    assert requires_covers(api, "ir", module, symbol) is allowed


@pytest.mark.parametrize(
    "case,expected",
    [
        ("allowed", "PASS"),
        ("forbidden", "FAIL"),
        ("missing_target", "UNKNOWN"),
        ("missing_source", "UNKNOWN"),
    ],
)
def test_onboarding_dependency_uses_exact_modules_and_real_source_evidence(
    tmp_path, case, expected
):
    raw = json.loads((ROOT / "docs/architecture/contracts/check.json").read_bytes())
    rule = next(
        rule for rule in raw["rules"] if rule["id"] == "CHECK-ONBOARDING-NO-REPORT-IMPLEMENTATION"
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/check/onboarding.py": (
            "from archkeel.check.report import observe_repository\n"
            if case == "forbidden"
            else "from archkeel.check.ports import ScanConfig\n"
        ),
        "archkeel/check/ports.py": "class ScanConfig: pass\n",
        "archkeel/check/report.py": "def observe_repository(): pass\n",
        # Another command must not be captured by expansion to the whole owner pair.
        "archkeel/check/run.py": "from archkeel.check.report import observe_repository\n",
        "docs/architecture/target/design.md": "Independent command responsibilities.\n",
        "intent.json": json.dumps(
            {
                "schema_version": raw["schema_version"],
                "components": raw["components"],
                "rules": [rule],
            }
        ),
    }
    if case == "missing_target":
        del files["archkeel/check/report.py"]
    if case == "missing_source":
        del files["archkeel/check/onboarding.py"]
    root = _prepare_repo(tmp_path, files)
    result, artifact = run_report(
        root,
        config=ScanConfig(("archkeel",), "archkeel", "intent.json", "0" * 64),
        analyzer=observe,
    )
    assert artifact is not None, result.diagnostics
    row = next(row for row in result.rule_assessments if row.id == rule["id"])
    assert row.status == expected
