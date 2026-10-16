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
    [
        "declared",
        "metadata_missing",
        "metadata_invalid",
        "requirement_missing",
        "requirement_invalid",
    ],
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


def test_response_decoder_returns_nominal_profile_and_section_names():
    from archkeel.ir.facts import SourceProfile, SourceSectionName

    raw = _response()
    response = decode_response(json.dumps(raw).encode())
    assert response.facts.profile is SourceProfile.PYTHON
    assert all(
        section.name is SourceSectionName(entry["name"])
        for section, entry in zip(response.facts.sections, raw["facts"]["sections"], strict=True)
    )
    assert all(isinstance(name, SourceSectionName) for name in response.facts.capabilities.sections)


@pytest.mark.parametrize("field", ["profile", "section"])
@pytest.mark.parametrize("value", ["not-registered", None, True, 1, [], {}])
def test_nominal_profile_and_section_decoders_keep_the_exact_wire_vocabulary(field, value):
    raw = _response()
    if field == "profile":
        raw["facts"]["profile"] = value
    else:
        raw["facts"]["sections"][0]["name"] = value
    with pytest.raises(ProtocolError, match="profile|section"):
        decode_response(json.dumps(raw).encode())


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("section", ["imports", "unknowns"])
def test_registered_profiles_keep_imports_and_unknowns_mandatory(language, section):
    from archkeel.ir.codec_observation import _validate_profile_sections
    from archkeel.ir.facts import Language
    from archkeel.ir.model import CLASSIFIED_SECTIONS
    from archkeel.ir.profiles import PROFILES

    profile = PROFILES[Language(language)]
    model = {name: None if name in profile.absent_sections else [] for name in CLASSIFIED_SECTIONS}
    _validate_profile_sections(model, profile)
    model[section] = None
    with pytest.raises(ValueError, match=section):
        _validate_profile_sections(model, profile)


def test_collection_error_kind_has_one_nominal_owner_and_keeps_its_wire_text():
    from dataclasses import asdict
    from typing import get_type_hints

    from archkeel.ir.protocol import CollectionError, CollectionErrorKind

    assert get_type_hints(CollectionError)["kind"] is CollectionErrorKind
    error = CollectionError(CollectionErrorKind.TIMEOUT, "collector", "timed out")
    assert error.kind is CollectionErrorKind.TIMEOUT
    assert json.dumps(asdict(error), sort_keys=True, separators=(",", ":")) == (
        '{"kind":"timeout","message":"timed out","subject":"collector"}'
    )


@pytest.mark.parametrize("value", ["PASS", "FAIL"])
def test_coverage_verdict_decoder_returns_the_binary_domain_enum(value):
    from archkeel.ir.codec_observation import _parse_verdict
    from archkeel.ir.model import Verdict

    assert _parse_verdict(value, "coverage status/rules") is Verdict(value)


@pytest.mark.parametrize("value", ["UNKNOWN", "pass", "", None, True, 1, [], {}])
def test_binary_coverage_verdict_rejects_unknown_and_malformed_tags(value):
    from archkeel.ir.codec_observation import _parse_verdict

    with pytest.raises(ValueError, match="coverage status/rules invalid"):
        _parse_verdict(value, "coverage status/rules")
