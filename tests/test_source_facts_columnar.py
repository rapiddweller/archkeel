# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Versioned source-fact columnar wire format tests."""

import json

import pytest


def test_string_interner_uses_positive_json_savings_and_is_lossless() -> None:
    from archkeel.ir.codec_strings import expand_strings, intern_strings, profitable_string

    value = {"names": ["qualified.identifier.long", "qualified.identifier.long", "$m", "$$m"]}
    encoded, table = intern_strings(value, profitable=profitable_string)
    assert "qualified.identifier.long" in table
    assert expand_strings(encoded, table) == value


def test_v5_response_roundtrips_columnar_records_and_both_evidence_lists() -> None:
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse, ProtocolVersion

    facts = decode_response(json.dumps(_response()).encode()).facts
    from dataclasses import replace

    facts = replace(facts, candidate_evidence=facts.evidence)
    response = CollectionResponse(facts, ProtocolVersion.V5)
    encoded = encode_response(response)
    envelope = json.loads(encoded)
    assert envelope["protocol_version"] == "5.0.0"
    assert envelope["facts"]["encoding"]["kind"] == "source-facts-columnar-v1"
    assert isinstance(envelope["facts"]["sections"][0]["records"][0], list)
    assert isinstance(envelope["facts"]["candidate_evidence"], list)
    assert decode_response(encoded) == response
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    Draft202012Validator(schema).validate(envelope)


def test_v5_decoder_rejects_bad_string_reference_before_source_validation() -> None:
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["protocol_version"] = "5.0.0"
    raw["provider_sources"] = []
    raw["facts"]["encoding"] = {
        "kind": "source-facts-columnar-v1",
        "record_fields": [],
        "evidence_fields": [],
        "data_fields": [],
        "section_data_fields": {},
        "string_reference": "$<index>",
    }
    raw["facts"]["string_table"] = []
    with pytest.raises(ProtocolError, match="encoding|columnar"):
        decode_response(json.dumps(raw).encode())


def test_v4_decoder_rejects_v5_compact_envelope() -> None:
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["facts"]["encoding"] = {}
    raw["facts"]["string_table"] = []
    with pytest.raises(ProtocolError, match="facts fields"):
        decode_response(json.dumps(raw).encode())


def test_v5_decoder_rejects_out_of_range_string_reference() -> None:
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse, ProtocolVersion

    facts = decode_response(json.dumps(_response()).encode()).facts
    envelope = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V5)))
    envelope["facts"]["sections"][0]["records"][0][0] = "$999999"
    with pytest.raises(ProtocolError, match="string table reference is out of range"):
        decode_response(json.dumps(envelope).encode())


def test_v5_expansion_uses_the_ordinary_source_fact_validator() -> None:
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import ProtocolError, _compact_source_facts, decode_response

    raw = _response()
    raw["protocol_version"] = "5.0.0"
    raw["provider_sources"] = []
    raw["facts"]["provider_bindings"] = []
    raw["facts"]["runtime"]["requirement_state"] = "declared"
    raw["facts"]["sections"][0]["records"][0]["evidence_ids"] = ["E-missing"]
    raw["facts"] = _compact_source_facts(raw["facts"])
    with pytest.raises(ProtocolError, match="dangling source evidence reference"):
        decode_response(json.dumps(raw).encode())


def test_v5_schema_checks_row_and_pair_widths() -> None:
    from pathlib import Path

    from jsonschema import Draft202012Validator, ValidationError
    from test_collection_protocol import _response

    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse, ProtocolVersion

    facts = decode_response(json.dumps(_response()).encode()).facts
    envelope = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V5)))
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    validator = Draft202012Validator(schema)
    narrow_row = json.loads(json.dumps(envelope))
    narrow_row["facts"]["sections"][0]["records"][0].pop()
    with pytest.raises(ValidationError):
        validator.validate(narrow_row)
    narrow_pair = json.loads(json.dumps(envelope))
    narrow_pair["facts"]["sections"][0]["records"][0][-1][0].pop()
    with pytest.raises(ValidationError):
        validator.validate(narrow_pair)
    duplicate_pair = json.loads(json.dumps(envelope))
    pairs = duplicate_pair["facts"]["sections"][0]["records"][0][-1]
    pairs.append(pairs[0].copy())
    with pytest.raises(ValidationError):
        validator.validate(duplicate_pair)
    duplicate_index = json.loads(json.dumps(envelope))
    pairs = duplicate_index["facts"]["sections"][0]["records"][0][-1]
    pairs.append([pairs[0][0], "different value"])
    with pytest.raises(ProtocolError, match="compact data field index is invalid"):
        decode_response(json.dumps(duplicate_index).encode())
