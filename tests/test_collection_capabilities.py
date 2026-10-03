# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An unavailable construct cannot certify a clean rule."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_collection_boundary_regressions import _facts

from archkeel.check.observation import assemble_observation
from archkeel.check.ratchets import unknown_positions_by_rule
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.protocol import CollectionResponse


@pytest.mark.parametrize("status", ["partial", "unsupported", None])
def test_empty_construct_facts_cannot_pass_without_decided_capability(
    tmp_path: Path, status: str | None
) -> None:
    facts = _facts(tmp_path)
    payload = json.loads(encode_response(CollectionResponse(facts)))
    payload["facts"]["capabilities"]["constructs"] = (
        [{"name": "assert", "status": status}] if status else []
    )
    for section in payload["facts"]["sections"]:
        if section["name"] == "constructs":
            section["records"] = []
    # The unavailable collector is allowed to report no candidates, but that is not absence proof.
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
                        "source": "sample",
                        "constructs": ["assert"],
                        "rationale": "No assertions.",
                        "provenance": ["architecture.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    observation, _ = assemble_observation(
        facts, contract_root=tmp_path, contract_path=contract, roots=("src",), namespace="sample"
    )
    assessment = rule_assessments(
        observation,
        undecided_by_rule=unknown_positions_by_rule(observation),
        complete=observation.coverage.status == "PASS",
    )[0]
    assert assessment.status == "UNKNOWN"
    if status == "partial":
        assert unknown_positions_by_rule(observation)["NO-ASSERT"] == 1
    else:
        assert any(
            item.kind == "rule-unsupported-by-profile" for item in observation.coverage.failures
        )


def test_decided_construct_capability_allows_clean_rule(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    sections = tuple(
        replace(section, records=()) if section.name == "constructs" else section
        for section in facts.sections
    )
    facts = replace(facts, sections=sections)
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
                        "source": "sample",
                        "constructs": ["assert"],
                        "rationale": "No assertions.",
                        "provenance": ["architecture.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    observation, _ = assemble_observation(
        facts, contract_root=tmp_path, contract_path=contract, roots=("src",), namespace="sample"
    )
    assert (
        rule_assessments(
            observation, undecided_by_rule=unknown_positions_by_rule(observation), complete=True
        )[0].status
        == "PASS"
    )
