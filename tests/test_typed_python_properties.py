# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Property domain types preserve existing descriptor proof and wire data."""

import ast
import copy
import json
from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_inherited_properties import _property, _validate
from test_uml_evaluation import _model

from archkeel.analyzer.python import source
from archkeel.analyzer.python.collect import collect
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts, facts_codec
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
WIRE = {"operation": "setter", "source": "local", "line": 6, "source_line": 4}


def _api():
    binding = getattr(facts, "PropertyBinding", None)
    assert binding is not None, "source facts needs the shared PropertyBinding owner"
    return binding


@pytest.mark.parametrize(
    "field,name", [("operation", "PropertyOperation"), ("source", "PropertyOrigin")]
)
def test_consumed_property_fields_are_owned_nominal_enums(field, name):
    binding = _api()
    annotation = get_type_hints(binding)[field]
    assert annotation is getattr(facts, name)
    assert issubclass(annotation, Enum) and not issubclass(annotation, str)


@pytest.mark.parametrize("mapping", [False, True])
def test_legacy_raw_property_constructor_preserves_dict_operations(mapping):
    raw = source._PropertyBinding(WIRE) if mapping else source._PropertyBinding(**WIRE)
    assert type(raw) is dict and raw == WIRE
    assert {**raw} == WIRE and raw["operation"] == "setter"
    assert json.loads(json.dumps(raw)) == WIRE


def test_property_decoder_reads_raw_mapping_and_immutable_record_identically():
    binding = _api()
    raw = source._PropertyBinding(**WIRE)
    decoded = facts.property_binding(raw)
    immutable = facts.property_binding(facts_codec.freeze_data(raw))
    assert type(decoded) is binding and decoded == immutable
    assert decoded.operation is facts.PropertyOperation.SETTER
    assert decoded.source is facts.PropertyOrigin.LOCAL
    assert facts_codec.property_binding_data(decoded) == raw
    assert json.dumps(facts_codec.property_binding_data(decoded)) == json.dumps(raw)
    with pytest.raises(FrozenInstanceError):
        decoded.line = 9


@pytest.mark.parametrize(
    "update",
    [
        {"operation": "deleter"},
        {"source": "unknown"},
        {"line": True},
        {"line": 0},
        {"source_line": -1},
        {"source_line": 6},
        {"source_line": "4"},
        {"source": "new"},
        {"operation": "create"},
        {"extra": True},
    ],
)
def test_shared_property_decoder_rejects_invalid_wire(update):
    _api()
    raw = WIRE | update
    with pytest.raises(ValueError):
        facts.property_binding(raw)
    with pytest.raises(ValueError):
        facts.property_binding(facts_codec.freeze_data(raw))


def test_actual_property_source_produces_nominal_local_and_base_operations():
    binding_type = _api()
    module = _parsed_module(
        "class Base:\n"
        "    @property\n    def value(self) -> int: ...\n"
        "    @value.setter\n    def value(self, value: int) -> None: ...\n"
        "class Child(Base):\n"
        "    @Base.value.getter\n    def value(self) -> int: ...\n"
    )
    bindings = [
        binding
        for owner in module.tree.body
        if isinstance(owner, ast.ClassDef)
        for binding in source.property_bindings(module, owner).values()
    ]
    assert all(type(binding) is binding_type for binding in bindings)
    assert [(item.operation.value, item.source.value) for item in bindings] == [
        ("create", "new"),
        ("setter", "local"),
        ("getter", "base"),
    ]


@pytest.mark.parametrize(
    "filename,scope",
    [
        ("analyzer/python/source.py", "_property_operation"),
        ("analyzer/python/source.py", "setter_local_references"),
        ("check/evaluation/boundary_types.py", "_property_chains"),
        ("check/evaluation/boundary_types.py", "_apply_property_methods"),
    ],
)
def test_actual_property_functions_have_no_raw_operation_dispatch(tmp_path, filename, scope):
    # Whole modules retain other pending grammars; only these actual scopes are asserted.
    owner = f"sample.core.{scope}"
    result = _observe_one_rule(
        tmp_path,
        {
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["string_literal_compare"],
        },
        {"core.py": (ROOT / "src/archkeel" / filename).read_text()},
    )
    assert result.diagnostics == () and result.observation is not None
    # Record-kind control and wire-key presence remain separate grammars. Native
    # evidence is restricted to property value comparisons or enum-value extraction.
    vocabulary = {"create", "getter", "setter", "new", "local", "base"}
    property_lines = {
        node.lineno
        for node in ast.walk(ast.parse((ROOT / "src/archkeel" / filename).read_text()))
        if isinstance(node, ast.Compare)
        and any(
            (isinstance(child, ast.Constant) and isinstance(child.value, str)
             and child.value in vocabulary)
            or (isinstance(child, ast.Attribute) and child.attr == "value")
            for child in ast.walk(node)
        )
    }
    evidence = {item.id: item for item in result.observation.evidence}
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == owner
        and any(evidence[reference].line in property_lines for reference in row.evidence_ids)
    ]


@pytest.mark.parametrize("setter,expected", [("int", "PASS"), ("object", "FAIL")])
def test_real_property_lifecycle_keeps_verdict_and_canonical_wire(tmp_path, setter, expected):
    _, report, observation = _validate(tmp_path, _property(setter=setter))
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0
    assert bool(trace_valid_violations(observation)) == (expected == "FAIL")
    collected = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = facts_codec.encode_response(CollectionResponse(collected))
    decoded = facts_codec.decode_response(payload)
    assert facts_codec.encode_response(decoded) == payload
    values = [
        record.data.get("property_binding")
        for section in decoded.facts.sections
        for record in section.records
        if record.data.get("property_binding") is not None
    ]
    assert len(values) == 2
    _api()
    ordered = sorted((facts.property_binding(value) for value in values), key=lambda item: item.line)
    assert [value.operation for value in ordered] == [
        facts.PropertyOperation.CREATE,
        facts.PropertyOperation.SETTER,
    ]


def _repository(tmp_path, *, producer=False):
    target = copy.deepcopy(
        json.loads(
            (
                ROOT / f"docs/architecture/contracts/{'python' if producer else 'ir'}.json"
            ).read_text()
        )
    )
    target.pop("$schema", None)
    entities = target["declarations"]["uml"]["entities"]
    target["declarations"]["uml"]["entities"] = [
        item
        for item in entities
        if item["id"].startswith("PYTHON-PROPERTY-" if producer else "IR-PROPERTY-")
        or (not producer and item["id"] == "archkeel.ir.facts")
    ]
    target["declarations"]["uml"]["relationships"] = []
    target["declarations"]["uml"]["scopes"] = []
    target["declarations"]["modules"] = []
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    target["rules"] = (
        []
        if producer
        else [item for item in root_contract["rules"] if item["id"] == "COLLECTOR-TYPED-IR-FACTS"]
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "contract.json": json.dumps(target),
        "docs/architecture/typed-python-properties.md": "Owned property proof.\n",
        "docs/architecture/language-adapter-target.md": "Source-only facts.\n",
        "docs/architecture/collector-wire-vocabulary.md": "Nominal source controls.\n",
    }
    paths = ["analyzer/python/source.py"] if producer else ["ir/facts.py", "ir/facts_codec.py"]
    for path in paths:
        files["archkeel/" + path] = (ROOT / "src/archkeel" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


@pytest.mark.parametrize("producer", [False, True])
def test_native_property_api_fulfils_unchanged_authored_target(tmp_path, producer):
    root, config = _repository(tmp_path, producer=producer)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(model)
    if not producer:
        assessment = next(
            row
            for row in rule_assessments(model, undecided_by_rule={})
            if row.id == "COLLECTOR-TYPED-IR-FACTS"
        )
        assert assessment.status == "PASS" and assessment.evaluation_proven


@pytest.mark.parametrize(
    "producer,old,new",
    [
        (False, "operation: PropertyOperation", "operation: str"),
        (False, "source: PropertyOrigin", "source: str"),
        (True, "dict[FunctionNode, PropertyBinding]", "dict[FunctionNode, _PropertyBinding]"),
    ],
)
def test_native_property_api_widening_fails_unchanged_target(tmp_path, producer, old, new):
    root, config = _repository(tmp_path, producer=producer)
    path = root / ("archkeel/analyzer/python/source.py" if producer else "archkeel/ir/facts.py")
    text = path.read_text()
    assert old in text, "the real consumed property API must exist before mutation"
    path.write_text(text.replace(old, new))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assert any(
        item.aspect in {"annotation", "signature"} and item.status == "FAIL"
        for item in comparison.assessments
    ), comparison
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _property_probe(value):\n    return value == "setter"\n',
        'def _property_probe(value):\n    return value in ("getter", "setter")\n',
        "def _property_probe(value):\n    return value == PropertyOperation.SETTER.value\n",
    ],
)
def test_native_property_owner_rejects_raw_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    path = root / "archkeel/ir/facts.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [
        row for row in trace_valid_violations(model) if "COLLECTOR-TYPED-IR-FACTS" in row.rule_ids
    ]
