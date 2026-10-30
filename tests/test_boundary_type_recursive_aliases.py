# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Guarded direct alias recursion keeps native declarations and every other branch checked."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.check.evaluation.boundary_types import _boundary_type_verdict, boundary_type_indexes
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import decode_response, encode_response, raw_record
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _native_case(tmp_path: Path, source: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "values.py").write_text(source)
    facts = decode_response(
        encode_response(
            CollectionResponse(
                collect(
                    CollectionRequest(
                        SnapshotInput(str(tmp_path), "a" * 40, False),
                        SourceScope(("sample",), "sample"),
                        PythonSettings(),
                    )
                )
            )
        )
    ).facts
    assert facts.coverage.files_read == facts.coverage.files_parsed == 2
    assert facts.coverage.full_scope
    assert {file.rel_path for file in facts.files} == {"sample/__init__.py", "sample/values.py"}
    return facts


def _verdict(
    facts,
    name: str,
    *,
    public: tuple[str, ...] = ("sample.values:RecordData", "sample.values:Box"),
):
    records = {
        section.name: [raw_record(row) for row in section.records] for section in facts.sections
    }
    imports, bindings = boundary_type_indexes(records["symbols"], records["imports"])
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                {
                    "id": "sample",
                    "label": "sample",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/sample.md"],
                    "public": list(public),
                }
            ],
            "rules": [],
        }
    )
    return _boundary_type_verdict(
        name, "sample.values", contract, {}, imports, bindings, type_shapes=dict(facts.type_shapes)
    )


def _actual_json_value_source() -> str:
    source = (Path(__file__).parents[1] / "src/archkeel/ir/facts.py").read_text()
    declarations = [
        ast.get_source_segment(source, node)
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
        and node.name == "RecordData"
        or isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "JsonValue"
    ]
    assert len(declarations) == 2 and all(declarations)
    return "from typing import TypeAlias\n" + "\n\n".join(declarations) + "\n"


@pytest.mark.parametrize("renamed", [False, True])
def test_native_actual_json_value_is_a_guarded_direct_alias(tmp_path, renamed):
    source = _actual_json_value_source()
    name = "JsonValue"
    if renamed:
        source = source.replace("JsonValue", "NestedValue").replace("RecordData", "Box")
        name = "NestedValue"
    verdict = _verdict(_native_case(tmp_path, source), name)
    assert verdict.violation is None and verdict.undecidable is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('str | tuple["Value", ...]', "PASS"),
        ('str | tuple["Value", ...] | object', "FAIL"),
        ('str | tuple["Value", ...] | dict[str, str]', "FAIL"),
        ('tuple["Value", ...]', "UNKNOWN"),
        ('str | "Value"', "UNKNOWN"),
        ('str | tuple["Value"]', "UNKNOWN"),
        ('str | list["Value"]', "UNKNOWN"),
        ('str | tuple["Missing", ...]', "UNKNOWN"),
        ('str | tuple["Value", ...] | Missing', "UNKNOWN"),
    ],
)
def test_native_direct_recursion_checks_every_arm(tmp_path, body, expected):
    facts = _native_case(tmp_path, f"from typing import TypeAlias\nValue: TypeAlias = {body}\n")
    verdict = _verdict(facts, "Value")
    assert (
        "FAIL" if verdict.violation else "UNKNOWN" if verdict.undecidable else "PASS"
    ) == expected


@pytest.mark.parametrize(
    "source",
    [
        'from typing import TypeAlias\nValue: TypeAlias = str | tuple["Other", ...]\n'
        'Other: TypeAlias = str | tuple["Value", ...]\n',
        'from typing import TypeAlias\nValue: TypeAlias = str | tuple["Value", ...]\n'
        "Value: TypeAlias = int\n",
        "from typing import TypeAlias\ntuple = list\n"
        'Value: TypeAlias = str | tuple["Value", ...]\n',
    ],
)
def test_native_mutual_rebound_and_shadowed_recursion_stays_unknown(tmp_path, source):
    verdict = _verdict(_native_case(tmp_path, source), "Value")
    assert verdict.violation is None and verdict.undecidable is not None


def test_recursive_alias_needs_native_quoted_shape(tmp_path):
    facts = _native_case(
        tmp_path, 'from typing import TypeAlias\nValue: TypeAlias = str | tuple["Value", ...]\n'
    )
    facts = replace(
        facts,
        type_shapes=tuple(
            (key, shape) for key, shape in facts.type_shapes if not key.startswith(("'", '"'))
        ),
    )
    verdict = _verdict(facts, "Value")
    assert verdict.violation is None and verdict.undecidable is not None


@pytest.mark.parametrize("present", [False, True])
def test_recursive_alias_requires_unique_declaration_evidence(tmp_path, present):
    import json

    facts = _native_case(
        tmp_path, 'from typing import TypeAlias\nValue: TypeAlias = str | tuple["Value", ...]\n'
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    [alias] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if row["kind"] == "type_alias" and row["data"].get("name") == "Value"
    ]
    assert alias["data"]["source_binding_unique"] is True
    if present:
        alias["data"]["source_binding_unique"] = False
    else:
        del alias["data"]["source_binding_unique"]
    verdict = _verdict(decode_response(json.dumps(payload).encode()).facts, "Value")
    assert verdict.violation is None and verdict.undecidable is not None


@pytest.mark.parametrize("proof", [True, False, None])
def test_imported_tuple_guard_needs_positive_binding_evidence(tmp_path, proof):
    import json

    facts = _native_case(
        tmp_path,
        "from builtins import tuple\nfrom typing import TypeAlias\n"
        'Value: TypeAlias = str | tuple["Value", ...]\n',
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    [binding] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if row["data"].get("binding") == "tuple"
        and row["data"].get("source_module") == "sample.values"
    ]
    assert binding["data"]["source_binding_unique"] is True
    if proof is None:
        del binding["data"]["source_binding_unique"]
    else:
        binding["data"]["source_binding_unique"] = proof
    verdict = _verdict(decode_response(json.dumps(payload).encode()).facts, "Value")
    assert verdict.violation is None
    assert (verdict.undecidable is None) is (proof is True)


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("dict", "FAIL"),
        ("Missing", "UNKNOWN"),
        ('"JsonValue"', "UNKNOWN"),
        ("JsonValue", "UNKNOWN"),
    ],
)
def test_recursive_alias_keeps_other_record_fields_checked(tmp_path, annotation, expected):
    source = _actual_json_value_source().replace(
        "entries: tuple[tuple[str, JsonValue], ...] = ()",
        f"entries: tuple[tuple[str, JsonValue], ...] = ()\n    other: {annotation}",
    )
    verdict = _verdict(_native_case(tmp_path, source), "JsonValue")
    assert (
        "FAIL" if verdict.violation else "UNKNOWN" if verdict.undecidable else "PASS"
    ) == expected
    assert verdict.path == ("other",)


_DTO_SOURCE = """from __future__ import annotations
from dataclasses import dataclass
from typing import TypeAlias

@dataclass(frozen=True)
class Leaf:
    value: str

@dataclass(frozen=True)
class Branch:
    child: Tree

Tree: TypeAlias = Leaf | Branch
"""


@pytest.mark.parametrize("renamed", [False, True])
def test_native_actual_type_shape_has_productive_dto_recursion(tmp_path, renamed):
    source = (Path(__file__).parents[1] / "src/archkeel/ir/type_shapes.py").read_text()
    if renamed:
        source = source.replace("TypeShape", "Tree").replace("TypeName", "Leaf")
    facts = _native_case(tmp_path, source)
    ground = _verdict(facts, "Leaf" if renamed else "TypeName", public=("sample.values",))
    assert ground.violation is None and ground.undecidable is None
    verdict = _verdict(facts, "Tree" if renamed else "TypeShape", public=("sample.values",))
    assert verdict.violation is None and verdict.undecidable is None


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("", "", "PASS"),
        ("child: Tree", "child: Tree\n    other: object", "FAIL"),
        ("child: Tree", "child: Tree\n    other: dict[str, str]", "FAIL"),
        ("child: Tree", "child: Tree\n    other: Missing", "UNKNOWN"),
        ("Leaf | Branch", "Leaf | Branch | object", "FAIL"),
        ("Leaf | Branch", "Leaf | Branch | Missing", "UNKNOWN"),
        ("Leaf | Branch", "Branch | Branch", "UNKNOWN"),
        ("Leaf | Branch", "Leaf | Branch | Tree", "UNKNOWN"),
        ("Leaf | Branch", "Leaf | Tree", "UNKNOWN"),
        ("child: Tree", "child: 'Tree'", "UNKNOWN"),
        ("child: Tree", "child: Other", "UNKNOWN"),
        ("@dataclass(frozen=True)", "@dataclass", "UNKNOWN"),
        ("@dataclass(frozen=True)\n", "", "UNKNOWN"),
        ("class Branch:", "class Branch(External):", "UNKNOWN"),
        (
            "Tree: TypeAlias = Leaf | Branch",
            "Tree: TypeAlias = Other\nOther: TypeAlias = Leaf | Branch",
            "UNKNOWN",
        ),
    ],
)
def test_native_dto_recursion_checks_all_arms_and_fields(tmp_path, before, after, expected):
    source = _DTO_SOURCE.replace(before, after) if before else _DTO_SOURCE
    verdict = _verdict(_native_case(tmp_path, source), "Tree", public=("sample.values",))
    assert (
        "FAIL" if verdict.violation else "UNKNOWN" if verdict.undecidable else "PASS"
    ) == expected


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("Tree", "source_binding_unique", None),
        ("Tree", "source_binding_unique", False),
        ("Branch", "source_binding_unique", None),
        ("Branch", "source_binding_unique", False),
        ("Branch", "member_inventories", None),
        ("Branch", "class_body_control_flow", True),
        ("Branch", "namespace_bound", None),
        ("Branch", "definition_contexts", None),
        ("Leaf", "source_binding_unique", None),
        ("Leaf", "member_inventories", None),
    ],
)
def test_native_dto_recursion_requires_positive_source_evidence(tmp_path, name, field, value):
    import json

    payload = json.loads(encode_response(CollectionResponse(_native_case(tmp_path, _DTO_SOURCE))))
    [symbol] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if section["name"] == "symbols" and row["data"].get("name") == name
    ]
    if value is None:
        symbol["data"].pop(field, None)
    else:
        symbol["data"][field] = value
    verdict = _verdict(
        decode_response(json.dumps(payload).encode()).facts, "Tree", public=("sample.values",)
    )
    assert verdict.violation is None and verdict.undecidable is not None


@pytest.mark.parametrize("name", ["TypeName", "TypeMember", "TypeLiteral", "UnresolvedType"])
def test_actual_dto_sum_requires_each_class_binding_even_with_another_ground(tmp_path, name):
    import json

    source = (Path(__file__).parents[1] / "src/archkeel/ir/type_shapes.py").read_text()
    payload = json.loads(encode_response(CollectionResponse(_native_case(tmp_path, source))))
    [symbol] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if section["name"] == "symbols" and row["data"].get("name") == name
    ]
    symbol["data"].pop("source_binding_unique")
    verdict = _verdict(
        decode_response(json.dumps(payload).encode()).facts, "TypeShape", public=("sample.values",)
    )
    assert verdict.violation is None and verdict.undecidable is not None


@pytest.mark.parametrize(
    "fields",
    [
        None,
        [],
        [{"name": "child", "annotation": "str"}],
        [{"name": "child", "annotation": "Tree"}] * 2,
    ],
    ids=["missing", "empty", "changed", "duplicate"],
)
def test_native_dto_field_view_cannot_erase_or_change_its_declarations(tmp_path, fields):
    import json

    payload = json.loads(
        encode_response(CollectionResponse(_native_case(tmp_path, _DTO_SOURCE), ProtocolVersion.V4))
    )
    [branch] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if section["name"] == "symbols" and row["data"].get("name") == "Branch"
    ]
    assert branch["data"]["attribute_declarations"][0]["annotation"] == "Tree"
    if fields is None:
        branch["data"].pop("fields")
    else:
        branch["data"]["fields"] = fields
    verdict = _verdict(
        decode_response(json.dumps(payload).encode()).facts, "Tree", public=("sample.values",)
    )
    assert verdict.violation is None and verdict.undecidable is not None


@pytest.mark.parametrize("keep_fields", [False, True])
def test_legacy_field_source_is_explicit_even_without_attribute_inventory(tmp_path, keep_fields):
    import json

    facts = _native_case(tmp_path, "class Leaf:\n    value: str\n")
    payload = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    [leaf] = [
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if section["name"] == "symbols"
    ]
    leaf["data"].pop("attribute_declarations")
    leaf["data"].pop("member_inventories")
    if not keep_fields:
        leaf["data"].pop("fields")
    verdict = _verdict(
        decode_response(json.dumps(payload).encode()).facts, "Leaf", public=("sample.values",)
    )
    assert verdict.violation is None
    assert (verdict.undecidable is None) is keep_fields


@pytest.mark.parametrize(
    "source",
    [
        "class Leaf: pass\n",
        "class Leaf:\n    _private: object\n    constant = {}\n    value: str\n",
    ],
)
def test_native_empty_private_and_unannotated_attributes_do_not_invent_fields(tmp_path, source):
    verdict = _verdict(_native_case(tmp_path, source), "Leaf", public=("sample.values",))
    assert verdict.violation is None and verdict.undecidable is None
