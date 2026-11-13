# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise retained TypeScript behavior with the verified native collector, without an oracle."""

from archkeel.cli.observe import observer_for
from archkeel.ir.facts import SourceFacts
from archkeel.ir.languages import Language
from archkeel.ir.protocol import CollectionRequest


def collect(request: CollectionRequest) -> SourceFacts:
    result = observer_for(Language.TYPESCRIPT).collector.collect(request)
    assert isinstance(result, SourceFacts), result
    assert result.verified_binary is not None
    return result
