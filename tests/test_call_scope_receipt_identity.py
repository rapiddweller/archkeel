# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A complete inventory does not authorize another rule's evaluation claim."""

import copy
import json

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import canonical_report_bytes, observation_payload
from archkeel.ir.codec_observation import parse_observation
from archkeel.ir.decisions import dependency_binding_id, rule_evaluation_binding_id
from archkeel.ir.model import SCHEMA_VERSION


def _observation(root):
    common = {"source": "sample.caller", "target": "sample.storage.page"}
    contract = {
        "schema_version": "3.7.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule("call_owner", id="KNOWN", **(common | {"allowed_sources": ["sample.caller"]})),
            _rule(
                "call_owner",
                id="UNKNOWN",
                **(common | {"target": "sample.storage.absent", "allowed_sources": []}),
            ),
        ],
    }
    result = _observe_tree(
        root,
        {
            "sample/__init__.py": "",
            "sample/storage.py": "def page(query): pass\n",
            "sample/caller.py": "from .storage import page\ndef run(q):\n    page(q)\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    return observation_payload(result.observation)


def _receipt(raw):
    return next(
        row
        for row in raw["scope_observations"]
        if row["kind"] == "rule_evaluation" and row["rule_ids"] == ["KNOWN"]
    )


def _read(root, raw, columnar):
    path = root / "saved.json"
    path.write_bytes(canonical_report_bytes(raw) if columnar else json.dumps(raw).encode())
    return {row.id: row for row in run_saved_report(path).rule_assessments}


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("drop_unknowns", [False, True])
def test_saved_reader_rejects_cross_rule_receipt_replay(tmp_path, drop_unknowns, columnar):
    raw = _observation(tmp_path)
    before = _read(tmp_path, raw, columnar)
    assert before["KNOWN"].status == "PASS" and before["KNOWN"].evaluation_proven
    assert before["UNKNOWN"].status == "UNKNOWN" and not before["UNKNOWN"].evaluation_proven
    receipt = copy.deepcopy(_receipt(raw))
    receipt.update(id="replayed-receipt", rule_ids=["UNKNOWN"])
    raw["scope_observations"].append(receipt)
    if drop_unknowns:
        raw["unknowns"] = [row for row in raw["unknowns"] if "UNKNOWN" not in row["rule_ids"]]
    after = _read(tmp_path, raw, columnar)
    assert after["UNKNOWN"].status == "UNKNOWN"
    assert not after["UNKNOWN"].evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("field", ["id", "subjects", "fact_ids", "evidence_ids", "scope", "count"])
def test_saved_reader_rejects_changed_receipt_claim(tmp_path, field, columnar):
    raw = _observation(tmp_path)
    receipt = _receipt(raw)
    original = copy.deepcopy(receipt)
    if field == "id":
        receipt[field] = "another-receipt"
    elif field in {"subjects", "fact_ids", "evidence_ids"}:
        receipt[field] = []
    else:
        receipt["data"][field] = "another-scope" if field == "scope" else 999
    assert receipt != original
    row = _read(tmp_path, raw, columnar)["KNOWN"]
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
def test_saved_reader_rejects_receipt_from_another_observation_version(tmp_path, columnar):
    raw = _observation(tmp_path)
    before = _read(tmp_path, raw, columnar)["KNOWN"]
    assert before.status == "PASS" and before.evaluation_proven
    assert raw["schema_version"] == SCHEMA_VERSION
    observation = parse_observation(raw)
    receipt_id = _receipt(raw)["id"]
    receipt = next(
        item for item in observation.records("scope_observations") or () if item.id == receipt_id
    )
    inventory_binding = dependency_binding_id(
        observation.sections,
        observation.coverage.failures,
        observation.evidence,
        include_calls=True,
    )
    serialized_receipt = next(
        item for item in raw["scope_observations"] if item["id"] == receipt_id
    )
    serialized_receipt["data"]["call_scope_proof"]["binding_id"] = rule_evaluation_binding_id(
        inventory_binding, receipt, "2.4.0"
    )
    after = _read(tmp_path, raw, columnar)["KNOWN"]
    assert after.status == "UNKNOWN" and not after.evaluation_proven
