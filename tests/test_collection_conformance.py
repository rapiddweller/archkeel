# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The same fixed wire examples are consumed by Python and the npm adapter."""

import json
from pathlib import Path

import jsonschema
import pytest

from archkeel.ir.facts_codec import ProtocolError, decode_request, decode_response

FIXTURES = Path(__file__).parent / "fixtures" / "collection-protocol"
SCHEMA = Path(__file__).parent.parent / "schema" / "source-facts.schema.json"


@pytest.mark.parametrize("name", ["request-python", "request-dart", "request-typescript"])
def test_shared_requests(name: str) -> None:
    payload = (FIXTURES / f"{name}.json").read_bytes()
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_bytes())).validate(json.loads(payload))
    decode_request(payload)


@pytest.mark.parametrize("name", ["response-python", "response-typescript"])
def test_shared_responses(name: str) -> None:
    payload = (FIXTURES / f"{name}.json").read_bytes()
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_bytes())).validate(json.loads(payload))
    decode_response(payload)


def test_policy_is_outside_shared_wire_schema() -> None:
    payload = (FIXTURES / "invalid-request-policy.json").read_bytes()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_bytes())).validate(
            json.loads(payload)
        )
    with pytest.raises(ProtocolError):
        decode_request(payload)


def test_structurally_valid_dangling_reference_is_rejected() -> None:
    payload = (FIXTURES / "invalid-response-reference.json").read_bytes()
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_bytes())).validate(json.loads(payload))
    with pytest.raises(ProtocolError, match="evidence"):
        decode_response(payload)
