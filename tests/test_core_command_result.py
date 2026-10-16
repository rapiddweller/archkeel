# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nominal Core result controls preserve independent schema and native intent."""

import ast
import copy
import importlib
import json
import sys
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Literal, get_args, get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_result_schema import _validator
from test_uml_evaluation import _model

from archkeel import cli
from archkeel.ir import model
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.codec_result import result_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations
from archkeel.check.ports import ScanConfig

ROOT = Path(__file__).parents[1]
MEMBERS = {"Command", "ExpectationOutcome", "RunResult"}
GUARD = "CORE-RESULT-SELECTED-CONTROL"


def test_command_has_one_core_owner_and_cli_keeps_identical_class():
    assert hasattr(model, "Command"), "RunResult has no canonical Core command owner"
    command = model.Command
    assert command is importlib.import_module("archkeel.cli.arguments").Command
    assert command.__module__ == "archkeel.ir.model"
    assert [(item.name, str(item)) for item in command] == [
        ("REPORT", "report"), ("VALIDATE", "validate"), ("CHECK", "check"),
        ("INIT", "init"), ("SKILL", "skill"), ("ARGUMENTS", "arguments"),
    ]


def test_run_result_annotations_use_distinct_precise_nominal_domains():
    hints = get_type_hints(model.RunResult)
    assert hasattr(model, "Command") and hints["command"] is model.Command
    assert hints["observation_complete"] == Literal[AssessmentStatus.PASS, AssessmentStatus.UNKNOWN]
    assert set(get_args(hints["observation_complete"])) == {
        AssessmentStatus.PASS, AssessmentStatus.UNKNOWN
    }
    assert hasattr(model, "ExpectationOutcome")
    assert hints["expectation_fulfilled"] is model.ExpectationOutcome
    assert [str(item) for item in model.ExpectationOutcome] == ["PASS", "FAIL", "UNKNOWN", "n/a"]
    assert hints["git_predicate"] == model.Verdict | None
    assert hints["host_order"] == model.Verdict | None


@pytest.mark.parametrize("command", ["report", "validate", "check", "init", "skill", "arguments"])
def test_valid_legacy_result_constructor_normalizes_once_and_preserves_wire(command):
    result = model.RunResult(command, 0, observation_complete="PASS", expectation_fulfilled="n/a")
    assert type(result.command) is getattr(model, "Command", None)
    assert result.observation_complete is AssessmentStatus.PASS
    assert type(result.expectation_fulfilled) is getattr(model, "ExpectationOutcome", None)
    assert isinstance(result.command, StrEnum)
    payload = result_payload(result)
    assert payload["command"] == command
    assert payload["observation_complete"] == "PASS"
    assert payload["expectation_fulfilled"] == "n/a"


def test_observation_completion_cannot_inherit_fail_from_broader_assessment():
    with pytest.raises(ValueError):
        model.RunResult("report", 0, observation_complete=AssessmentStatus.FAIL)


def test_free_contract_shell_command_does_not_become_dispatch_vocabulary():
    assert get_type_hints(model.ContractCommand)["command"] is str


@pytest.mark.parametrize("command", ["skill", "arguments"])
def test_published_command_result_subset_stays_four_values_and_rejects_cli_failure_tags(command):
    schema = json.loads((ROOT / "schema/command-result.schema.json").read_text())
    assert schema["properties"]["command"]["enum"] == ["init", "check", "validate", "report"]
    result = model.RunResult(
        command, 2,
        diagnostics=(model.Diagnostic("parse_error", "arguments", "invalid", "Repair."),),
    )
    payload = result_payload(result)
    assert payload["command"] == command
    errors = list(_validator("command-result.schema.json").iter_errors(payload))
    assert any(list(error.path) == ["command"] for error in errors)


@pytest.mark.parametrize("failure", ["arguments", "skill"])
def test_actual_cli_error_context_keeps_legacy_wire_tag(tmp_path, monkeypatch, capsys, failure):
    if failure == "arguments":
        argv = ["archkeel", "--not-an-option"]
    else:
        argv = ["archkeel", "skill", "install", "codex", "--root", str(tmp_path)]
        def fail_install(*args, **kwargs):
            raise ValueError("installation cannot complete")
        monkeypatch.setattr(cli, "install_skill", fail_install)
    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == failure
    assert payload["exit_code"] == 2
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["expectation_fulfilled"] == "UNKNOWN"


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        row for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-RESULT-")
        or row["id"] in {"IR-DEPENDENCY-model", "IR-GRAPH-RunResult"}
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    contract["rules"] = [{
        "id": GUARD, "kind": "forbidden_construct", "source": "archkeel.ir.model",
        "constructs": ["string_literal_compare"],
        "rationale": "Protect only actual selected Core declarations in this source-backed fixture.",
        "provenance": ["docs/architecture/core-command-result-types.md"],
        "decided_by": "architect",
    }]
    return contract


def _repository(tmp_path):
    source = (ROOT / "src/archkeel/ir/architecture_graph.py").read_text()
    assessment = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "AssessmentStatus"
    )
    model_source = (
        "from __future__ import annotations\nimport builtins\nfrom dataclasses import dataclass\n"
        "from typing import Literal\nfrom enum import StrEnum\n"
        "from .architecture_graph import AssessmentStatus as AssessmentStatus\n\n"
        + _source_members("src/archkeel/ir/model.py", MEMBERS)
    )
    files = {
        "archkeel/__init__.py": "", "archkeel/ir/__init__.py": "",
        "archkeel/ir/model.py": model_source,
        "archkeel/ir/architecture_graph.py":
            "from enum import StrEnum\n\n" + ast.get_source_segment(source, assessment),
        "contract.json": json.dumps(_contract()),
        "docs/architecture/core-command-result-types.md": "Selected Core API intent.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(value)


def test_native_selected_core_source_matches_seven_independent_target_entities(tmp_path):
    root, config = _repository(tmp_path)
    assert len(_contract()["declarations"]["uml"]["entities"]) == 7
    _valid(_model(root, config))


@pytest.mark.parametrize("old,new", [
    ("command: Command", "command: str"),
    ("observation_complete: Literal[AssessmentStatus.PASS, AssessmentStatus.UNKNOWN]",
     "observation_complete: AssessmentStatus"),
    ("expectation_fulfilled: ExpectationOutcome", "expectation_fulfilled: str"),
    ("class Command(StrEnum):", "class Command(str):"),
    ("class ExpectationOutcome(StrEnum):", "class ExpectationOutcome(str):"),
])
def test_native_field_widening_and_enum_substitution_fail_fixed_target(tmp_path, old, new):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir/model.py"
    content = source.read_text()
    assert old in content
    intent = (root / "contract.json").read_bytes()
    source.write_text(content.replace(old, new, 1))
    value = _model(root, config)
    comparison = architecture_report(value).comparison
    assert any(row.status == "FAIL" for row in comparison.assessments)
    assert trace_valid_violations(value)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize("probe", [
    'def _probe(value):\n    return value == "report"\n',
    'def _probe(value):\n    return value in ("PASS", "UNKNOWN")\n',
    'def _probe(value):\n    return "command" in value\n',
    'def _probe(value):\n    match value:\n        case "n/a":\n'
    '            return True\n        case _:\n            return False\n',
    'from typing import Final\nTAG: Final[str] = "report"\n'
    'def _probe(value):\n    return value == TAG\n',
])
def test_native_selected_core_projection_rejects_raw_control_mutations(tmp_path, probe):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir/model.py"
    source.write_text(source.read_text() + "\n" + probe)
    value = _model(root, config)
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(value))
