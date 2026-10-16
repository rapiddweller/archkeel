# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collector wire vocabulary has one typed owner and preserves old bytes."""

import json
from dataclasses import FrozenInstanceError, replace

import pytest
from test_collection_protocol import _request, _response

from archkeel.ir.facts_codec import (
    ProtocolError,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("version", ["1.0.0", "2.0.0", "3.0.0"])
def test_wire_request_decodes_owned_language_and_version(language, version):
    from archkeel.ir.facts import Language
    from archkeel.ir.protocol import ProtocolVersion

    raw = json.loads(_request())
    raw["protocol_version"] = version
    raw["resolver"] = {"language": language}
    if language == "typescript":
        raw["resolver"]["tsconfig"] = "tsconfig.json"
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    request = decode_request(payload)
    assert request.resolver.language is Language(language)
    assert request.protocol_version is ProtocolVersion(version)
    assert encode_request(request) == payload


@pytest.mark.parametrize(
    "state",
    ["declared", "metadata_missing", "metadata_invalid", "requirement_missing", "requirement_invalid"],
)
def test_response_decodes_runtime_state_once_and_preserves_wire_bytes(state):
    from archkeel.ir.facts import RuntimeRequirementState

    raw = _response()
    raw["protocol_version"] = "3.0.0"
    raw["facts"]["runtime"]["requirement_state"] = state
    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    response = decode_response(payload)
    assert response.facts.runtime.requirement_state is RuntimeRequirementState(state)
    assert encode_response(response) == payload


def test_language_aliases_reference_the_same_owner():
    from archkeel.analyzer.runtime import Language as RuntimeLanguage
    from archkeel.check.ports import Language as PortLanguage
    from archkeel.ir.facts import Language
    from archkeel.ir.profiles import Language as ProfileLanguage

    assert RuntimeLanguage is PortLanguage is ProfileLanguage is Language
    assert Language.PYTHON.value == "python"


def test_fixed_settings_discriminators_are_immutable_enum_members():
    from archkeel.ir.facts import Language
    from archkeel.ir.protocol import DartSettings, PythonSettings, TypeScriptSettings

    for settings, expected in [
        (PythonSettings(), Language.PYTHON),
        (DartSettings(), Language.DART),
        (TypeScriptSettings(), Language.TYPESCRIPT),
    ]:
        assert settings.language is expected
        with pytest.raises(FrozenInstanceError):
            settings.language = Language.PYTHON


@pytest.mark.parametrize("invalid", [None, True, 1, [], {}, "future"])
def test_typed_runtime_state_rejects_invalid_vocabulary(invalid):
    raw = _response()
    raw["protocol_version"] = "3.0.0"
    raw["facts"]["runtime"]["requirement_state"] = invalid
    with pytest.raises(ProtocolError, match="requirement_state"):
        decode_response(json.dumps(raw).encode())


def test_programmatic_legacy_response_still_has_the_identical_v1_wire():
    from archkeel.ir.protocol import CollectionResponse, ProtocolVersion

    legacy = decode_response(json.dumps(_response()).encode())
    assert legacy.protocol_version is ProtocolVersion.V1
    assert encode_response(CollectionResponse(legacy.facts, "1.0.0")) == encode_response(legacy)
    assert replace(legacy.facts.runtime, requirement_state="declared") == legacy.facts.runtime
