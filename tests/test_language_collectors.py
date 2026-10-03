# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from archkeel.analyzer.dart.collect import collect as collect_dart
from archkeel.analyzer.python.collect import collect as collect_python
from archkeel.ir.facts import ExternalPackageTarget, LocalTarget
from archkeel.ir.facts_codec import (
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    DartSettings,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _request(root: Path, language: str) -> CollectionRequest:
    resolver = PythonSettings() if language == "python" else DartSettings()
    return CollectionRequest(
        SnapshotInput(str(root), "HEAD", False),
        SourceScope(("src",), "sample"),
        resolver,
    )


def test_python_collects_all_source_sections_and_round_trips_strictly(tmp_path: Path) -> None:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (package / "__init__.py").write_text("from .models import Item\n")
    (package / "models.py").write_text(
        "from dataclasses import dataclass\n\n"
        "@dataclass\nclass Item:\n    value: str\n"
        "\ndef use(item: Item) -> str:\n    return item.value\n"
    )

    facts = collect_python(_request(tmp_path, "python"))

    assert facts.profile == "archkeel-python-analyzer"
    assert {section.name for section in facts.sections} == set(facts.capabilities.sections)
    assert {section.name for section in facts.sections} == {
        "symbols",
        "imports",
        "calls",
        "references",
        "bindings",
        "typing_signals",
        "constructs",
        "unknowns",
    }
    assert {file.rel_path for file in facts.files} == {
        "src/sample/__init__.py",
        "src/sample/models.py",
    }
    assert facts.state.classes
    assert facts.inputs and facts.source.source_digest
    assert any(isinstance(target, LocalTarget) for target in facts.imports)
    assert decode_response(encode_response(CollectionResponse(facts))).facts == facts


def test_python_keeps_syntax_failure_as_unknown_coverage_gap(tmp_path: Path) -> None:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "broken.py").write_text("def broken(:\n")

    facts = collect_python(_request(tmp_path, "python"))

    assert facts.coverage.selected_files == ("src/sample/__init__.py", "src/sample/broken.py")
    assert facts.coverage.files_read == 2
    assert facts.coverage.files_parsed == 1
    assert facts.coverage.gaps
    assert facts.coverage.gaps[0].evidence_class.value == "UNKNOWN"


def test_python_source_digest_tracks_raw_selected_and_resolution_inputs(tmp_path: Path) -> None:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("value = 1\n")
    request = _request(tmp_path, "python")

    first = collect_python(request)
    (package / "__init__.py").write_text("value = 2\n")
    second = collect_python(request)

    assert first.source.source_digest != second.source.source_digest
    selected = next(item for item in second.inputs if item.role == "selected")
    assert selected.digest == hashlib.sha256((package / "__init__.py").read_bytes()).hexdigest()


def test_dart_collects_part_libraries_and_typed_import_targets(tmp_path: Path) -> None:
    package = tmp_path / "src"
    package.mkdir()
    (tmp_path / "pubspec.yaml").write_text("name: sample\n")
    (package / "main.dart").write_text(
        "import 'local.dart';\nimport 'package:thirdparty/widgets.dart';\npart 'detail.dart';\n"
    )
    (package / "local.dart").write_text("class Local {}\n")
    (package / "detail.dart").write_text("part of 'main.dart';\n")

    facts = collect_dart(_request(tmp_path, "dart"))

    assert facts.profile == "archkeel-dart-directives"
    assert {file.rel_path for file in facts.files} == {"src/main.dart", "src/local.dart"}
    assert {item.path for item in facts.inputs if item.role == "selected"} == {
        "src/main.dart",
        "src/local.dart",
        "src/detail.dart",
    }
    assert any(isinstance(target, LocalTarget) for target in facts.imports)
    assert any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert facts.coverage.files_read == 3
    assert facts.coverage.files_parsed == 3


def test_dart_unresolved_directive_is_a_coverage_unknown(tmp_path: Path) -> None:
    package = tmp_path / "src"
    package.mkdir()
    (tmp_path / "pubspec.yaml").write_text("name: sample\n")
    (package / "main.dart").write_text("import 'missing.dart';\n")

    facts = collect_dart(_request(tmp_path, "dart"))

    assert facts.coverage.gaps
    assert facts.coverage.gaps[0].evidence_class.value == "UNKNOWN"


def test_request_codec_round_trip_uses_the_strict_wire_schema(tmp_path: Path) -> None:
    request = _request(tmp_path, "python")
    payload = encode_request(request)
    assert json.loads(payload)["resolver"] == {"language": "python"}

    assert decode_request(payload) == request


def test_python_entry_reads_and_writes_only_strict_codec_messages(tmp_path: Path) -> None:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("value = 1\n")
    completed = subprocess.run(
        [sys.executable, "-m", "archkeel.analyzer.python.entry"],
        input=encode_request(_request(tmp_path, "python")),
        capture_output=True,
        check=True,
    )

    response = decode_response(completed.stdout)
    assert response.facts.coverage.selected_files == ("src/sample/__init__.py",)
    assert completed.stderr == b""
