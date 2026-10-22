# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The collection process exchanges source inputs, never architecture policy."""

import json
import zlib

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
    assert request.protocol_version == "1.0.0"
    assert json.loads(encode_request(request)) == json.loads(_request())


@pytest.mark.parametrize("field", ["contract", "baseline", "verdict"])
def test_collection_request_rejects_architecture_policy(field: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload[field] = "policy.json"
    with pytest.raises(ProtocolError, match="fields"):
        decode_request(json.dumps(payload).encode())


def test_new_request_is_labeled_v3() -> None:
    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import CollectionRequest, PythonSettings, SnapshotInput, SourceScope

    request = CollectionRequest(
        SnapshotInput("/source-project", "a" * 40, False),
        SourceScope(("src",), "project"),
        PythonSettings(),
    )
    payload = json.loads(encode_request(request))
    assert payload["protocol_version"] == "3.0.0"
    assert decode_request(json.dumps(payload).encode()).protocol_version == "3.0.0"


@pytest.fixture(scope="module")
def _request_validator():
    from pathlib import Path

    from jsonschema import Draft202012Validator

    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    return Draft202012Validator(schema)


@pytest.mark.parametrize("phase", ["collect", "imports", "providers"])
def test_v4_python_collection_phase_roundtrips(phase: str, _request_validator) -> None:
    from dataclasses import replace

    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import ProtocolVersion, PythonCollectionPhase, PythonSettings

    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion.V4,
        resolver=PythonSettings(phase=PythonCollectionPhase(phase)),
    )
    encoded = encode_request(request)
    decoded = decode_request(encoded)
    assert decoded == request
    assert isinstance(decoded.resolver, PythonSettings)
    assert decoded.resolver.phase is PythonCollectionPhase(phase)
    assert json.loads(encoded)["resolver"] == {
        "language": "python",
        "provider_sources": [],
        "phase": phase,
    }
    _request_validator.validate(json.loads(encoded))


def test_v5_python_request_keeps_v4_collection_settings(_request_validator) -> None:
    from dataclasses import replace

    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import ProtocolVersion, PythonSettings

    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion.V5,
        resolver=PythonSettings(),
    )
    encoded = encode_request(request)
    _request_validator.validate(json.loads(encoded))
    assert decode_request(encoded) == request


def test_v6_python_request_keeps_v4_collection_settings(_request_validator) -> None:
    from dataclasses import replace

    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import ProtocolVersion, PythonSettings

    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion.V6,
        resolver=PythonSettings(),
    )
    encoded = encode_request(request)
    _request_validator.validate(json.loads(encoded))
    assert decode_request(encoded) == request


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0", "3.0.0"])
def test_default_python_phase_preserves_legacy_request_bytes(version: str) -> None:
    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import PythonCollectionPhase, PythonSettings

    expected = json.loads(_request())
    expected["protocol_version"] = version
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    request = decode_request(encoded)
    assert isinstance(request.resolver, PythonSettings)
    assert request.resolver.phase is PythonCollectionPhase.COLLECT
    assert encode_request(request) == encoded


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0", "3.0.0"])
def test_legacy_encoder_rejects_python_import_survey(version: str) -> None:
    from dataclasses import replace

    from archkeel.ir.facts_codec import ProtocolError, decode_request, encode_request
    from archkeel.ir.protocol import ProtocolVersion, PythonCollectionPhase, PythonSettings

    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion(version),
        resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS),
    )
    with pytest.raises(ProtocolError, match="phase requires collection protocol 4.0.0"):
        encode_request(request)


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0", "3.0.0"])
@pytest.mark.parametrize("phase", ["collect", "imports", "providers"])
def test_legacy_requests_reject_python_phase_fields(
    version: str, phase: str, _request_validator
) -> None:
    from jsonschema import ValidationError

    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload["protocol_version"] = version
    payload["resolver"]["phase"] = phase
    with pytest.raises(ProtocolError, match="resolver fields"):
        decode_request(json.dumps(payload).encode())
    with pytest.raises(ValidationError):
        _request_validator.validate(payload)


@pytest.mark.parametrize(
    "phase_fields",
    [{}, {"phase": None}, {"phase": True}, {"phase": []}, {"phase": "future"}],
    ids=["missing", "null", "boolean", "array", "unknown"],
)
def test_v4_requests_reject_missing_or_invalid_python_phase(
    phase_fields: dict, _request_validator
) -> None:
    from jsonschema import ValidationError

    from archkeel.ir.facts_codec import ProtocolError, decode_request

    payload = json.loads(_request())
    payload["protocol_version"] = "4.0.0"
    payload["resolver"].update(provider_sources=[], **phase_fields)
    with pytest.raises(ProtocolError, match="phase|resolver fields"):
        decode_request(json.dumps(payload).encode())
    with pytest.raises(ValidationError):
        _request_validator.validate(payload)


def test_import_survey_rejects_provider_sources_and_keeps_positional_settings(
    _request_validator,
) -> None:
    import hashlib
    from dataclasses import replace

    from jsonschema import ValidationError

    from archkeel.ir.facts import Language
    from archkeel.ir.facts_codec import ProtocolError, decode_request, encode_request
    from archkeel.ir.protocol import (
        ProtocolVersion,
        PythonCollectionPhase,
        PythonProviderSource,
        PythonSettings,
    )

    source = "def convert(): pass\n"
    provider = PythonProviderSource(
        "vendor",
        ".archkeel-providers/vendor.py",
        source,
        hashlib.sha256(source.encode()).hexdigest(),
    )
    settings = PythonSettings(Language.PYTHON, (provider,))
    assert settings.phase is PythonCollectionPhase.COLLECT
    request = replace(
        decode_request(_request()), protocol_version=ProtocolVersion.V4, resolver=settings
    )
    payload = json.loads(encode_request(request))
    _request_validator.validate(payload)
    payload["resolver"]["phase"] = "imports"
    with pytest.raises(ProtocolError, match="import survey cannot include provider sources"):
        decode_request(json.dumps(payload).encode())
    with pytest.raises(ProtocolError, match="import survey cannot include provider sources"):
        encode_request(
            replace(request, resolver=replace(settings, phase=PythonCollectionPhase.IMPORTS))
        )
    with pytest.raises(ValidationError):
        _request_validator.validate(payload)


@pytest.mark.parametrize("version", ["0.0.0", "9.0.0", None, True])
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


def test_collection_json_keeps_sorted_nested_object_order() -> None:
    from archkeel.ir.facts_codec import _decode

    raw = _response()
    raw["facts"]["sections"][0]["records"][0]["data"]["codec_order"] = {
        "z": {"ä": 2, "a": 1},
        "a": [],
    }
    decoded = _decode(json.dumps(raw, ensure_ascii=False).encode())
    assert list(decoded) == ["facts", "protocol_version"]
    facts = decoded["facts"]
    assert list(facts) == sorted(raw["facts"])
    nested = facts["sections"][0]["records"][0]["data"]["codec_order"]
    assert list(nested) == ["a", "z"]
    assert list(nested["z"]) == ["a", "ä"]


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_collection_json_rejects_nested_nonfinite_numbers(token: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["facts"]["sections"][0]["records"][0]["data"]["codec_number"] = ["CODEC_NUMBER"]
    payload = json.dumps(raw).encode().replace(b'"CODEC_NUMBER"', token.encode())
    with pytest.raises(ProtocolError, match="JSON numbers must be finite"):
        decode_response(payload)


@pytest.mark.parametrize(
    "payload,reason",
    [
        (b'{"value":NaN,"value":0}', "duplicate field value"),
        (b'{"outer":{"value":1e400,"value":0}}', "duplicate field value"),
        (b'{"value":NaN} trailing', "Extra data"),
        (b'{"value":1e400,}', "Expecting property name"),
        (b'{"value":-NaN}', "Expecting value"),
    ],
)
def test_collection_json_reports_duplicate_or_syntax_errors_before_nonfinite(payload, reason):
    from archkeel.ir.facts_codec import ProtocolError, decode_request, decode_response

    for decoder in (decode_request, decode_response):
        with pytest.raises(ProtocolError, match=reason):
            decoder(payload)


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


@pytest.mark.parametrize(
    "version", ["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0"]
)
def test_response_encoder_validates_without_reparsing_its_json(version):
    from unittest.mock import patch

    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    response = CollectionResponse(decode_response(json.dumps(_response()).encode()).facts, version)
    with patch("archkeel.ir.facts_codec._decode", side_effect=AssertionError("JSON reparse")):
        if version == "5.0.0":
            from archkeel.ir import facts_codec as codec
            from archkeel.ir.protocol import ProtocolVersion

            runtime = codec._runtime_payload(response.facts.runtime, ProtocolVersion.V5)
            raw = codec._facts_payload(response.facts, ProtocolVersion.V5, runtime)
            with patch(
                "archkeel.ir.facts_codec._json_value",
                side_effect=AssertionError("deep-copy JSON normalization"),
            ):
                codec._compact_source_facts(raw)
            encoded = encode_response(response)
        else:
            encoded = encode_response(response)
    assert decode_response(encoded) == response
    document = zlib.decompress(encoded) if version == "8.0.0" else encoded
    assert (
        document
        == json.dumps(
            json.loads(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


@pytest.mark.parametrize(
    "version", ["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0"]
)
def test_response_encoder_still_rejects_invalid_facts_without_json_reparse(version):
    from dataclasses import replace
    from unittest.mock import patch

    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    facts = decode_response(json.dumps(_response()).encode()).facts
    invalid = replace(facts, coverage=replace(facts.coverage, files_parsed=999))
    with (
        patch("archkeel.ir.facts_codec._decode", side_effect=AssertionError("JSON reparse")),
        pytest.raises(ProtocolError, match="impossible collection coverage counts"),
    ):
        encode_response(CollectionResponse(invalid, version))


def test_nested_record_freezing_validates_each_json_value_once():
    from unittest.mock import patch

    from archkeel.ir import facts_codec

    raw = {"value": 1}
    for _ in range(32):
        raw = {"nested": raw}
    with patch.object(facts_codec, "_json_value", wraps=facts_codec._json_value) as validate:
        frozen = facts_codec.freeze_data(raw)
    assert validate.call_count == 34
    assert facts_codec.thaw_data(frozen) == raw


def test_legacy_response_defaults_runtime_state_and_roundtrips_as_legacy() -> None:
    from archkeel.ir.facts_codec import decode_response, encode_response

    raw = _response()
    response = decode_response(json.dumps(raw).encode())
    assert response.protocol_version == "1.0.0"
    assert response.facts.runtime.requirement_state == "declared"
    encoded = json.loads(encode_response(response))
    assert encoded["protocol_version"] == "1.0.0"
    assert "requirement_state" not in encoded["facts"]["runtime"]


def test_current_response_requires_runtime_state_and_is_labeled_v3(tmp_path) -> None:
    from pathlib import Path

    import jsonschema
    from test_collection_boundary_regressions import _facts

    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    encoded = encode_response(CollectionResponse(_facts(tmp_path)))
    payload = json.loads(encoded)
    assert payload["protocol_version"] == "3.0.0"
    assert "requirement_state" in payload["facts"]["runtime"]
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    jsonschema.Draft202012Validator(schema).validate(payload)
    assert decode_response(encoded).protocol_version == "3.0.0"

    legacy_runtime_schema = json.loads(
        (
            Path(__file__).parent / "fixtures/collection-protocol/legacy-runtime-schemas.json"
        ).read_bytes()
    )["source_facts_1"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(legacy_runtime_schema).validate(payload["facts"]["runtime"])


def test_encoders_reject_unsupported_versions(tmp_path) -> None:
    from test_collection_boundary_regressions import _facts

    from archkeel.ir.facts_codec import ProtocolError, encode_request, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    request = CollectionRequest(
        SnapshotInput("/source-project", "a" * 40, False),
        SourceScope(("src",), "project"),
        PythonSettings(),
        "9.0.0",
    )
    with pytest.raises(ProtocolError, match="version"):
        encode_request(request)
    with pytest.raises(ProtocolError, match="version"):
        encode_response(CollectionResponse(_facts(tmp_path), "9.0.0"))


def test_legacy_encoder_rejects_nondefault_runtime_state(tmp_path) -> None:
    from dataclasses import replace

    from test_collection_boundary_regressions import _facts

    from archkeel.ir.facts_codec import ProtocolError, encode_response
    from archkeel.ir.protocol import CollectionResponse

    facts = _facts(tmp_path)
    facts = replace(facts, runtime=replace(facts.runtime, requirement_state="metadata_missing"))
    with pytest.raises(ProtocolError, match="cannot carry"):
        encode_response(CollectionResponse(facts, "1.0.0"))


def test_response_rejects_runtime_state_for_wrong_version() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["facts"]["runtime"]["requirement_state"] = "declared"
    with pytest.raises(ProtocolError, match="runtime fields"):
        decode_response(json.dumps(raw).encode())

    raw["protocol_version"] = "2.0.0"
    del raw["facts"]["runtime"]["requirement_state"]
    with pytest.raises(ProtocolError, match="runtime fields"):
        decode_response(json.dumps(raw).encode())


def test_source_response_rejects_unknown_runtime_requirement_state() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    raw = _response()
    raw["protocol_version"] = "2.0.0"
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


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
def test_frozen_legacy_shape_vocabulary_roundtrips_without_wire_changes(version: str) -> None:
    from pathlib import Path

    import jsonschema

    from archkeel.ir.facts_codec import decode_response, encode_response

    root = Path(__file__).parent / "fixtures/collection-protocol"
    payload = (root / f"source-facts-{version}.json").read_bytes()
    assert encode_response(decode_response(payload)) == payload
    schema = json.loads((root / "legacy-type-shapes.schema.json").read_bytes())
    for item in json.loads(payload)["facts"]["type_shapes"]:
        jsonschema.Draft202012Validator(schema).validate(item["shape"])


def _list_shape() -> dict:
    return {
        "kind": "list",
        "text": "[str]",
        "elements": [{"kind": "name", "text": "str", "name": "str"}],
    }


def test_new_list_shape_roundtrips_with_the_current_protocol_and_schema() -> None:
    from pathlib import Path

    import jsonschema

    from archkeel.ir.facts_codec import decode_response, encode_response

    raw = _response()
    raw["protocol_version"] = "3.0.0"
    raw["facts"]["runtime"]["requirement_state"] = "declared"
    raw["facts"]["type_shapes"] = [{"expression": "[str]", "shape": _list_shape()}]
    encoded = encode_response(decode_response(json.dumps(raw).encode()))
    assert json.loads(encoded) == raw
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    jsonschema.Draft202012Validator(schema).validate(raw)


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
@pytest.mark.parametrize(
    "nesting", ["root", "owner", "head", "argument", "left", "right", "unpack"]
)
def test_legacy_protocol_rejects_new_list_at_every_shape_nesting(
    version: str, nesting: str
) -> None:
    from pathlib import Path

    import jsonschema

    from archkeel.ir.facts_codec import ProtocolError, decode_response

    shape = _list_shape()
    name = {"kind": "name", "text": "str", "name": "str"}
    if nesting == "owner":
        shape = {"kind": "member", "text": "value.member", "owner": shape, "member": "member"}
    elif nesting in {"head", "argument"}:
        shape = {
            "kind": "application",
            "text": "Container[value]",
            "head": shape if nesting == "head" else name,
            "arguments": [shape if nesting == "argument" else name],
            "tuple_arguments": False,
        }
    elif nesting in {"left", "right"}:
        shape = {
            "kind": "union",
            "text": "value | str",
            "left": shape if nesting == "left" else name,
            "right": shape if nesting == "right" else name,
        }
    elif nesting == "unpack":
        shape = {"kind": "unpack", "text": "*value", "argument": shape}
    raw = _response()
    raw["protocol_version"] = version
    if version == "2.0.0":
        raw["facts"]["runtime"]["requirement_state"] = "declared"
    raw["facts"]["type_shapes"] = [{"expression": "value", "shape": shape}]
    with pytest.raises(ProtocolError, match="shape"):
        decode_response(json.dumps(raw).encode())
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(raw)


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
def test_encoder_cannot_label_list_shapes_as_legacy(version: str) -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    raw = _response()
    raw["protocol_version"] = "3.0.0"
    raw["facts"]["runtime"]["requirement_state"] = "declared"
    raw["facts"]["type_shapes"] = [{"expression": "[str]", "shape": _list_shape()}]
    facts = decode_response(json.dumps(raw).encode()).facts
    with pytest.raises(ProtocolError, match="shape"):
        encode_response(CollectionResponse(facts, protocol_version=version))


@pytest.mark.parametrize("invalid", ["missing", "extra", "wrong_type", "bad_child"])
def test_list_shape_rejects_malformed_fields_in_codec_and_schema(invalid: str) -> None:
    from pathlib import Path

    import jsonschema

    from archkeel.ir.facts_codec import ProtocolError, decode_response

    shape = _list_shape()
    if invalid == "missing":
        del shape["elements"]
    elif invalid == "extra":
        shape["arguments"] = []
    elif invalid == "wrong_type":
        shape["elements"] = "str"
    else:
        shape["elements"] = [{"kind": "name", "text": "str", "name": "str", "extra": 1}]
    raw = _response()
    raw["protocol_version"] = "3.0.0"
    raw["facts"]["runtime"]["requirement_state"] = "declared"
    raw["facts"]["type_shapes"] = [{"expression": "[str]", "shape": shape}]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(raw).encode())
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes()
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(raw)


def test_record_freezing_validates_the_envelope_and_data_in_one_walk():
    from unittest.mock import patch

    from archkeel.ir import facts_codec

    record = _response()["facts"]["sections"][0]["records"][0]
    record["data"] = {"items": [{"nested": [1, True, None, "text"]}]}

    def values(value):
        children = (
            value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
        )
        return 1 + sum(values(child) for child in children)

    with patch.object(facts_codec, "_json_value", wraps=facts_codec._json_value) as validate:
        parsed = facts_codec.parse_record(record)
    assert validate.call_count == values(record)
    assert facts_codec.record_payload(parsed) == record


@pytest.mark.parametrize(
    "bad",
    [(1,), {1: "value"}, float("nan"), float("inf"), object()],
    ids=["tuple", "nonstring-key", "nan", "infinity", "object"],
)
def test_owned_response_path_keeps_raw_parser_and_encoder_validation(bad, monkeypatch):
    import copy

    from archkeel.ir import facts_codec as codec

    raw = _response()
    record = raw["facts"]["sections"][0]["records"][0]
    record["data"]["poison"] = bad
    with pytest.raises(codec.ProtocolError):
        codec.parse_record(record)
    evidence = copy.deepcopy(raw["facts"]["evidence"][0])
    evidence["excerpt"] = bad
    with pytest.raises((codec.ProtocolError, ValueError)):
        codec.parse_evidence(evidence)
    valid = codec.decode_response(json.dumps(_response()).encode())
    original = codec._facts_payload

    def poisoned(*args):
        result = original(*args)
        result["sections"][0]["records"][0]["data"]["poison"] = bad
        return result

    monkeypatch.setattr(codec, "_facts_payload", poisoned)
    with pytest.raises((codec.ProtocolError, ValueError, TypeError)):
        codec.encode_response(valid)


def test_owned_decoder_does_not_recopy_validated_record_trees():
    from unittest.mock import patch

    from archkeel.ir import facts_codec as codec

    raw = _response()
    record = raw["facts"]["sections"][0]["records"][0]
    record["data"]["nested"] = {"items": [1, "text"]}
    with patch.object(codec, "_json_value", wraps=codec._json_value) as copy_tree:
        decoded = codec.decode_response(json.dumps(raw).encode())
    assert copy_tree.call_count == 0
    assert codec.record_payload(decoded.facts.sections[0].records[0]) == record
    with patch.object(codec, "_json_value", wraps=codec._json_value) as copy_tree:
        public = codec.parse_record(record)
    assert copy_tree.call_count > 0
    record["data"]["nested"]["items"].append("later")
    assert codec.record_payload(public)["data"]["nested"]["items"] == [1, "text"]


@pytest.mark.parametrize("version", ["3.0.0", "5.0.0"])
def test_encoder_checks_owned_json_before_semantic_claims(version):
    from dataclasses import replace

    from archkeel.ir import facts_codec as codec
    from archkeel.ir.model import RecordData

    response = codec.decode_response(json.dumps(_response()).encode())
    section = response.facts.sections[0]
    record = section.records[0]
    invalid = replace(
        record,
        data=RecordData((*record.data.entries, ("poison", RecordData(((1, "bad key"),))))),
    )
    facts = replace(
        response.facts,
        adapter=replace(response.facts.adapter, code_digest="invalid digest"),
        sections=(
            replace(section, records=(invalid, *section.records[1:])),
            *response.facts.sections[1:],
        ),
    )
    # Owned raw JSON must be valid before semantic claims such as the adapter digest are checked.
    with pytest.raises(codec.ProtocolError, match="JSON fields must be strings"):
        codec.encode_response(replace(response, facts=facts, protocol_version=version))


def _response_with(version: str):
    from archkeel.ir.facts_codec import decode_response
    from archkeel.ir.protocol import CollectionResponse

    return CollectionResponse(decode_response(json.dumps(_response()).encode()).facts, version)


def test_v8_request_roundtrips_with_features(_request_validator) -> None:
    from dataclasses import replace

    from archkeel.ir.facts import GATED_RESOLUTION_FEATURES
    from archkeel.ir.facts_codec import decode_request, encode_request
    from archkeel.ir.protocol import ProtocolVersion, PythonSettings

    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion.V8,
        resolver=PythonSettings(features=tuple(sorted(GATED_RESOLUTION_FEATURES))),
    )
    encoded = encode_request(request)
    assert json.loads(encoded)["resolver"]["features"] == sorted(GATED_RESOLUTION_FEATURES)
    _request_validator.validate(json.loads(encoded))
    assert decode_request(encoded) == request


def test_v8_response_is_zlib_framed_ordinary_facts(_request_validator) -> None:
    from archkeel.ir.facts_codec import decode_response, encode_response

    response = _response_with("8.0.0")
    encoded = encode_response(response)
    assert encoded[:1] == b"\x78"
    envelope = json.loads(zlib.decompress(encoded))
    assert envelope["protocol_version"] == "8.0.0"
    assert "encoding" not in envelope["facts"] and "string_table" not in envelope["facts"]
    _request_validator.validate(envelope)
    assert decode_response(encoded) == response
    # No pools: the facts object is exactly what V4 puts on the wire.
    assert envelope["facts"] == json.loads(encode_response(_response_with("4.0.0")))["facts"]


@pytest.mark.parametrize(
    "version", ["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0"]
)
def test_every_protocol_version_decodes_what_it_encodes(version: str) -> None:
    from archkeel.ir.facts_codec import decode_response, encode_response

    response = _response_with(version)
    assert decode_response(encode_response(response)) == response


def test_only_v8_responses_are_compressed() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response

    plain_v8 = zlib.decompress(encode_response(_response_with("8.0.0")))
    with pytest.raises(ProtocolError, match="only collection protocol 8.0.0"):
        decode_response(plain_v8)
    with pytest.raises(ProtocolError, match="only collection protocol 8.0.0"):
        decode_response(zlib.compress(encode_response(_response_with("7.0.0")), 1))


def test_v8_decoder_rejects_corrupt_truncated_and_padded_streams() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response

    encoded = encode_response(_response_with("8.0.0"))
    for damaged in (encoded[:-4], encoded + b"x", encoded[:20] + b"\x00" + encoded[21:]):
        with pytest.raises(ProtocolError):
            decode_response(damaged)


def test_v8_decompression_is_bounded_at_sixteen_times_the_output_limit() -> None:
    from archkeel.ir.facts_codec import ProtocolError, decode_response

    padding = b'{"protocol_version":"8.0.0","pad":"' + b"a" * 20_000 + b'"}'
    bomb = zlib.compress(padding, 1)
    assert len(bomb) < 1_000
    with pytest.raises(ProtocolError, match="exceeds its 16000 byte limit"):
        decode_response(bomb, output_limit=1_000)
    # Within the bound the stream is accepted as framing; the response is then judged on content.
    with pytest.raises(ProtocolError, match="response fields mismatch"):
        decode_response(bomb, output_limit=2_000)


def _emitting(payload: bytes, **limits):
    import sys

    from archkeel.analyzer.process import ProcessCollector

    script = f"import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write({payload!r})\n"
    return ProcessCollector((sys.executable, "-B", "-c", script), **limits)


def _v8_import_survey_request(root):
    from archkeel.ir.protocol import (
        CollectionRequest,
        ProtocolVersion,
        PythonCollectionPhase,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "project"),
        PythonSettings(phase=PythonCollectionPhase.IMPORTS),
        ProtocolVersion.V8,
    )


def test_v8_invalid_facts_are_a_protocol_error_at_the_process_boundary(tmp_path) -> None:
    from archkeel.ir.facts_codec import encode_response
    from archkeel.ir.protocol import CollectionError, CollectionErrorKind

    envelope = json.loads(zlib.decompress(encode_response(_response_with("8.0.0"))))
    envelope["facts"]["coverage"]["files_parsed"] = 999
    payload = zlib.compress(json.dumps(envelope).encode(), 1)

    result = _emitting(payload).collect_response(_v8_import_survey_request(tmp_path))

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "impossible collection coverage counts" in result.message


def test_output_limit_counts_compressed_bytes_and_bounds_decompression(tmp_path) -> None:
    from archkeel.ir.protocol import CollectionError, CollectionErrorKind

    request = _v8_import_survey_request(tmp_path)
    bomb = zlib.compress(b'{"protocol_version":"8.0.0","pad":"' + b"a" * 20_000 + b'"}', 1)

    inflated = _emitting(bomb, output_limit_bytes=1_000).collect_response(request)
    assert isinstance(inflated, CollectionError)
    assert inflated.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "exceeds its 16000 byte limit" in inflated.message

    oversized = _emitting(bomb, output_limit_bytes=len(bomb) - 1).collect_response(request)
    assert isinstance(oversized, CollectionError)
    assert oversized.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "Collector output exceeded" in oversized.message
