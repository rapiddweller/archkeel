# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare native facts with the recorded oracle before Core tests use its Python provenance."""

from dataclasses import replace

from recorded_typescript import collect as recorded_collect
from test_collector_native_imports import _view

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli.observe import TYPESCRIPT_COLLECTOR, executable
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionRequest, ProtocolVersion


def collect(request: CollectionRequest) -> SourceFacts:
    wire = (
        replace(request, protocol_version=ProtocolVersion.V9)
        if request.scope.exclude_test_sources
        else request
    )
    native = ProcessCollector((str(executable(TYPESCRIPT_COLLECTOR)),)).collect(wire)
    assert isinstance(native, SourceFacts), native
    oracle = recorded_collect(request)
    assert _view(native) == _view(oracle)
    return oracle
