# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reject malformed inherited-member proof at the process boundary."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_source_trust_boundary import _payload

from archkeel.ir.facts_codec import ProtocolError, decode_response

SCHEMA = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes())


def _schema_errors(payload):
    return list(Draft202012Validator(SCHEMA).iter_errors(payload))


@pytest.mark.parametrize(
    "key",
    [
        "source_binding_unique",
        "source_member_binding_static",
        "origin_member_binding_static",
        "origin_binding_unique",
        "class_header_static",
        "class_body_control_flow",
        "signature_decorators_proven",
        "source_final_method_binding",
        "overloaded",
        "overload_signature",
    ],
)
@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_malformed_proof_flags(key, value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"][key] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    assert _schema_errors(payload)


@pytest.mark.parametrize("value", [None, "x", [""], [1], [None], [False], {}])
def test_malformed_candidates(value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"]["reexport_candidates"] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    assert _schema_errors(payload)


@pytest.mark.parametrize("value", [[], ["module.Class"]])
def test_candidate_arrays(value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"]["reexport_candidates"] = value
    facts = decode_response(json.dumps(payload).encode()).facts
    assert facts.sections[0].records[0].data.get("reexport_candidates") == tuple(value)
    assert not _schema_errors(payload)
