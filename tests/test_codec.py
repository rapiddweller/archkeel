# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import pytest

from codekeel.ir.codec import observation_payload, parse_observation
from codekeel.ir.model import EvidenceClass, Observation, RecordData


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
        "analyzer": {"name": "a", "version": "1", "code_digest": "unknown"},
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
                "typing_signals",
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


def test_parse_rejects_invalid_coverage_rules():
    raw = raw_observation()
    raw["coverage"]["rules"] = "UNKNOWN"
    with pytest.raises(ValueError, match="status/rules"):
        parse_observation(raw)
