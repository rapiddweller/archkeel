# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared real-process helper for Dart collector tests."""

from __future__ import annotations

import sys

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionError, CollectionRequest


def collect_native_dart(request: CollectionRequest) -> SourceFacts | CollectionError:
    return ProcessCollector(
        (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.dart.entry")
    ).collect(request)


def require_native_dart(result: SourceFacts | CollectionError) -> SourceFacts:
    if isinstance(result, CollectionError):
        pytest.fail(f"native Dart collection failed ({result.kind}): {result.message}")
    return result
