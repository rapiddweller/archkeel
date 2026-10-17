# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep call-count directions narrow and terminal rule decisions nominal."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal, get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import model
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.summary import _call_site_lines

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/unresolved-call-change-types.md"
GUARDS = {
    "CALL-CHANGE-VALIDATION-FILTER",
    "CALL-CHANGE-VALIDATION-SIDES",
    "CALL-CHANGE-SUMMARY",
    "TERMINAL-RULE-ASSESSMENT-CONTROL",
}


def _change(raw):
    return model.UnresolvedCallChange(raw, "app.run", "handle", "dynamic", "app", "app.py", (3,), 0, 1)


def test_existing_direction_port_is_a_nominal_two_member_subset():
    kind = model.KnownSemanticChangeKind
    assert get_type_hints(model.UnresolvedCallChange)["change"] == Literal[kind.ADDED, kind.REMOVED]


@pytest.mark.parametrize("raw", ["added", "removed"])
def test_supported_legacy_directions_normalize_once_and_keep_json(raw):
    row = _change(raw)
    assert row.change is model.KnownSemanticChangeKind(raw)
    assert json.loads(json.dumps(asdict(row)))["change"] == raw


@pytest.mark.parametrize("raw", ["changed", "relocated", "future", "", None, 1])
def test_other_semantic_actions_and_invalid_values_cannot_enter_the_narrow_port(raw):
    with pytest.raises((TypeError, ValueError)):
        _change(raw)


def test_actual_summary_preserves_counts_signs_and_output_for_legacy_inputs():
    result = model.RunResult(
        "validate", 1, failures=("budget",),
        unresolved_call_changes=(_change("added"), _change("removed")),
    )
    assert _call_site_lines(result) == (
        "Unresolved call sites: 1 added, 1 removed",
        "  + app.py:3 app.run: handle() [app] dynamic",
        "  - app.py:3 app.run: handle() [app] dynamic",
    )


def _repository(tmp_path, mutation=None):
    contracts = [
        json.loads((ROOT / f"docs/architecture/contracts/{part}.json").read_text())
        for part in ("ir", "check", "render")
    ]
    target = contracts[0]
    target.pop("$schema", None)
    entities = [
        dict(item) for item in target["declarations"]["uml"]["entities"]
        if item["id"].startswith("CALL-CHANGE-") or item["id"] == "IR-DEPENDENCY-model"
    ]
    assert len(entities) == 3, "actual call direction needs authored field intent"
    for item in entities:
        if item["kind"] == "module":
            item.pop("parent_id", None)
    target["components"] = [dict(
        id="core", label="core", role="component", packages=["archkeel"],
        responsibilities=["Consume the actual owned call and rule controls."],
        forbidden_responsibilities=[], provenance=[DOC], public=["archkeel"],
    )]
    target["rules"] = [rule for contract in contracts for rule in contract["rules"] if rule["id"] in GUARDS]
    assert {rule["id"] for rule in target["rules"]} == GUARDS
    target["declarations"] = {
        "uml": {"schema_version": "1.0.0", "entities": entities, "relationships": [], "scopes": []}
    }
    prefix = "from __future__ import annotations\n"
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/render/__init__.py": "",
        "archkeel/ir/model.py": prefix
        + "import builtins\nfrom dataclasses import dataclass\nfrom enum import StrEnum\n"
        + "from typing import Literal, TypeAlias\n"
        + _source_members("src/archkeel/ir/model.py", {"KnownSemanticChangeKind", "CallChangeKind", "UnresolvedCallChange"}),
        "archkeel/check/validation/__init__.py": prefix
        + "from archkeel.ir.model import KnownSemanticChangeKind as _KnownSemanticChangeKind\n"
        + _source_members("src/archkeel/check/validation/__init__.py", {"_unresolved_calls_since", "_one_sided_paths"}),
        "archkeel/render/summary.py": prefix
        + "from archkeel.ir.model import KnownSemanticChangeKind as _KnownSemanticChangeKind\n"
        + _source_members("src/archkeel/render/summary.py", {"_call_site_lines"}),
        "archkeel/render/terminal.py": prefix
        + "from archkeel.ir.model import RuleAssessmentStatus as _RuleAssessmentStatus\n"
        + _source_members("src/archkeel/render/terminal.py", {"print_result"}),
        "contract.json": json.dumps(target),
        DOC: (ROOT / DOC).read_text(),
        "docs/architecture/dependency-selector-target.md": "Model compatibility owner.\n",
    }
    if mutation:
        path, old, new = mutation
        assert files[path].count(old) == 1, "mutate exactly one actual control or field"
        files[path] = files[path].replace(old, new)
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(observation):
    comparison = architecture_report(observation).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    selected = {row.id: row for row in rule_assessments(observation, undecided_by_rule={}) if row.id in GUARDS}
    assert set(selected) == GUARDS
    assert all(row.status == "PASS" and row.evaluation_proven for row in selected.values())
    assert not trace_valid_violations(observation)


def test_native_actual_direction_field_and_all_four_consumers_meet_fixed_intent(tmp_path):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))


def test_native_actual_direction_field_weakening_fails_unchanged_target(tmp_path):
    root, config = _repository(tmp_path, ("archkeel/ir/model.py", "change: CallChangeKind", "change: str"))
    before = (root / "contract.json").read_bytes()
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize("path,old,new,guard", [
    ("archkeel/check/validation/__init__.py", "item.change is _KnownSemanticChangeKind.REMOVED", 'item.change == "removed"', "CALL-CHANGE-VALIDATION-FILTER"),
    ("archkeel/check/validation/__init__.py", "item.change is _KnownSemanticChangeKind.ADDED", 'item.change == "added"', "CALL-CHANGE-VALIDATION-SIDES"),
    ("archkeel/render/summary.py", "sum(item.change is _KnownSemanticChangeKind.ADDED", 'sum(item.change == "added"', "CALL-CHANGE-SUMMARY"),
    ("archkeel/render/terminal.py", "item.status is _RuleAssessmentStatus.UNKNOWN", 'item.status == "UNKNOWN"', "TERMINAL-RULE-ASSESSMENT-CONTROL"),
])
def test_native_actual_consumer_raw_regression_fails_unchanged_guard(tmp_path, path, old, new, guard):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    root, config = _repository(tmp_path / "mutated", (path, old, new))
    before = (root / "contract.json").read_bytes()
    assert any(guard in row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == before
