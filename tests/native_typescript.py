# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare public recorded facts, then exercise Core through the shell's verified native path."""

from dataclasses import replace

from collector_pin import assembled as assembled
from recorded_typescript import collect as recorded_collect
from test_collector_native_imports import _view

from archkeel.check.observe import Observer
from archkeel.cli.observe import observer_for
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionRequest, ProtocolVersion
from archkeel.ir.state_facts import ProducerKind


def collect(request: CollectionRequest) -> SourceFacts:
    wire = replace(
        request,
        protocol_version=ProtocolVersion.V9
        if request.scope.exclude_test_sources
        else ProtocolVersion.V8,
    )
    collector = replace(
        observer_for("typescript").collector, protocol_version=wire.protocol_version
    )
    native = collector.collect(wire)
    assert isinstance(native, SourceFacts), native
    oracle = recorded_collect(request)
    assert _view(native) == _view(oracle)
    assert native.verified_binary is not None
    return native


def trusted(collector, **options):
    return Observer(collector, producer=ProducerKind.BUNDLED, **options)


def observer_by_language(collector, **options):
    kind = ProducerKind.BUNDLED if collector.language == "typescript" else ProducerKind.PYTHON
    return Observer(collector, producer=kind, **options)
