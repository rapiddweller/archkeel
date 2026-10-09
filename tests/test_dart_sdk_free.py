# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dart source collection does not invoke a Dart executable."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from archkeel.ir.facts_codec import decode_response, encode_request
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope


def test_entry_collects_with_empty_path_and_invalid_dart_executable(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: commerce\n", encoding="utf-8")
    source = tmp_path / "lib/main.dart"
    source.parent.mkdir()
    source.write_text("class Main {}\n", encoding="utf-8")
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "commerce"),
        DartSettings(),
    )
    env = dict(os.environ, PATH="", DART_EXECUTABLE="/definitely/not/dart")

    result = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "archkeel.analyzer.dart.entry"],
        input=encode_request(request),
        capture_output=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    facts = decode_response(result.stdout).facts
    assert facts.profile == "archkeel-dart-analyzer"
    assert facts.runtime.name == "python"
    assert {item.rel_path for item in facts.files} == {"lib/main.dart"}
