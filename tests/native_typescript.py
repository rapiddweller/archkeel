# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise retained TypeScript behavior with the verified native collector, without an oracle."""

from dataclasses import replace

from archkeel.cli.observe import observer_for
from archkeel.ir.facts import SourceFacts
from archkeel.ir.languages import Language
from archkeel.ir.protocol import CollectionRequest, ProtocolVersion


def collect(request: CollectionRequest) -> SourceFacts:
    collector = observer_for(Language.TYPESCRIPT).collector
    if request.scope.exclude_test_sources:
        collector = replace(collector, protocol_version=ProtocolVersion.V9)
        request = replace(request, protocol_version=ProtocolVersion.V9)
    result = collector.collect(request)
    assert isinstance(result, SourceFacts), result
    assert result.verified_binary is not None
    return result
