# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Diagnostic identity, legacy wire behavior and independent native control evidence."""

import ast
import copy
import importlib
import json
from dataclasses import FrozenInstanceError
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir import model
from archkeel.ir.codec import decode_canonical_model, parse_observation
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
        "contract_invalid",
        "rule",
        "unknown",
        "Fix.",
        "/rules/0",
        "rule.violated",
        (location,),
        "contract.json",
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
        row
        for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-DIAGNOSTIC-")
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [row for row in root["rules"] if row["id"] == "DIAGNOSTIC-TYPED-CONTROL"]
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


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    return parse_observation(decode_canonical_model(json.loads(encoded)))


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
        ("    diagnostic: Diagnostic\n", "    diagnostic: str\n"),
        (
            "def __init__(self, diagnostic: Diagnostic) -> None:",
            "def __init__(self, diagnostic: str) -> None:",
        ),
        (
            "def __init__(self, diagnostic: Diagnostic) -> None:",
            "def __init__(self, diagnostic: Diagnostic) -> str:",
        ),
    ],
    ids=[
        "kind-field",
        "code-field",
        "exception-diagnostic-field",
        "exception-constructor-parameter",
        "exception-constructor-return",
    ],
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
    assert any("DIAGNOSTIC-TYPED-CONTROL" in row.rule_ids for row in trace_valid_violations(value))


def _diagnostic_imports(path):
    """Project only real diagnostic import declarations, preserving their actual routes."""
    source = (ROOT / path).read_text()
    declarations = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom):
            names = [alias for alias in node.names if alias.name in NAMES]
            if names:
                declarations.append(
                    ast.unparse(ast.ImportFrom(module=node.module, names=names, level=node.level))
                )
    return "\n".join(declarations) + "\n"


def test_existing_public_diagnostic_reexports_reach_the_canonical_owner(tmp_path):
    root, config = _repository(tmp_path)
    paths = (
        "src/archkeel/ir/model.py",
        "src/archkeel/check/report.py",
        "src/archkeel/render/html.py",
        "src/archkeel/render/terminal.py",
    )
    for source in paths:
        target = root / source.removeprefix("src/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_diagnostic_imports(source))
    # Existing public functions give both boundary policies real signature subjects.
    git = root / "archkeel/check/git.py"
    git.write_text(
        "from pathlib import PurePosixPath\n\n"
        + _source_members("src/archkeel/check/git.py", {"relative_path"})
    )
    terminal = root / "archkeel/render/terminal.py"
    terminal.write_text(
        terminal.read_text()
        + "from collections.abc import Iterator\n\n"
        + _source_members("src/archkeel/render/terminal.py", {"progress"})
    )
    for package in ("check", "render"):
        (root / "archkeel" / package / "__init__.py").write_text("")
    contract = _contract()
    contract["components"].append(
        {
            "id": "DIAGNOSTIC-CONSUMER",
            "label": "consumer",
            "role": "component",
            "packages": ["archkeel.check", "archkeel.render"],
            "public": [
                "archkeel.check.report:Diagnostic",
                "archkeel.check.report:DiagnosticError",
                "archkeel.check.report:ReportLocation",
                "archkeel.render.html:Diagnostic",
                "archkeel.render.terminal:Diagnostic",
                "archkeel.render.terminal:progress",
                "archkeel.check.git:relative_path",
            ],
            "responsibilities": ["Retain existing public diagnostic names with clear owned types."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/typed-diagnostic-owner.md"],
        }
    )
    for source in ("archkeel.check", "archkeel.render"):
        contract["rules"].append(
            {
                "id": "DIAGNOSTIC-PUBLIC-" + source.rsplit(".", 1)[-1],
                "kind": "boundary_types",
                "source": source,
                "rationale": "Resolve existing diagnostic names to their canonical owner.",
                "provenance": ["docs/architecture/typed-diagnostic-owner.md"],
                "decided_by": "architect",
            }
        )
    (root / "contract.json").write_text(json.dumps(contract))
    value = _model(root, config)
    unknown = tuple(
        row
        for row in value.records("unknowns") or ()
        if any(identity.startswith("DIAGNOSTIC-PUBLIC-") for identity in row.rule_ids)
    )
    details = [
        {
            "kind": row.kind,
            "qualified_name": row.data.get("qualified_name"),
            "reason": row.data.get("reason"),
        }
        for row in unknown
    ]
    print("PUBLIC_ROUTE_UNKNOWN_JSON=" + json.dumps(details))
    assert not unknown, details
    assert not trace_valid_violations(value)
