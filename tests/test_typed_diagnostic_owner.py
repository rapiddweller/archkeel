# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Diagnostic identity, legacy wire behavior and independent native control evidence."""

import copy
import importlib
import json
from dataclasses import FrozenInstanceError
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import model
from archkeel.ir.codec_result import result_bytes, result_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
OWNER = "archkeel.ir.diagnostics"
NAMES = ("DiagnosticKind", "DiagnosticCode", "Diagnostic", "DiagnosticError", "ReportLocation")
SCHEMA = json.loads((ROOT / "schema/command-result.schema.json").read_text())["$defs"]["diagnostic"]


@pytest.mark.parametrize("name", NAMES)
def test_model_diagnostic_facades_keep_the_exact_owned_class_identity(name):
    path = ROOT / "src/archkeel/ir/diagnostics.py"
    assert path.exists(), "The coherent diagnostic owner has not been extracted"
    owner = importlib.import_module(OWNER)
    assert getattr(model, name) is getattr(owner, name)
    assert getattr(model, name).__module__ == OWNER


@pytest.mark.parametrize("kind", SCHEMA["properties"]["kind"]["enum"])
def test_every_existing_kind_normalizes_legacy_string_construction(kind):
    code = "rule.violated" if kind == "contract_invalid" else None
    diagnostic = model.Diagnostic(kind, "subject", "unknown claim", "Repair.", None, code)
    assert isinstance(diagnostic.kind, StrEnum)
    assert type(diagnostic.kind) is model.DiagnosticKind


@pytest.mark.parametrize("code", SCHEMA["properties"]["code"]["enum"])
def test_every_existing_code_normalizes_legacy_string_construction(code):
    diagnostic = model.Diagnostic("contract_invalid", "rule", "unknown", "Repair.", None, code)
    assert isinstance(diagnostic.code, StrEnum)
    assert type(diagnostic.code) is model.DiagnosticCode


def test_diagnostic_wire_bytes_and_legacy_locations_remain_exact():
    location = model.ReportLocation("src/a.py", 1)
    diagnostic = model.Diagnostic(
        "contract_invalid", "rule", "unknown", "Fix.", "/rules/0",
        "rule.violated", (location,), "contract.json"
    )
    result = model.RunResult("validate", 2, diagnostics=(diagnostic,))
    expected = (
        b'{"code":"rule.violated","contract_path":"contract.json","kind":"contract_invalid",'
        b'"locations":[{"line":1,"path":"src/a.py"}],"pointer":"/rules/0","remedy":"Fix.",'
        b'"subject":"rule","unknown_claim":"unknown"}'
    )
    assert expected in result_bytes(result)
    assert result_payload(result)["diagnostics"] == [json.loads(expected)]
    assert diagnostic.locations[0] is location
    error = model.DiagnosticError(diagnostic)
    assert error.diagnostic is diagnostic and str(error) == "unknown"
    with pytest.raises(FrozenInstanceError):
        diagnostic.kind = "parse_error"
    with pytest.raises(FrozenInstanceError):
        location.path = "other.py"


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        row for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-DIAGNOSTIC-")
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        row for row in root["rules"] if row["id"] == "DIAGNOSTIC-TYPED-CONTROL"
    ]
    return contract


def _repository(tmp_path):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(_contract()),
        "docs/architecture/typed-diagnostic-owner.md": "Owned diagnostic intent.\n",
    }
    owner = ROOT / "src/archkeel/ir/diagnostics.py"
    if owner.exists():
        files["archkeel/ir/diagnostics.py"] = owner.read_text()
    else:
        # RED observes the actual legacy declarations at their actual old owner.
        files["archkeel/ir/model.py"] = (
            "from __future__ import annotations\nfrom dataclasses import dataclass\n"
            "from typing import Literal, TypeAlias, get_args\n\n"
            + _source_members("src/archkeel/ir/model.py", set(NAMES))
        )
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None
    return comparison


def _assert_valid(value):
    assert _comparison(value).status == "PASS", _comparison(value)
    assert not trace_valid_violations(value)


def test_native_diagnostic_owner_matches_independent_intent_and_module_guard(tmp_path):
    root, config = _repository(tmp_path)
    assert len(_contract()["declarations"]["uml"]["entities"]) == 20
    _assert_valid(_model(root, config))


@pytest.mark.parametrize(
    "old,new",
    [
        ("kind: DiagnosticKind", "kind: str"),
        ("code: DiagnosticCode | None", "code: str | None"),
        (
            "def __init__(self, diagnostic: Diagnostic) -> None:",
            "def __init__(self, diagnostic: Diagnostic) -> str:",
        ),
    ],
    ids=["kind-field", "code-field", "exception-constructor-return"],
)
def test_native_diagnostic_widening_fails_with_fixed_authored_target(tmp_path, old, new):
    root, config = _repository(tmp_path)
    _assert_valid(_model(root, config))
    path = root / "archkeel/ir/diagnostics.py"
    source = path.read_text()
    assert old in source
    intent = (root / "contract.json").read_bytes()
    path.write_text(source.replace(old, new, 1))
    value = _model(root, config)
    assert any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in _comparison(value).assessments
    )
    assert trace_valid_violations(value)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "contract_invalid"\n',
        'def _probe(value):\n    return value in ("timeout", "parse_error")\n',
        'def _probe(value):\n    return "kind" in value\n',
        (
            'def _probe(value):\n    match value:\n        case "contract_invalid":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nTAG: Final[str] = "contract_invalid"\n'
            "\ndef _probe(value):\n    return value == TAG\n"
        ),
    ],
    ids=["equality", "membership", "protocol-key", "match", "final-alias"],
)
def test_native_diagnostic_owner_forbids_raw_control_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    _assert_valid(_model(root, config))
    path = root / "archkeel/ir/diagnostics.py"
    path.write_text(path.read_text() + "\n" + probe)
    value = _model(root, config)
    assert any(
        "DIAGNOSTIC-TYPED-CONTROL" in row.rule_ids for row in trace_valid_violations(value)
    )
