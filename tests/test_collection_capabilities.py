# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An unavailable construct capability cannot certify an empty observation as clean."""

import json
from pathlib import Path

import pytest
from collector_pin import assembled

from archkeel.check.ratchets import unknown_positions_by_rule
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import decode_response


@pytest.mark.parametrize("status", ["partial", "unsupported", None])
def test_empty_construct_facts_cannot_pass_without_decided_capability(
    tmp_path: Path, status: str | None
) -> None:
    payload = json.loads(
        (Path(__file__).parent / "fixtures/collection-protocol/response-python.json").read_bytes()
    )
    payload["facts"]["capabilities"]["constructs"] = (
        [{"name": "assert", "status": status}] if status else []
    )
    for name in (
        "symbols",
        "calls",
        "references",
        "bindings",
        "typing_signals",
        "constructs",
        "unknowns",
    ):
        payload["facts"]["capabilities"]["sections"].append(name)
        payload["facts"]["sections"].append({"name": name, "records": []})
    facts = decode_response(json.dumps(payload).encode()).facts
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [],
                "rules": [
                    {
                        "id": "NO-ASSERT",
                        "kind": "forbidden_construct",
                        "source": "project",
                        "constructs": ["assert"],
                        "rationale": "No assertions.",
                        "provenance": ["architecture.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    observation, _ = assembled(
        facts, contract_root=tmp_path, contract_path=contract, roots=("src",), namespace="project"
    )
    unknown = unknown_positions_by_rule(observation)
    [assessment] = rule_assessments(
        observation, undecided_by_rule=unknown, complete=observation.coverage.status == "PASS"
    )
    assert assessment.status == "UNKNOWN"
    if status == "partial":
        assert unknown["NO-ASSERT"] == 1
    else:
        assert any(
            item.kind == "rule-unsupported-by-profile" for item in observation.coverage.failures
        )
