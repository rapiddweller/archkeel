# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The request versions of the host equal the one Rust list (`archkeel-facts` protocol).

The Python list is compared with the committed schema; a Rust test ties that schema to
`Version::ALL`. The schema must also refuse each request that the collector refuses.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from archkeel.analyzer.interpreter import NATIVE_PYTHON_PROTOCOL
from archkeel.ir.protocol import (
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
    collection_request,
)

SCHEMA = Path(__file__).parents[1] / "native/facts/schema/archkeel-request.schema.json"
# The request versions that a native collector reads: the same list as `Version::ALL` in
# `native/facts/src/protocol.rs`. Only this test reads the list, so it lives here (#1009).
NATIVE_REQUEST_PROTOCOLS = (
    ProtocolVersion.V3,
    ProtocolVersion.V8,
    ProtocolVersion.V9,
    NATIVE_PYTHON_PROTOCOL,
)


def test_the_python_list_equals_the_versions_of_the_generated_request_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    rust = schema["$defs"]["Version"]["enum"]
    assert [str(version) for version in NATIVE_REQUEST_PROTOCOLS] == rust


def test_the_builder_sends_a_version_of_the_list() -> None:
    snapshot = SnapshotInput("/repository", "a" * 40, False)
    plain = collection_request(snapshot, SourceScope(("src",), "shop"), TypeScriptSettings())
    scoped = collection_request(snapshot, SourceScope(("src",), "shop", True), TypeScriptSettings())
    assert {plain.protocol_version, scoped.protocol_version} <= set(NATIVE_REQUEST_PROTOCOLS)
    assert plain.protocol_version != scoped.protocol_version
    # 10.0.0 is only the request of the native Python collector (AD-334).
    assert NATIVE_PYTHON_PROTOCOL not in {plain.protocol_version, scoped.protocol_version}


def _request(version: str = "8.0.0") -> dict[str, Any]:
    scope: dict[str, Any] = {"roots": ["src"], "namespace": "shop"}
    if version in {"9.0.0", "10.0.0"}:
        scope["exclude_test_sources"] = False
    return {
        "protocol_version": version,
        "snapshot": {"root": "/repository", "git_head": "a" * 40, "dirty": False},
        "scope": scope,
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    }


def _refused() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for mutate in [
        lambda r: r["scope"].update(exclude_test_sources=False),  # on 8.0.0
        lambda r: r["scope"].update(exclude_test_sources=None),
        lambda r: r["resolver"].update(bundler=False),
        lambda r: r["resolver"].update(bundler=None),
        lambda r: r.update(extra=1),
        lambda r: r["snapshot"].update(dirty="yes"),
        lambda r: r.update(protocol_version="7.0.0"),
        lambda r: r["resolver"].update(language="python"),
    ]:
        case = _request()
        mutate(case)
        cases.append(case)
    nine = _request("9.0.0")
    del nine["scope"]["exclude_test_sources"]
    # 10.0.0 carries only the Python resolver, and the Python resolver only 10.0.0 (AD-334).
    ten = _request("10.0.0")
    ten["scope"]["exclude_test_sources"] = False
    return [*cases, nine, ten]


@pytest.mark.parametrize("request_value", _refused())
def test_the_schema_refuses_what_the_collector_refuses(request_value: dict[str, Any]) -> None:
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert not validator.is_valid(request_value)


@pytest.mark.parametrize("version", ["3.0.0", "8.0.0", "9.0.0"])
def test_the_schema_accepts_what_the_collector_accepts(version: str) -> None:
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    value = _request(version)
    assert validator.is_valid(value)
    value["resolver"]["bundler"] = True
    assert validator.is_valid(value)
