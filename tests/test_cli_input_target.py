# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native controls observe actual CLI source against independently authored intent."""

import ast
import copy
import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARD = "CLI-TYPED-CONTROL"


def _cli_contract():
    return copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/cli.json").read_text()))


def _cli_repository(tmp_path):
    source_root = ROOT / "src/archkeel"
    files = {
        path.relative_to(source_root.parent).as_posix(): path.read_text()
        for path in (source_root / "cli").glob("*.py")
    }
    facts = (source_root / "ir/facts.py").read_text()
    language = next(
        node
        for node in ast.parse(facts).body
        if isinstance(node, ast.ClassDef) and node.name == "Language"
    )
    files.update(
        {
            "archkeel/__init__.py": "",
            "archkeel/check/__init__.py": "",
            "archkeel/check/ports.py": "from ..ir.facts import Language as Language\n",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/facts.py": "from enum import StrEnum\n\n"
            + ast.get_source_segment(facts, language),
            "contract.json": json.dumps(_cli_contract()),
            "docs/architecture/cli-input-types.md": (
                ROOT / "docs/architecture/cli-input-types.md"
            ).read_text(),
        }
    )
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _guard(model, rule_id=GUARD):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == rule_id)


def test_native_cli_input_target_and_whole_module_guard_are_proven(tmp_path):
    root, config = _cli_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "report"\n',
        'def _probe(value):\n    return value in ("report", "validate")\n',
        (
            'def _probe(value):\n    match value:\n        case "report":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nREPORT: Final[str] = "report"\n'
            "\ndef _probe(value):\n    return value == REPORT\n"
        ),
    ],
    ids=["equality", "membership", "match", "final-string"],
)
def test_native_cli_guard_rejects_string_protocol_dispatch(tmp_path, probe):
    root, config = _cli_repository(tmp_path)
    contract = (root / "contract.json").read_bytes()
    source = root / "archkeel/cli/arguments.py"
    source.write_text(source.read_text() + "\n" + probe)
    model = _model(root, config)
    assert _guard(model).status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("arguments.py", "command: Command | None", "command: str | None"),
        ("arguments.py", "agent: InstallationAgent", "agent: str"),
        ("__init__.py", ") -> CLIArguments:", ") -> argparse.Namespace:"),
        (
            "arguments.py",
            "def report_mode(value: str) -> ReportMode:",
            "def report_mode(value: str) -> str:",
        ),
    ],
    ids=["command-field", "agent-field", "parser-return", "mode-return"],
)
def test_native_cli_source_widening_fails_with_target_unchanged(tmp_path, path, old, new):
    root, config = _cli_repository(tmp_path)
    contract = (root / "contract.json").read_bytes()
    source = root / "archkeel/cli" / path
    assert old in source.read_text()
    source.write_text(source.read_text().replace(old, new, 1))
    model = _model(root, config)
    assert (root / "contract.json").read_bytes() == contract
    comparison = architecture_report(model).comparison
    assert comparison is not None and any(row.status == "FAIL" for row in comparison.assessments)
    target_rule = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target_rule.status == "FAIL"
    assert any(target_rule.id in row.rule_ids for row in trace_valid_violations(model))


def test_own_native_cli_guard_covers_the_whole_package(self_observation):
    guard = _guard(self_observation, "cli:" + GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven, guard
    contract = _cli_contract()
    own_guard = next(rule for rule in contract["rules"] if rule["id"] == GUARD)
    assert own_guard["source"] == "archkeel.cli"
    assert not own_guard.get("exact_sources") and not own_guard.get("allowed_sources")

def test_native_cli_guard_accepts_owned_enums_and_path_data(tmp_path):
    root, config = _cli_repository(tmp_path)
    source = root / "archkeel/cli/arguments.py"
    source.write_text(
        source.read_text()
        + "\n\ndef _command_probe(value: Command) -> bool:\n"
        "    return value is Command.REPORT\n"
        "\n\ndef _path_probe(actual: str, expected: str) -> bool:\n"
        "    return actual == expected\n"
    )
    model = _model(root, config)
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not any(GUARD in row.rule_ids for row in trace_valid_violations(model))


def test_own_native_cli_target_pins_actual_closed_fields_and_parser(self_observation):
    comparison = architecture_report(self_observation).comparison
    assert comparison is not None
    for name, aspect in (
        ("CLIArguments.command", "annotation"),
        ("CLIArguments.only", "annotation"),
        ("CLIArguments.agent", "annotation"),
        ("CLIArguments.language", "annotation"),
        ("Parser.parse_args", "signature"),
    ):
        target_id = "cli:CLI-INPUT-" + name
        assert any(
            row.subject_id == target_id and row.aspect == aspect and row.status == "PASS"
            for row in comparison.assessments
        ), (target_id, aspect)
