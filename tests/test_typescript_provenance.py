# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The in-package TypeScript collector is a Python process whose identity includes its parsers."""

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.analyzer import runtime
from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts_codec import decode_response, encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    DartSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)


def _request(root: Path) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "app"),
        TypeScriptSettings(),
    )


def test_typescript_provenance_names_the_profile_and_python_runtime() -> None:
    analyzer, info = collector_provenance("typescript")
    assert analyzer.name == "archkeel-typescript-imports"
    assert (info.name, info.required) == ("python", ">=3.11")


def test_parser_versions_are_part_of_the_analyzer_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    before = collector_provenance("typescript")[0].code_digest
    real = importlib.metadata.version
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "version",
        lambda name: "9.9.9" if name == "tree-sitter-typescript" else real(name),
    )
    assert collector_provenance("typescript")[0].code_digest != before
    # Other collectors do not depend on the parser.
    assert collector_provenance("dart")[0] == collector_provenance("dart")[0]


def test_entry_round_trips_one_strict_response(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.ts").write_text("import './b';\n")
    (tmp_path / "src/b.ts").write_text("export const b = 1;\n")
    (tmp_path / "tsconfig.json").write_text('{"include": ["src"]}')
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "archkeel.analyzer.typescript.entry"],
        input=encode_request(_request(tmp_path)),
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    facts = decode_response(done.stdout).facts
    assert facts.profile == "archkeel-typescript-imports"
    assert facts.coverage.full_scope
    assert [file.rel_path for file in facts.files] == ["src/a.ts", "src/b.ts"]


def test_entry_refuses_another_language_request(tmp_path: Path) -> None:
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("src",), "app"),
        DartSettings(),
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "archkeel.analyzer.typescript.entry"],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert done.returncode != 0
    assert done.stdout == b""
