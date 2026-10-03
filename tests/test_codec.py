# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import pytest

from archkeel.ir.codec import (
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
)
from archkeel.ir.model import EvidenceClass, Observation, RecordData


def raw_observation():
    record = {
        "id": "m1",
        "evidence_class": "FACT",
        "area": "x",
        "kind": "module",
        "title": "M",
        "subjects": ["backend.m"],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"nested": {"value": 1}, "items": ["a", 2]},
    }
    base = {
        "schema_version": "1.2.0",
        "analyzer": {"name": "archkeel-python-analyzer", "version": "1", "code_digest": "unknown"},
        "source": {
            "git_head": "unknown",
            "dirty": "unknown",
            "source_digest": "unknown",
            "scope": ["backend"],
        },
        "contract": {"schema_version": "1", "digest": "unknown", "path": "contract.json"},
        "coverage": {
            "status": "PASS",
            "files_discovered": 1,
            "files_read": 1,
            "files_parsed": 1,
            "calls_analyzed": 0,
            "calls_resolved": 0,
            "calls_partially_resolved": 0,
            "calls_unresolved": 0,
            "ast_coverage_percent": 100.0,
            "call_resolution_percent": 100.0,
            "failures": [],
        },
        "evidence": [],
    }
    base.update(
        {
            section: [record] if section == "modules" else []
            for section in (
                "metrics",
                "declarations",
                "scope_observations",
                "packages",
                "modules",
                "symbols",
                "imports",
                "dependency_edges",
                "transitive_paths",
                "path_observations",
                "cycles",
                "calls",
                "references",
                "bindings",
                "typing_signals",
                "constructs",
                "contexts",
                "context_evidence",
                "violations",
                "unknowns",
            )
        }
    )
    return base


def test_parse_observation_is_immutable_and_nested_data_is_tuple():
    value = parse_observation(raw_observation())
    assert isinstance(value, Observation)
    assert value.records("modules")[0].evidence_class is EvidenceClass.FACT
    assert isinstance(value.records("modules")[0].data, RecordData)
    assert isinstance(value.records("modules")[0].data.get("items"), tuple)
    assert observation_payload(value)["modules"][0]["data"]["nested"] == {"value": 1}


def test_parse_rejects_unknown_top_level_field():
    raw = raw_observation()
    raw["extra"] = True
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_observation(raw)


def test_language_observation_additive_runtime_and_producer_round_trip():
    raw = raw_observation()
    raw["analyzer"] = {
        "name": "archkeel-typescript-imports",
        "version": "5.9.3",
        "code_digest": "a" * 64,
    }
    for section in ("symbols", "references", "bindings", "calls", "typing_signals", "constructs"):
        raw[section] = None
    raw.pop("python_version", None)
    raw["runtime"] = {"name": "node", "version": "22.13.0"}
    raw["producer"] = {"name": "custom-ts-parser", "version": "1.2.0", "code_digest": "b" * 64}

    observation = parse_observation(raw)

    payload = observation_payload(observation)
    assert payload["runtime"] == raw["runtime"]
    assert payload["producer"] == raw["producer"]


def test_old_python_observation_keeps_legacy_wire_fields():
    raw = raw_observation()
    observation = parse_observation(raw)
    assert set(observation_payload(observation)) == set(raw)


def test_parse_rejects_invalid_coverage_rules():
    raw = raw_observation()
    raw["coverage"]["rules"] = "UNKNOWN"
    with pytest.raises(ValueError, match="status/rules"):
        parse_observation(raw)


def test_dart_profile_accepts_its_absent_sections_as_null():
    raw = raw_observation()
    raw["analyzer"]["name"] = "archkeel-dart-directives"
    for section in ("symbols", "references", "bindings"):
        raw[section] = None

    observation = parse_observation(raw)

    assert observation.records("symbols") is None
    assert observation.records("references") is None
    assert observation.records("bindings") is None


def test_python_profile_rejects_a_null_required_section():
    raw = raw_observation()
    raw["symbols"] = None

    with pytest.raises(ValueError, match="symbols.*array"):
        parse_observation(raw)


def test_unknown_analyzer_identity_is_rejected():
    raw = raw_observation()
    raw["analyzer"]["name"] = "third-party-observer"

    with pytest.raises(ValueError, match="unsupported analyzer identity"):
        parse_observation(raw)


def test_dart_profile_rejects_a_null_section_it_does_not_declare_absent():
    raw = raw_observation()
    raw["analyzer"]["name"] = "archkeel-dart-directives"
    for section in ("symbols", "references", "bindings"):
        raw[section] = None
    raw["calls"] = None

    with pytest.raises(ValueError, match="calls.*array"):
        parse_observation(raw)


def test_python_profile_rejects_a_non_array_section():
    raw = raw_observation()
    raw["symbols"] = {}

    with pytest.raises(ValueError, match="symbols.*array"):
        parse_observation(raw)


def test_canonical_encoder_rejects_null_for_python_required_section():
    raw = raw_observation()
    raw["symbols"] = None

    with pytest.raises(ValueError, match="symbols.*array"):
        encode_canonical_model(raw)


def test_canonical_decoder_rejects_null_for_python_required_section():
    encoded = encode_canonical_model(raw_observation())
    encoded["symbols"] = None

    with pytest.raises(ValueError, match="symbols.*array"):
        decode_canonical_model(encoded)


def test_canonical_decoder_rejects_unknown_analyzer_identity():
    raw = raw_observation()
    raw["analyzer"]["name"] = "third-party-observer"

    with pytest.raises(ValueError, match="unsupported analyzer identity"):
        decode_canonical_model(raw)
