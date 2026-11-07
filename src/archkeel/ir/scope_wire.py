# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the scope fields that a collection request carries in each protocol version."""

from .protocol import ProtocolVersion, SourceScope, since

EXCLUDE_TEST_SOURCES: str = "exclude_test_sources"


def scope_fields(version: ProtocolVersion) -> set[str]:
    """Return the exact scope keys of a request; protocol 9.0.0 adds the test-source flag."""
    fields = {"roots", "namespace"}
    if version in since(ProtocolVersion.V9):
        fields.add(EXCLUDE_TEST_SOURCES)
    return fields


def scope_payload(scope: SourceScope, version: ProtocolVersion) -> dict[str, object]:
    """Return the scope keys of a request. An earlier protocol cannot carry the flag."""
    payload: dict[str, object] = {"roots": list(scope.roots), "namespace": scope.namespace}
    if version in since(ProtocolVersion.V9):
        payload[EXCLUDE_TEST_SOURCES] = scope.exclude_test_sources
    return payload
