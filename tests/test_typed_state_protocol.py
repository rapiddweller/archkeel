# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""State wire compatibility and native controls use the real declarations."""

import copy
import json
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import state_facts
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import freeze_data, thaw_data
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.state_codec import parse_state_data, state_data
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARDS = ("STATE-FACTS-TYPED-CONTROL", "STATE-CODEC-TYPED-CONTROL")
FIELD_TYPES = {
    "binding": "BindingState",
    "referent_mutability": "ReferentMutability",
    "mutability": "ObjectMutability",
    "property_assignment": "PropertyAssignment",
}


def _wire():
    return {
        "classes": [
            {
                "qualified_name": "sample.Bag",
                "module": "sample",
                "frozen": False,
                "protocol": False,
                "methods": [],
                "evidence_ids": ["e"],
                "fields": [
                    {
                        "name": "value",
                        "annotation": "str",
                        "binding": "non_reassignable",
                        "referent_mutability": "mutable_container",
                        "mutability": "mutable",
                        "evidence_ids": ["e"],
                        "property_assignment": "unavailable",
                    }
                ],
            }
        ],
        "functions": [
            {
                "scope": "sample.run",
                "module": "sample",
                "class_owner": None,
                "receiver": None,
                "parameters": [],
                "events": [
                    {
                        "kind": "assignment",
                        "targets": ["ctx"],
                        "constructor": "Bag",
                        "annotation": None,
                        "alias": None,
                    },
                    {
                        "kind": "attribute",
                        "binding": "ctx",
                        "path": ["value"],
                        "access": "read",
                        "evidence_id": "e",
                    },
                    {
                        "kind": "attribute",
                        "binding": "ctx",
                        "path": ["value"],
                        "access": "write",
                        "evidence_id": "e",
                    },
                    {
                        "kind": "attribute",
                        "binding": "ctx",
                        "path": ["value", "append"],
                        "access": "mutation",
                        "evidence_id": "e",
                    },
                    {"kind": "pass", "binding": "ctx", "target": "consume", "evidence_id": "e"},
                ],
            }
        ],
    }


def test_state_wire_decodes_to_nominal_controls_without_changing_bytes_or_order():
    raw = _wire()
    facts = parse_state_data(freeze_data(raw))
    field = facts.classes[0].fields[0]
    for name in FIELD_TYPES:
        assert isinstance(getattr(field, name), StrEnum), (name, field)
    for event in facts.functions[0].events[1:4]:
        assert isinstance(event.access, StrEnum)
    assert thaw_data(state_data(facts)) == raw
    assert json.dumps(thaw_data(state_data(facts)), sort_keys=True) == json.dumps(
        raw, sort_keys=True
    )
    before = asdict(facts)
    assert parse_state_data(state_data(facts)) == facts
    assert asdict(facts) == before


def test_public_state_fields_own_nominal_annotations():
    fields = get_type_hints(state_facts.FieldState)
    for name, expected in FIELD_TYPES.items():
        actual = fields[name]
        if name == "property_assignment":
            actual = next(item for item in actual.__args__ if item is not type(None))
        assert isinstance(actual, type) and issubclass(actual, StrEnum), (name, actual)
        assert actual.__name__ == expected
    access = get_type_hints(state_facts.AttributeAccess)["access"]
    assert isinstance(access, type) and issubclass(access, StrEnum)
    assert access.__name__ == "StateAccess"


@pytest.mark.parametrize("field", list(FIELD_TYPES))
@pytest.mark.parametrize("invalid", ["invalid", 1, [], {}])
def test_state_parser_rejects_unknown_or_nontext_controls(field, invalid):
    raw = _wire()
    raw["classes"][0]["fields"][0][field] = invalid
    with pytest.raises(ValueError):
        parse_state_data(freeze_data(raw))


@pytest.mark.parametrize("invalid", ["invalid", None, 1, [], {}])
def test_state_parser_rejects_unknown_or_nontext_event_tags(invalid):
    raw = _wire()
    raw["functions"][0]["events"][0]["kind"] = invalid
    with pytest.raises(ValueError, match="event"):
        parse_state_data(freeze_data(raw))


@pytest.mark.parametrize(
    "path,access", [([], "read"), (["append"], "mutation"), (["x"], "invalid")]
)
def test_state_parser_keeps_access_path_constraints(path, access):
    raw = _wire()
    raw["functions"][0]["events"][1].update(path=path, access=access)
    with pytest.raises(ValueError):
        parse_state_data(freeze_data(raw))


def _state_contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["rules"] = []
    contract["declarations"]["uml"]["entities"] = [
        entity
        for entity in contract["declarations"]["uml"]["entities"]
        if entity["id"].startswith("IR-STATE-")
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [rule for rule in root["rules"] if rule["id"] in GUARDS]
    return contract


def _state_repository(tmp_path):
    facts = (
        "from __future__ import annotations\nfrom dataclasses import dataclass\n"
        "from typing import TypeAlias\n\n"
        + _source_members("src/archkeel/ir/facts.py", {"RecordData", "JsonValue"})
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/facts.py": facts,
        "archkeel/ir/state_facts.py": (ROOT / "src/archkeel/ir/state_facts.py").read_text(),
        "archkeel/ir/state_codec.py": (ROOT / "src/archkeel/ir/state_codec.py").read_text(),
        "contract.json": json.dumps(_state_contract()),
        "docs/architecture/typed-state-protocol.md": "State intent and native controls.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison(model):
    comparison = architecture_report(model).comparison
    assert comparison is not None
    return comparison


def test_native_state_api_and_parser_match_owned_target_and_guards(tmp_path):
    root, config = _state_repository(tmp_path)
    assert _state_contract()["declarations"]["uml"]["entities"]
    model = _model(root, config)
    assert _comparison(model).status == "PASS", _comparison(model)
    guards = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    for identifier in GUARDS:
        assert guards[identifier].status == "PASS" and guards[identifier].evaluation_proven
    assert not trace_valid_violations(model)


def test_native_state_control_widening_fails_with_unchanged_target(tmp_path):
    root, config = _state_repository(tmp_path)
    path = root / "archkeel/ir/state_facts.py"
    source = path.read_text()
    assert "binding: BindingState" in source
    path.write_text(source.replace("binding: BindingState", "binding: str", 1))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = _comparison(model)
    assert any(
        row.aspect == "annotation" and row.status == "FAIL" for row in comparison.assessments
    )
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "assignment"\n',
        'def _probe(value):\n    return value in ("assignment", "attribute")\n',
        (
            'def _probe(value):\n    match value:\n        case "assignment":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nASSIGNMENT: Final[str] = "assignment"\n'
            "\ndef _probe(value):\n    return value == ASSIGNMENT\n"
        ),
    ],
    ids=["equality", "membership", "match", "final-string"],
)
def test_native_state_parser_rejects_string_dispatch_without_parser_exemption(tmp_path, probe):
    root, config = _state_repository(tmp_path)
    path = root / "archkeel/ir/state_codec.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    violations = [row for row in trace_valid_violations(model) if GUARDS[1] in row.rule_ids]
    assert violations and all(
        row.data.get("construct") == "string_literal_compare" for row in violations
    )


def test_own_native_state_guards_cover_domain_and_codec(self_observation):
    assessments = {row.id: row for row in rule_assessments(self_observation, undecided_by_rule={})}
    for identifier in GUARDS:
        assert (
            assessments[identifier].status == "PASS" and assessments[identifier].evaluation_proven
        )
    assert not [
        row
        for row in self_observation.records("constructs")
        if row.kind == "string_literal_compare"
        and any(
            row.data.get("owner", "").startswith(module)
            for module in ("archkeel.ir.state_facts", "archkeel.ir.state_codec")
        )
    ]
