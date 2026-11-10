# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The request versions of the host equal the one Rust list (`archkeel-facts` protocol)."""

import json
from pathlib import Path

from archkeel.ir.protocol import (
    NATIVE_REQUEST_PROTOCOLS,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
    collection_request,
)

SCHEMA = Path(__file__).parents[1] / "native/facts/schema/archkeel-request.schema.json"


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
