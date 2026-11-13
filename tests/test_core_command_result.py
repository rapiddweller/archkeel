# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nominal Core result controls preserve independent schema and native intent."""

import ast
import copy
import importlib
import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Literal, get_args, get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_result_schema import _validator

from archkeel.check.ports import ScanConfig
from archkeel.cli import legacy_bindings as cli
from archkeel.cli import main
from archkeel.ir import model
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.codec_result import result_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
MEMBERS = {"Command", "ExpectationOutcome", "RunResult"}
GUARD = "CORE-RESULT-SELECTED-CONTROL"


def test_command_has_one_core_owner_and_cli_keeps_identical_class():
    assert hasattr(model, "Command"), "RunResult has no canonical Core command owner"
    command = model.Command
    assert command is importlib.import_module("archkeel.cli.arguments").Command
    assert command.__module__ == "archkeel.ir.model"


def test_run_result_annotations_use_distinct_precise_nominal_domains():
    hints = get_type_hints(
        model.RunResult, globalns={**vars(model), "ArchitectureProjection": ArchitectureProjection}
    )
    assert hasattr(model, "Command") and hints["command"] is model.Command
    assert hints["observation_complete"] == Literal[AssessmentStatus.PASS, AssessmentStatus.UNKNOWN]
    assert set(get_args(hints["observation_complete"])) == {
        AssessmentStatus.PASS,
        AssessmentStatus.UNKNOWN,
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
        command,
        2,
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
    assert main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == failure
    assert payload["exit_code"] == 2
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["expectation_fulfilled"] == "UNKNOWN"


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        row
        for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-RESULT-")
        or row["id"]
        in {"IR-DEPENDENCY-model", "IR-GRAPH-RunResult", "IR-GRAPH-RunResult.declared_rules"}
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    contract["rules"] = [
        {
            "id": GUARD,
            "kind": "forbidden_construct",
            "source": "archkeel.ir.model",
            "constructs": ["string_literal_compare"],
            "rationale": "Protect the actual selected Core declarations in this fixture.",
            "provenance": ["docs/architecture/core-command-result-types.md"],
            "decided_by": "architect",
        }
    ]
    return contract


def _repository(tmp_path):
    source = (ROOT / "src/archkeel/ir/architecture_graph.py").read_text()
    assessment = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "AssessmentStatus"
    )
    model_source = (
        "from __future__ import annotations\nimport builtins\nfrom dataclasses import dataclass\n"
        "from typing import Literal\nfrom enum import StrEnum\n"
        "from .architecture_graph import AssessmentStatus as AssessmentStatus\n\n"
        + _source_members("src/archkeel/ir/model.py", MEMBERS)
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/model.py": model_source,
        "archkeel/ir/architecture_graph.py": "from enum import StrEnum\n\n"
        + ast.get_source_segment(source, assessment),
        "contract.json": json.dumps(_contract()),
        "docs/architecture/core-command-result-types.md": "Selected Core API intent.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(value)


@pytest.mark.parametrize("declared", ["PASS", "FAIL", "UNKNOWN"])
def test_result_declared_rules_normalizes_legacy_values_at_its_real_ingress(declared):
    result = model.RunResult("report", 0, declared_rules=declared)
    assert result.declared_rules is AssessmentStatus(declared)
    assert result_payload(result)["declared_rules"] == declared


@pytest.mark.parametrize("invalid", ["DECLARATION", "invalid", None, 1])
def test_result_declared_rules_rejects_values_outside_its_closed_domain(invalid):
    with pytest.raises(ValueError):
        model.RunResult("report", 0, declared_rules=invalid)


RESULT_GUARDS = {
    "IR-RESULT-ASSESSMENT-CONTROL": "archkeel.ir.model.RunResult",
    "RENDER-RULE-LEGEND-CONTROL": "archkeel.render.html._atlas_rule_counts",
    "RENDER-REPORT-FAILURE-CONTROL": "archkeel.render.summary.report_violates_rules",
    "RENDER-REPORT-UNKNOWN-CONTROL": "archkeel.render.summary.report_leaves_rules_undecided",
    "RENDER-RESULT-BADGE-CONTROL": "archkeel.render.summary._decision_badge",
}


def _owned_result_rules():
    return [
        rule
        for name in ("ir", "render")
        for rule in json.loads((ROOT / f"docs/architecture/contracts/{name}.json").read_text())[
            "rules"
        ]
        if rule["id"] in RESULT_GUARDS
    ]


def _result_guard_repository(tmp_path):
    rules = _owned_result_rules()
    assert {rule["id"]: rule["source"] for rule in rules} == RESULT_GUARDS
    root, config = _repository(tmp_path)
    contract = {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "RESULT-CONTROLS",
                "label": "controls",
                "role": "component",
                "packages": ["archkeel"],
                "responsibilities": ["Own the actual result control fixture."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/core-command-result-types.md"],
                "decided_by": "architect",
            }
        ],
        "rules": rules,
    }
    (root / "contract.json").write_text(json.dumps(contract))
    graph = root / "archkeel/ir/architecture_graph.py"
    graph.write_text(
        graph.read_text()
        + "\n\n"
        + _source_members("src/archkeel/ir/architecture_graph.py", {"RuleAssessmentStatus"})
    )
    render = root / "archkeel/render"
    render.mkdir()
    (render / "__init__.py").write_text("")
    (render / "html.py").write_text(
        "from archkeel.ir.architecture_graph import RuleAssessmentStatus\n"
        "from archkeel.ir.model import RunResult\n\n"
        + _source_members("src/archkeel/render/html.py", {"_atlas_rule_counts"})
    )
    (render / "summary.py").write_text(
        "from archkeel.ir.model import AssessmentStatus as _AssessmentStatus\n"
        "from archkeel.ir.model import Command as _Command\n"
        "from archkeel.ir.model import RunResult\n\n"
        + _source_members(
            "src/archkeel/render/summary.py",
            {"report_violates_rules", "report_leaves_rules_undecided", "_decision_badge"},
        )
    )
    return root, config
