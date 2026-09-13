# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# DATAMIMIC
# Copyright (c) 2023-2026 Rapiddweller Asia Co., Ltd.

from __future__ import annotations

import json

from test_delta import _model as _base_model

from pledge.ir.codec import (
    canonical_json_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
)
from pledge.ir.trace import validate_evidence_classes


def _record(
    identifier: str,
    evidence_class: str,
    *,
    evidence_ids: list[str] | None = None,
    rule_ids: list[str] | None = None,
    fact_ids: list[str] | None = None,
    provenance: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": identifier,
        "evidence_class": evidence_class,
        "area": "architecture",
        "kind": "item",
        "title": identifier,
        "subjects": ["sample.tasks"],
        "evidence_ids": evidence_ids or [],
        "rule_ids": rule_ids or [],
        "fact_ids": fact_ids or [],
        "provenance": provenance or [],
        "data": {"repeated": "architecture-value"},
    }


def _model() -> dict[str, object]:
    rule = _record("RULE", "DECLARED_RULE", provenance=["AGENTS.md"])
    fact = _record("FACT", "FACT", evidence_ids=["EVD"])
    violation = _record("VIO", "VIOLATION", rule_ids=["RULE"], fact_ids=["FACT"])
    model = _base_model(git_head="a" * 40)
    model.update(
        {
            "schema_version": "test",
            "declarations": [rule],
            "imports": [fact],
            "violations": [violation],
            "evidence": [
                {
                    "id": "EVD",
                    "file": "sample/tasks/sample.py",
                    "line": 1,
                    "end_line": 1,
                    "column": 0,
                    "excerpt": "import sample",
                }
            ],
        }
    )
    return model


def test_compact_canonical_encoding_is_lossless() -> None:
    model = _model()
    model["metrics"] = [_record(f"METRIC-{index}", "FACT") for index in range(32)]
    encoded = json.loads(canonical_report_bytes(model))
    assert encoded["encoding"]["kind"] == "architecture-ir-columnar-v1"
    assert decode_canonical_model(encoded) == model
    assert len(canonical_report_bytes(model)) < len(canonical_json_bytes(model))


def test_violation_trace_is_rule_fact_and_source_complete() -> None:
    model = _model()
    validate_evidence_classes(parse_observation(model))
    violations = model["violations"]
    evidence = model["evidence"]
    assert len(violations) == 1
    for violation in violations:
        assert violation["evidence_class"] == "VIOLATION"
        assert violation["rule_ids"] == ["RULE"]
        records = {
            item["id"]: item
            for section in model.values()
            if isinstance(section, list)
            for item in section
            if isinstance(item, dict) and "id" in item
        }
        assert records[violation["rule_ids"][0]]["evidence_class"] == "DECLARED_RULE"
        fact = records[violation["fact_ids"][0]]
        assert fact["evidence_class"] == "FACT"
        source = {item["id"]: item for item in evidence}[fact["evidence_ids"][0]]
        assert source["file"].startswith("sample/tasks/")
        assert source["line"] > 0 and source["excerpt"]
