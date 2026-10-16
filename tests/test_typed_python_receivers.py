# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Receiver origins retain legacy inputs and conservative call evidence."""

import ast
import copy
import inspect
import json
from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python import receiver_types
from archkeel.analyzer.python.calls import _bind_receiver, _local_receiver_types, collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.receiver_types import ReceiverType
from archkeel.analyzer.python.resolve import _resolve_receiver_bound_call, build_symbol_index
from archkeel.analyzer.python.scopes import LexicalScopes
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
ORIGINS = ("literal", "annotation", "documented")


def _origin_type():
    annotation = get_type_hints(ReceiverType)["origin"]
    assert isinstance(annotation, type) and issubclass(annotation, Enum), annotation
    return annotation


def test_receiver_origin_field_and_existing_alias_are_nominal():
    assert receiver_types.Origin is _origin_type()


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_normalizes_valid_legacy_origins(raw):
    value = ReceiverType("arbitrary.QualifiedType", raw)
    assert isinstance(value.origin, _origin_type())
    assert value.origin.value == raw and value.type_name == "arbitrary.QualifiedType"


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_preserves_nominal_identity_and_immutability(raw):
    origin = _origin_type()(raw)
    value = ReceiverType("list", origin)
    assert value.origin is origin
    with pytest.raises(FrozenInstanceError):
        value.origin = origin


@pytest.mark.parametrize("raw", ["", "unknown", None, 7])
def test_receiver_constructor_rejects_invalid_origin(raw):
    with pytest.raises(ValueError):
        ReceiverType("list", raw)


def test_receiver_constructor_keeps_required_origin_parameter():
    assert inspect.signature(ReceiverType).parameters["origin"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        ReceiverType("list")


def test_actual_receiver_producers_publish_all_three_nominal_origins():
    module = _parsed_module(
        "from pathlib import Path\n"
        "def use(annotated: list[str]):\n"
        "    literal = []\n"
        "    documented = Path('value')\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    node = next(item for item in module.tree.body if isinstance(item, ast.FunctionDef))
    actual = _local_receiver_types(node, LexicalScopes(module))
    assert set(actual) == {"annotated", "literal", "documented"}
    assert all(isinstance(value.origin, _origin_type()) for value in actual.values())
    assert {name: value.origin.value for name, value in actual.items()} == {
        "annotated": "annotation", "literal": "literal", "documented": "documented"
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("literal", ("resolved", ["builtins.list.append"], "literal-bound receiver of known type", 1)),
        ("annotation", ("partially_resolved", ["builtins.list.append"], "annotated receiver of known type, unproven at runtime", 1)),
        ("documented", ("partially_resolved", ["builtins.list.append"], "receiver bound to a call result of documented type, unproven at runtime", 1)),
    ],
)
def test_legacy_origin_keeps_real_resolver_verdict_and_wire_values(raw, expected):
    assert _resolve_receiver_bound_call(["items", "append"], {"items": ReceiverType("list", raw)}) == expected


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("literal", "literal", "literal"), ("literal", "annotation", "literal"),
        ("literal", "documented", "literal"), ("annotation", "literal", "literal"),
        ("annotation", "annotation", "annotation"), ("annotation", "documented", "annotation"),
        ("documented", "literal", "literal"), ("documented", "annotation", "documented"),
        ("documented", "documented", "documented"),
    ],
)
def test_legacy_origin_merge_keeps_existing_evidence_preference(first, second, expected):
    values = {"items": ReceiverType("list", first)}
    _bind_receiver(values, "items", ReceiverType("list", second))
    result = values["items"]
    assert result is not None
    origin = result.origin.value if isinstance(result.origin, Enum) else result.origin
    assert origin == expected


def test_actual_receiver_merge_has_no_raw_origin_dispatch(tmp_path):
    result = _observe_one_rule(
        tmp_path,
        {"kind": "forbidden_construct", "source": "sample.core", "constructs": ["string_literal_compare"]},
        {"core.py": (ROOT / "src/archkeel/analyzer/python/calls.py").read_text()},
    )
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == "sample.core._bind_receiver"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "def use():\n    items = []\n    items = {}\n    items.append(1)\n",
        "def use(list):\n    items = list()\n    items.append(1)\n",
        "def use():\n    items = []\n    for items in (): pass\n    items.append(1)\n",
    ],
)
def test_ambiguous_and_shadowed_receivers_stay_unresolved(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "items.append")
    assert call["status"] == "unresolved" and call["targets"] == []


def _receiver_repository(tmp_path):
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/python.json").read_text()))
    contract.pop("$schema", None)
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [rule for rule in root_contract["rules"] if rule["id"] == "PYTHON-RECEIVERS-TYPED-CONTROL"]
    contract["declarations"]["uml"]["entities"] = [
        item for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith("PYTHON-RECEIVER-")
    ]
    files = {
        "archkeel/__init__.py": "", "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "archkeel/analyzer/python/receiver_types.py": (ROOT / "src/archkeel/analyzer/python/receiver_types.py").read_text(),
        "contract.json": json.dumps(contract),
        "docs/architecture/typed-python-receivers.md": "Owned receiver origins.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_receiver_api_fulfils_owned_origin_target_and_module_guard(tmp_path):
    root, config = _receiver_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessment = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == "PYTHON-RECEIVERS-TYPED-CONTROL")
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert not trace_valid_violations(model)


def test_native_receiver_origin_widening_fails_unchanged_target(tmp_path):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    source = path.read_text()
    assert "origin: ReceiverOrigin" in source
    path.write_text(source.replace("origin: ReceiverOrigin", "origin: str", 1))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assert any(item.aspect == "annotation" and item.status == "FAIL" for item in comparison.assessments)
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "literal"\n',
        'def _probe(value):\n    return value in ("literal", "annotation")\n',
        "def _probe(value):\n    return value == ReceiverOrigin.LITERAL.value\n",
    ],
)
def test_native_receiver_model_rejects_raw_origin_dispatch(tmp_path, probe):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [row for row in trace_valid_violations(model) if "PYTHON-RECEIVERS-TYPED-CONTROL" in row.rule_ids]
