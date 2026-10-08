# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared real-process helper for Dart collector tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionError, CollectionRequest


def collect_native_dart(request: CollectionRequest) -> SourceFacts | CollectionError:
    executable = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if executable is None:
        return CollectionError("missing_tool", "dart", "Dart SDK is not installed")
    entry = Path(__file__).parents[1] / "src/archkeel/analyzer/dart/entry.py"
    return ProcessCollector((sys.executable, "-B", str(entry))).collect(request)


def require_native_dart(result: SourceFacts | CollectionError) -> SourceFacts:
    if isinstance(result, CollectionError):
        if result.kind == "missing_tool" and not (
            os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
        ):
            pytest.skip(result.message)
        pytest.fail(f"native Dart collection failed ({result.kind}): {result.message}")
    return result
