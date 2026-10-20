# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""New call evidence cannot change the meaning of published wire resources."""

import copy
import json

import pytest
from test_call_owner_policy import _observe
from test_delta import _model, _record
from test_result_schema import _validator

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import (
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
    result_payload,
)
from archkeel.ir.facts import RecordData, call_binding
from archkeel.ir.model import Diagnostic, RunResult


@pytest.mark.parametrize("version", ["6.0", "7.0", "8.0", "9.0"])
@pytest.mark.parametrize("wire", ["2.0.0", "2.1.0"])
def test_command_versions_preserve_their_observation_boundary(version, wire):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = wire
    result = RunResult(
        "check",
        2,
        observation=parse_observation(raw),
        diagnostics=(Diagnostic("parse_error", "fixture", "Unavailable.", "Repair."),),
    )
    name = (
        "command-result.schema.json"
        if version == "6.0"
        else f"command-result-{version}.schema.json"
    )
    validator = _validator(name)
    packet = result_payload(result)
    assert validator.is_valid(packet) is (wire == "2.0.0" or version == "9.0")
    packet["schema_version"] = "future-command-version"
    assert not validator.is_valid(packet)


@pytest.mark.parametrize("profile", ["decoded", "python-decoded"])
@pytest.mark.parametrize("wire", ["1.3.0", "2.0.0", "2.1.0"])
@pytest.mark.parametrize("version", ["2.0.0", "2.1.0"])
def test_decoded_resource_ids_keep_their_version_scope(profile, wire, version):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = wire
    validator = _validator("command-result-9.0.schema.json").evolve(
        schema={"$ref": f"urn:archkeel:architecture-ir:{profile}:{version}"}
    )
    assert validator.is_valid(raw) is (wire == version or version == "2.0.0" and wire == "1.3.0")


@pytest.mark.parametrize(
    "binding",
    [
        {"origin": "future_origin", "target": "sample.page", "evidence_ids": ["e"]},
        {"origin": "direct", "target": "sample.page", "evidence_ids": ["e"], "extra": True},
        {"origin": "direct", "target": None, "evidence_ids": ["e"]},
        {"origin": "direct", "target": "sample.page", "evidence_ids": []},
    ],
)
def test_current_reader_refuses_future_or_malformed_call_bindings(binding):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.1.0"
    raw["calls"] = [_record("call", kind="call", data={"call_binding": binding})]
    with pytest.raises(ValueError):
        parse_observation(raw)


@pytest.mark.parametrize(
    "change,value",
    [
        ("descriptor_owner_module", "other"),
        ("descriptor_member", "utcnow"),
        ("descriptor_kind", "function"),
        ("runtime_name", "other-python"),
        ("runtime_implementation", "pypy"),
        ("stdlib_source_digest", "0"),
    ],
)
def test_native_datetime_proof_rejects_tampered_descriptor_identity(change, value):
    proof = {
        "kind": "native_descriptor",
        "target": "datetime.datetime.now",
        "runtime_name": "python",
        "runtime_version": "3.13.0",
        "runtime_implementation": "cpython",
        "descriptor_owner_module": "datetime",
        "descriptor_owner_qualname": "datetime",
        "descriptor_member": "now",
        "descriptor_kind": "classmethod_descriptor",
        "stdlib_source_digest": "a" * 64,
        "witness_evidence_ids": ("call-evidence",),
    }
    proof[change] = value
    payload = RecordData(
        (
            ("origin", "native"),
            ("target", "datetime.datetime.now"),
            ("evidence_ids", ("call-evidence",)),
            ("proof", RecordData(tuple(sorted(proof.items())))),
        )
    )
    with pytest.raises(ValueError, match="native descriptor proof"):
        call_binding(payload)


@pytest.mark.parametrize("profile", ["decoded", "python-decoded"])
def test_current_python_schema_validates_call_binding_shape(profile):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.1.0"
    raw["calls"] = [
        _record(
            "call",
            kind="call",
            data={
                "source_scope": "sample.run",
                "source_module": "sample",
                "expression": "page",
                "status": "resolved",
                "targets": ["sample.page"],
                "candidate_count": 1,
                "candidates_truncated": False,
                "reason": "",
                "target_evidence_ids": [],
                "call_binding": {
                    "origin": "direct",
                    "target": "sample.page",
                    "evidence_ids": ["e"],
                },
            },
        )
    ]
    validator = _validator("command-result-9.0.schema.json").evolve(
        schema={"$ref": f"urn:archkeel:architecture-ir:{profile}:2.1.0"}
    )
    assert validator.is_valid(raw)
    malformed = copy.deepcopy(raw)
    malformed["calls"][0]["data"]["call_binding"]["origin"] = "future_origin"
    assert not validator.is_valid(malformed)

    explicit_null = copy.deepcopy(raw)
    explicit_null["calls"][0]["data"]["call_binding"] = None
    assert validator.is_valid(explicit_null)
    del explicit_null["calls"][0]["data"]["call_binding"]
    assert not validator.is_valid(explicit_null)


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("wire", ["1.2.0", "1.3.0", "2.0.0", "2.1.0"])
def test_missing_call_consideration_is_rejected_only_for_current_python(wire, columnar):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = wire
    raw["calls"] = [
        _record("unconsidered", kind="call"),
        _record("considered", kind="call", data={"call_binding": None}),
    ]
    if columnar:
        raw = decode_canonical_model(encode_canonical_model(raw))
    if wire == "2.1.0":
        with pytest.raises(ValueError, match="call_binding"):
            parse_observation(raw)
    else:
        assert len(parse_observation(raw).records("calls")) == 2


@pytest.mark.parametrize("columnar", [False, True])
def test_current_python_explicit_null_call_consideration_roundtrips(columnar):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.1.0"
    raw["calls"] = [_record("considered", kind="call", data={"call_binding": None})]
    if columnar:
        raw = decode_canonical_model(encode_canonical_model(raw))
    assert observation_payload(parse_observation(raw))["calls"] == raw["calls"]


@pytest.mark.parametrize("analyzer", ["archkeel-typescript-imports", "archkeel-dart-analyzer"])
def test_current_non_python_calls_do_not_require_python_binding_evidence(analyzer):
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.1.0"
    raw["analyzer"]["name"] = analyzer
    raw["typing_signals"] = raw["constructs"] = None
    raw["calls"] = [
        _record(
            "call",
            kind="call",
            data={
                "source_scope": "sample.run",
                "source_module": "sample",
                "expression": "page",
                "status": "resolved",
                "targets": ["sample.page"],
                "candidate_count": 1,
                "candidates_truncated": False,
                "reason": "",
                "target_evidence_ids": [],
            },
        )
    ]
    assert len(parse_observation(raw).records("calls")) == 1
    validator = _validator("command-result-9.0.schema.json").evolve(
        schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.1.0"}
    )
    assert validator.is_valid(raw)


@pytest.mark.parametrize("columnar", [False, True])
def test_saved_call_owner_pass_requires_every_call_consideration(tmp_path, columnar):
    result, row = _observe(
        tmp_path,
        "def run(unknown):\n    unknown()\n",
        allowed=("sample.caller.run",),
    )
    assert row.status == "PASS" and row.evaluation_proven
    raw = observation_payload(result.observation)
    call = next(item for item in raw["calls"] if item["data"]["expression"] == "unknown")
    assert call["data"]["call_binding"] is None
    path = tmp_path / "architecture.json"
    path.write_text(json.dumps(encode_canonical_model(raw) if columnar else raw))
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed == row
    del call["data"]["call_binding"]
    path.write_text(json.dumps(encode_canonical_model(raw) if columnar else raw))
    replay = run_saved_report(path)
    assert replay.exit_code == 2 and replay.observation is None
    assert replay.declared_rules == "UNKNOWN"
