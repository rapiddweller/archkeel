# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Property operations need ordered, source-owned proof across the process port."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_inherited_properties import _property, _validate

from archkeel.analyzer.python.collect import collect
from archkeel.check.observation import assemble_observation
from archkeel.check.ratchets import unknown_positions
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

SCHEMA = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes())


@pytest.fixture
def payload(tmp_path):
    _validate(tmp_path, _property())
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    return json.loads(encode_response(CollectionResponse(facts)))


def _records(payload):
    return next(
        section["records"]
        for section in payload["facts"]["sections"]
        if section["name"] == "symbols"
    )


def _setter(payload):
    return next(
        record
        for record in _records(payload)
        if record["data"].get("property_binding", {}).get("operation") == "setter"
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("operation", "deleter"),
        ("source", "unknown"),
        ("line", True),
        ("line", 0),
        ("source_line", -1),
        ("source_line", "4"),
        ("extra", True),
    ],
)
def test_malformed_property_binding_is_rejected_by_codec_and_schema(payload, key, value):
    _setter(payload)["data"]["property_binding"][key] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    assert list(Draft202012Validator(SCHEMA).iter_errors(payload))


@pytest.mark.parametrize(
    "change", ["future", "wrong-owner", "wrong-evidence", "missing-origin", "wrong-members"]
)
def test_property_binding_cannot_borrow_another_source_position(payload, change):
    setter = _setter(payload)
    if change == "future":
        setter["data"]["property_binding"]["source_line"] = 1000
    elif change == "wrong-owner":
        setter["data"]["parent"] = "sample.api.Hidden"
    elif change == "wrong-evidence":
        setter["data"]["property_binding"]["line"] += 1
    elif change == "missing-origin":
        setter["data"]["property_binding"]["source_line"] = 1
    else:
        next(record for record in _records(payload) if record["data"].get("property_members"))[
            "data"
        ]["property_members"] = []
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_removing_all_property_proof_retains_unknown(payload, tmp_path):
    for record in _records(payload):
        record["data"].pop("property_binding", None)
        record["data"].pop("property_members", None)
    facts = decode_response(json.dumps(payload).encode()).facts
    observation, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    assert unknown_positions(observation) > 0


def test_removing_creation_signature_proof_cannot_certify_a_property(payload, tmp_path):
    getter = next(
        record
        for record in _records(payload)
        if record["data"].get("property_binding", {}).get("operation") == "create"
    )
    getter["data"].pop("signature_decorators_proven")
    facts = decode_response(json.dumps(payload).encode()).facts
    observation, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    assert unknown_positions(observation) > 0


def test_property_facts_round_trip_and_remain_immutable(payload, tmp_path):
    assert not list(Draft202012Validator(SCHEMA).iter_errors(payload))
    _records(payload).reverse()
    facts = decode_response(json.dumps(payload).encode()).facts
    before = encode_response(CollectionResponse(facts))
    observation, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    assert unknown_positions(observation) == 0
    assert encode_response(CollectionResponse(facts)) == before


@pytest.mark.parametrize(
    "change",
    [
        "no-evidence",
        "wrong-kind",
        "wrong-category",
        "static",
        "async",
        "duplicate-members",
        "member-owner",
    ],
)
def test_property_proof_rejects_incoherent_method_and_owner(payload, change):
    setter = _setter(payload)
    owner = next(record for record in _records(payload) if record["data"].get("property_members"))
    if change == "no-evidence":
        setter["evidence_ids"] = []
    elif change == "wrong-kind":
        setter["kind"] = "function"
    elif change == "wrong-category":
        setter["data"]["symbol_category"] = "function"
    elif change == "static":
        setter["data"]["method_kind"] = "static"
    elif change == "async":
        setter["data"]["async"] = True
    elif change == "duplicate-members":
        owner["data"]["property_members"].append("value")
    else:
        setter["data"]["property_members"] = []
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("replacement", ["typed", "setter", "fresh"])
def test_missing_direct_property_proof_never_checks_stale_accessors(tmp_path, replacement):
    source = _property(setter="int" if replacement == "typed" else "object")
    source = source.split("class Child(Base):")[0].replace("class Base:", "class Child:")
    if replacement == "setter":
        source += "    @value.setter\n    def value(self, new_value: int) -> None: ...\n"
    elif replacement == "fresh":
        source += "    @property\n    def value(self) -> int: ...\n"
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == "PASS"
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    for record in _records(payload):
        record["data"].pop("property_binding", None)
        record["data"].pop("property_members", None)
    stripped = decode_response(json.dumps(payload).encode()).facts
    observation, _ = assemble_observation(
        stripped,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    assert unknown_positions(observation) > 0
    assert observation.records("violations") == ()


@pytest.mark.parametrize(
    "source",
    [
        "class Child:\n    def value(self) -> int: ...\n",
        "from dataclasses import dataclass\n@dataclass\nclass Child:\n"
        "    @property\n    def value(self) -> int: ...\n",
        "from typing import overload\nclass Child:\n"
        "    @overload\n    def value(self, arg: int) -> int: ...\n"
        "    @overload\n    def value(self, arg: str) -> str: ...\n"
        "    def value(self, arg): ...\n",
    ],
    ids=["ordinary", "dataclass-lone-getter", "overload"],
)
def test_direct_signature_controls_do_not_require_property_chain_proof(tmp_path, source):
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == "PASS"
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    for record in _records(payload):
        record["data"].pop("property_binding", None)
        record["data"].pop("property_members", None)
    observation, _ = assemble_observation(
        decode_response(json.dumps(payload).encode()).facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    assert unknown_positions(observation) == 0
    assert observation.records("violations") == ()
