# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Method kinds are nominal while descriptor proof and raw compatibility stay fixed."""

import ast
import copy
import json
from dataclasses import FrozenInstanceError, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_inherited_properties import _property, _validate
from test_uml_evaluation import _model

from archkeel.analyzer.python import source
from archkeel.analyzer.python.collect import collect
from archkeel.analyzer.python.imports import collect_imports
from archkeel.check.evaluation.boundary_types import _method_signature_positions
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts, facts_codec, source_graph
from archkeel.ir.architecture_graph import ModifierKind
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.protocol import (
    CollectionRequest, CollectionResponse, PythonSettings, SnapshotInput, SourceScope,
)
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
TAGS = ("instance", "static", "class", "constructor", "factory")
OPAQUE = (None, "", "future", "STATIC", 7, False, [], {})


def _api():
    model = getattr(facts, "MethodDescriptor", None)
    assert model is not None, "facts must own the consumed immutable method descriptor"
    return model


def _method(decorators="", prefix=""):
    module = _parsed_module(
        prefix + "class Child:\n" + decorators + "    def make(self, value: int) -> int: ...\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    owner = next(item for item in module.tree.body if isinstance(item, ast.ClassDef))
    method = next(item for item in owner.body if isinstance(item, ast.FunctionDef))
    return module, owner, method


def test_descriptor_field_and_five_shared_kinds_are_nominal():
    model = _api()
    annotation = get_type_hints(model)["method_kind"]
    assert annotation is facts.MethodKind
    assert issubclass(annotation, Enum) and not issubclass(annotation, str)
    assert tuple(item.value for item in annotation) == TAGS
    kind = annotation.STATIC
    descriptor = model(kind, True, False)
    assert descriptor.method_kind is kind
    with pytest.raises(FrozenInstanceError):
        descriptor.method_kind = kind
    with pytest.raises(ValueError):
        model("static", True, False)


@pytest.mark.parametrize("tag", TAGS)
def test_method_reader_accepts_all_existing_profile_tags_once(tag):
    _api()
    value = facts.parse_method_kind(tag)
    assert value is facts.MethodKind(tag)
    assert facts.parse_method_kind(value) is value


@pytest.mark.parametrize("tag", OPAQUE)
def test_method_reader_does_not_default_opaque_tags_to_instance(tag):
    _api()
    assert facts.parse_method_kind(tag) is None


@pytest.mark.parametrize(
    "decorators,prefix,kind,proven",
    [
        ("", "", "instance", True),
        ("    @staticmethod\n", "", "static", True),
        ("    @classmethod\n", "", "class", True),
        ("    @property\n", "", "instance", True),
        ("    @staticmethod\n    @property\n", "", "static", False),
        ("    @classmethod\n    @property\n", "", "class", False),
        ("    @property\n    @staticmethod\n", "", "static", False),
        ("    @classmethod\n    @staticmethod\n", "", "static", False),
        ("    @staticmethod\n    @classmethod\n", "", "class", False),
        ("    @staticmethod()\n", "", "instance", False),
        ("    @custom\n", "", "instance", False),
        ("    @staticmethod\n    @custom\n", "", "static", False),
        ("    @abstractmethod\n", "from abc import abstractmethod\n", "instance", True),
        ("    @staticmethod\n    @abstractmethod\n", "from abc import abstractmethod\n", "static", True),
        ("    @overload\n", "from typing import overload\n", "instance", True),
        ("    @method\n", "from builtins import classmethod as method\n", "class", True),
        ("    @staticmethod\n", "staticmethod = custom\n", "instance", False),
    ],
)
def test_real_descriptor_producer_and_legacy_wire_keep_proof_order(
    decorators, prefix, kind, proven,
):
    module, owner, method = _method(decorators, prefix)
    raw = source.method_decorator_data(module=module, node=method, parent=owner)
    assert type(raw) is dict
    assert raw["method_kind"] == kind
    assert raw["signature_decorators_proven"] is proven
    assert raw["source_final_method_binding"] is False
    assert json.loads(json.dumps(raw)) == raw and {**raw} == raw
    model = _api()
    descriptor = source.method_descriptor(module, method, owner)
    assert type(descriptor) is model
    assert descriptor.method_kind is facts.MethodKind(kind)
    assert descriptor.signature_decorators_proven is proven
    assert descriptor.source_final_method_binding is raw["source_final_method_binding"]
    assert facts_codec.method_descriptor_data(descriptor) == raw
    assert ("property_binding" in raw) is (descriptor.property_binding is not None)


@pytest.mark.parametrize("tag", TAGS + OPAQUE)
def test_receiver_selection_keeps_previous_nonstatic_semantics(tag):
    data = {
        "method_kind": tag, "receiver_parameter": "self", "name": "make",
        "parameters": [{"name": "self", "annotation": "object"},
                       {"name": "value", "annotation": "int"}],
        "returns": "str",
    }
    expected = [("self", "object"), ("value", "int"), ("return", "str")] if tag == "static" else [
        ("value", "int"), ("return", "str")
    ]
    assert _method_signature_positions(data) == expected
    data["parameters"] = list(reversed(data["parameters"]))
    assert _method_signature_positions(data) == [("value", "int"), ("self", "object"), ("return", "str")]


def test_receiver_helper_retains_its_existing_required_key_contract():
    with pytest.raises(KeyError):
        _method_signature_positions(
            {"receiver_parameter": "self", "name": "make",
             "parameters": [{"name": "self", "annotation": None}], "returns": None}
        )


@pytest.fixture
def method_record(tmp_path):
    _validate(tmp_path, "class Child:\n    def make(self, value: int) -> int: ...\n")
    collected = collect(CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("sample",), "sample"), PythonSettings(),
    ))
    record = next(
        item for section in collected.sections for item in section.records
        if item.kind == "method" and item.data.get("name") == "make"
    )
    return collected, record


@pytest.mark.parametrize("tag", TAGS + OPAQUE + ("<missing>",))
def test_existing_wire_transport_preserves_known_and_opaque_method_tags(method_record, tag):
    collected, record = method_record
    raw = facts_codec.thaw_data(record.data)
    if tag == "<missing>":
        raw.pop("method_kind")
    else:
        raw["method_kind"] = tag
    changed = replace(record, data=facts_codec.freeze_data(raw))
    collected = replace(collected, sections=tuple(
        replace(section, records=tuple(changed if item.id == record.id else item for item in section.records))
        for section in collected.sections
    ))
    encoded = facts_codec.encode_response(CollectionResponse(collected))
    decoded = facts_codec.decode_response(encoded)
    decoded_record = next(item for section in decoded.facts.sections for item in section.records
                          if item.id == record.id)
    assert facts_codec.thaw_data(decoded_record.data) == raw
    assert facts_codec.encode_response(decoded) == encoded
    entity = source_graph._symbol(decoded_record, "python")
    assert tuple(entity.modifiers) == (
        (ModifierKind.STATIC,) if tag == "static" else
        (ModifierKind.CLASS,) if tag == "class" else ()
    )


@pytest.mark.parametrize(
    "filename,scope",
    [
        ("analyzer/python/source.py", "method_descriptor"),
        ("check/evaluation/boundary_types.py", "_method_signature_positions"),
        ("ir/source_graph.py", "_symbol"),
        ("ir/facts_validation.py", "_property_bindings"),
        ("ir/facts_validation.py", "_resolution_gap_module"),
    ],
)
def test_actual_method_kind_controls_have_no_raw_dispatch(tmp_path, filename, scope):
    text = (ROOT / "src/archkeel" / filename).read_text()
    if filename.endswith("source.py") and "def method_descriptor(" not in text:
        scope = "method_decorator_data"
    result = _observe_one_rule(
        tmp_path,
        {"kind": "forbidden_construct", "source": "sample.core",
         "constructs": ["string_literal_compare"]},
        {"core.py": text},
    )
    assert result.diagnostics == () and result.observation is not None
    relevant = {
        node.lineno for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Compare) and any(
            (isinstance(child, ast.Constant) and child.value == "method_kind")
            or (isinstance(child, ast.Name) and child.id == "method_kind")
            or (isinstance(child, ast.Attribute) and child.attr == "value")
            for child in ast.walk(node)
        )
    }
    evidence = {item.id: item for item in result.observation.evidence}
    observed = [
        row for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == "sample.core." + scope
        and (filename.endswith("source.py") or any(evidence[e].line in relevant for e in row.evidence_ids))
    ]
    assert observed == [], [(row.title, [evidence[e].excerpt for e in row.evidence_ids]) for row in observed]


def _repository(tmp_path, producer=False):
    target = copy.deepcopy(json.loads((ROOT / f"docs/architecture/contracts/{'python' if producer else 'ir'}.json").read_text()))
    target.pop("$schema", None)
    target["declarations"]["modules"] = []
    uml = target["declarations"]["uml"]
    uml["relationships"] = []
    uml["scopes"] = []
    uml["entities"] = [
        item for item in uml["entities"]
        if item["id"].startswith("PYTHON-METHOD-" if producer else "IR-METHOD-")
        or item["id"] in ({"PYTHON-PROPERTY-SOURCE"} if producer else {"archkeel.ir.facts", "IR-PROPERTY-CODEC"})
    ]
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    target["rules"] = [] if producer else [
        item for item in root_contract["rules"] if item["id"] == "COLLECTOR-TYPED-IR-FACTS"
    ]
    files = {
        "archkeel/__init__.py": "", "archkeel/ir/__init__.py": "",
        "archkeel/analyzer/__init__.py": "", "archkeel/analyzer/python/__init__.py": "",
        "contract.json": json.dumps(target),
        "docs/architecture/typed-method-descriptors.md": "Nominal method descriptor proof.\n",
        "docs/architecture/typed-python-properties.md": "Property proof.\n",
        "docs/architecture/language-adapter-target.md": "Source-only facts.\n",
        "docs/architecture/collector-wire-vocabulary.md": "Nominal source controls.\n",
    }
    for path in (("analyzer/python/source.py",) if producer else ("ir/facts.py", "ir/facts_codec.py")):
        files["archkeel/" + path] = (ROOT / "src/archkeel" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


@pytest.mark.parametrize("producer", [False, True])
def test_native_descriptor_fulfils_authored_consumed_api_target(tmp_path, producer):
    root, config = _repository(tmp_path, producer)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(model)
    if not producer:
        assessment = next(item for item in rule_assessments(model, undecided_by_rule={})
                          if item.id == "COLLECTOR-TYPED-IR-FACTS")
        assert assessment.status == "PASS" and assessment.evaluation_proven


@pytest.mark.parametrize(
    "producer,old,new",
    [
        (False, "method_kind: MethodKind", "method_kind: str"),
        (False, "-> MethodKind | None:", "-> str | None:"),
        (True, ") -> MethodDescriptor:", ") -> RecordData:"),
    ],
)
def test_native_descriptor_api_mutations_fail_the_unchanged_target(tmp_path, producer, old, new):
    root, config = _repository(tmp_path, producer)
    path = root / ("archkeel/analyzer/python/source.py" if producer else "archkeel/ir/facts.py")
    text = path.read_text()
    assert old in text, "the actual consumed nominal API must exist"
    path.write_text(text.replace(old, new, 1))
    contract = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert any(item.status == "FAIL" and item.aspect in {"annotation", "signature"}
               for item in comparison.assessments), comparison
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize("probe", [
    'def _method_probe(value):\n    return value == "static"\n',
    'def _method_probe(value):\n    return value in ("instance", "class")\n',
    "def _method_probe(value):\n    return value == MethodKind.STATIC.value\n",
])
def test_native_descriptor_owner_rejects_raw_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    path = root / "archkeel/ir/facts.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [row for row in trace_valid_violations(model) if "COLLECTOR-TYPED-IR-FACTS" in row.rule_ids]
