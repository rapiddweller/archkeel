"""The collection process exchanges source inputs, never architecture policy."""

import json

import pytest


def _request() -> bytes:
    return json.dumps(
        {
            "protocol_version": "1.0.0",
            "snapshot": {"root": "/tmp/project", "git_head": "a" * 40, "dirty": False},
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
