# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The collection process exchanges source inputs, never architecture policy."""

import json

import pytest


def _request() -> bytes:
    return json.dumps(
        {
            "protocol_version": "1.0.0",
            "snapshot": {"root": "/source-project", "git_head": "a" * 40, "dirty": False},
            "scope": {"roots": ["src"], "namespace": "project"},
            "resolver": {"language": "python"},
        }
    ).encode()


def test_collection_request_roundtrip_contains_only_source_inputs() -> None:
    from archkeel.ir.facts_codec import decode_request, encode_request

    request = decode_request(_request())
    assert request.snapshot.git_head == "a" * 40
    assert request.scope.roots == ("src",)
    assert request.resolver.language == "python"
    assert json.loads(encode_request(request)) == json.loads(_request())


@pytest.mark.parametrize("field", ["contract", "baseline", "verdict"])
def test_collection_request_rejects_architecture_policy(field: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload[field] = "policy.json"
    with pytest.raises(ProtocolError, match="fields"):
        decode_request(json.dumps(payload).encode())


@pytest.mark.parametrize("version", ["0.0.0", "2.0.0", None, True])
def test_collection_request_rejects_incompatible_version(version: object) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload["protocol_version"] = version
    with pytest.raises(ProtocolError, match="version"):
        decode_request(json.dumps(payload).encode())


@pytest.mark.parametrize("path", ["../outside", "/outside", "src\\outside", "src/../outside"])
def test_collection_request_rejects_escaping_scope(path: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload["scope"]["roots"] = [path]
    with pytest.raises(ProtocolError, match="scope"):
        decode_request(json.dumps(payload).encode())


def test_collection_request_rejects_unknown_language() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload["resolver"]["language"] = "future-language"
    with pytest.raises(ProtocolError, match="language"):
        decode_request(json.dumps(payload).encode())


def _response() -> dict:
    return {
        "protocol_version": "1.0.0",
        "facts": {
            "state": {"classes": [], "functions": []},
            "candidate_evidence": [],
            "profile": "archkeel-python-analyzer",
            "adapter": {"name": "alternate-parser", "version": "1.0.0", "code_digest": "b" * 64},
            "runtime": {"name": "python", "version": "3.11.12", "required": ">=3.11"},
            "source": {
                "git_head": "a" * 40,
                "dirty": False,
                "source_digest": "c" * 64,
                "scope": ["src/**/*.py"],
            },
            "capabilities": {
                "sections": ["imports"],
                "resolution_features": ["static-imports"],
                "constructs": [],
            },
            "inputs": [{"path": "src/app.py", "digest": "d" * 64, "role": "selected"}],
            "files": [
                {
                    "id": "FILE-app",
                    "rel_path": "src/app.py",
                    "module": "project.app",
                    "package": "project",
                    "all_exports": [],
                    "all_literal": False,
                    "compatibility_logic_free": False,
                    "stable_bindings": [],
                    "blank": False,
                    "evidence_id": "E-app",
                }
            ],
            "imports": [{"kind": "external", "import_id": "IMP-1", "package": "library"}],
            "sections": [
                {
                    "name": "imports",
                    "records": [
                        {
                            "id": "IMP-1",
                            "evidence_class": "FACT",
                            "area": "dependencies",
                            "kind": "import",
                            "title": "Import library",
                            "subjects": ["project.app", "library"],
                            "evidence_ids": ["E-app"],
                            "rule_ids": [],
                            "fact_ids": [],
                            "provenance": [],
                            "data": {
                                "source_module": "project.app",
                                "source_package": "project",
                                "target_module": "library",
                                "target_package": "library",
                                "symbol": None,
                                "binding": "library",
                                "relative_level": 0,
                                "under_type_checking": False,
                                "ordinary_module": True,
                                "module_level_import": True,
                                "reexport": False,
                                "symbols_known": True,
                            },
                        }
                    ],
                }
            ],
            "coverage": {
                "selected_files": ["src/app.py"],
                "files_read": 1,
                "files_parsed": 1,
                "full_scope": True,
                "gaps": [],
            },
            "evidence": [
                {
                    "id": "E-app",
                    "file": "src/app.py",
                    "line": 1,
                    "end_line": 1,
                    "column": 0,
                    "excerpt": "import library",
                }
            ],
            "uncertain_reexports": [],
            "type_shapes": [],
        },
    }


def test_source_response_is_immutable_and_preserves_alternate_parser_identity() -> None:
    from dataclasses import FrozenInstanceError

    from archkeel.ir.facts_codec import decode_response, encode_response

    raw = _response()
    response = decode_response(json.dumps(raw).encode())
    raw["facts"]["sections"][0]["records"][0]["data"]["source_module"] = "changed"
    assert response.facts.sections[0].records[0].data.get("source_module") == "project.app"
    assert response.facts.adapter.name == "alternate-parser"
    assert json.loads(encode_response(response))["facts"]["adapter"]["name"] == "alternate-parser"
    with pytest.raises(FrozenInstanceError):
        response.facts.coverage.files_read = 0


def test_runtime_requirement_state_is_optional_on_old_source_responses() -> None:
    from archkeel.ir.facts_codec import decode_response, encode_response

    raw = _response()
    response = decode_response(json.dumps(raw).encode())
    assert response.facts.runtime.requirement_state == "declared"
    assert (
        json.loads(encode_response(response))["facts"]["runtime"]["requirement_state"] == "declared"
    )


def test_source_response_rejects_unknown_runtime_requirement_state() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["facts"]["runtime"]["requirement_state"] = "maybe"
    with pytest.raises(ProtocolError, match="requirement_state"):
        decode_response(json.dumps(raw).encode())


@pytest.mark.parametrize("field", ["contract", "baseline", "verdict", "violations"])
def test_source_response_rejects_policy_fields(field: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["facts"][field] = []
    with pytest.raises(ProtocolError, match="fields"):
        decode_response(json.dumps(raw).encode())


@pytest.mark.parametrize(
    "invalid",
    [
        "duplicate_id",
        "dangling_evidence",
        "dangling_fact",
        "impossible_coverage",
        "false_complete",
        "partial_without_gap",
        "unregistered_profile",
        "policy_record",
        "wrong_import_payload",
        "escaping_evidence",
    ],
)
def test_source_response_rejects_claims_core_cannot_use(invalid: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    facts = raw["facts"]
    record = facts["sections"][0]["records"][0]
    if invalid == "duplicate_id":
        facts["sections"][0]["records"].append(record.copy())
    elif invalid == "dangling_evidence":
        record["evidence_ids"] = ["missing"]
    elif invalid == "dangling_fact":
        record["fact_ids"] = ["missing"]
    elif invalid == "impossible_coverage":
        facts["coverage"]["files_parsed"] = 2
    elif invalid == "false_complete":
        facts["coverage"]["files_parsed"] = 0
    elif invalid == "partial_without_gap":
        facts["coverage"]["full_scope"] = False
    elif invalid == "unregistered_profile":
        facts["profile"] = "archkeel-future"
    elif invalid == "policy_record":
        record["rule_ids"] = ["R-1"]
    elif invalid == "wrong_import_payload":
        record["data"]["target_module"] = ["library"]
    elif invalid == "escaping_evidence":
        facts["evidence"][0]["file"] = "../outside.py"
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(raw).encode())


def test_source_defined_nested_names_do_not_inherit_envelope_field_constraints() -> None:
    from archkeel.ir.facts_codec import decode_response

    payload = _response()
    record = payload["facts"]["sections"][0]["records"][0]
    record["data"]["annotations"] = {
        "status": {"text": "Literal[State.READY]"},
        "contract": {"text": "str"},
    }
    facts = decode_response(json.dumps(payload).encode()).facts
    assert facts.sections[0].records[0].data.get("annotations") is not None


def test_snapshot_root_accepts_native_absolute_windows_paths() -> None:
    from archkeel.ir.facts_codec import decode_request

    payload = json.loads(_request())
    payload["snapshot"]["root"] = "C:" + chr(92) + "source-project"
    assert decode_request(json.dumps(payload).encode()).snapshot.root == payload["snapshot"]["root"]
    payload["snapshot"]["root"] = "C:source-project"
    with pytest.raises(ValueError, match="absolute"):
        decode_request(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_runtime_required",
        "missing_constructs",
        "invalid_support",
        "duplicate_construct",
        "unknown_construct",
    ],
)
def test_common_runtime_and_construct_contract_rejects_malformed_claims(invalid: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    capabilities = raw["facts"]["capabilities"]
    if invalid == "missing_runtime_required":
        del raw["facts"]["runtime"]["required"]
    elif invalid == "missing_constructs":
        del capabilities["constructs"]
    elif invalid == "invalid_support":
        capabilities["constructs"] = [{"name": "assert", "status": "supported"}]
    elif invalid == "duplicate_construct":
        capabilities["constructs"] = [{"name": "assert", "status": "decided"}] * 2
    else:
        capabilities["constructs"] = [{"name": "future_construct", "status": "decided"}]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(raw).encode())


def test_published_wire_schema_accepts_real_collector_payload(tmp_path) -> None:
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from test_collection_boundary_regressions import _facts

    from archkeel.ir.facts_codec import encode_response
    from archkeel.ir.protocol import CollectionResponse

    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    payload = json.loads(encode_response(CollectionResponse(_facts(tmp_path))))
    Draft202012Validator(schema).validate(payload)
