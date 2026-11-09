# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-316: the native TypeScript collector is a drop-in behind `[scan].collector_argv`.

Consumer: the host process port (`analyzer/process.py`) and `evaluate_source`. The Python
TypeScript collector is the difference oracle for the files that the native skeleton reports.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zlib
from dataclasses import replace
from pathlib import Path

import pytest

from archkeel.analyzer import process as process_owner
from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.typescript.collect import collect
from archkeel.analyzer.typescript.explore_scope import NO_PRODUCTION_SOURCE
from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
FIXTURES = (
    "fixtures/H-typescript",
    "fixtures/H-uml-typescript",
    "fixtures/F-typescript-story",
    "fixtures/L-nest-realworld",
)


@pytest.fixture
def binary(native_binary: Path) -> Path:
    return native_binary


def _request(root: Path, version: ProtocolVersion = ProtocolVersion.V3) -> CollectionRequest:
    config = load_config(root)
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(config.roots, config.namespace),
        TypeScriptSettings(config.tsconfig or "tsconfig.json"),
        version,
    )


def _facts(result: SourceFacts | CollectionError) -> SourceFacts:
    assert not isinstance(result, CollectionError), result
    return result


def test_host_report_reads_the_native_reply(tmp_path: Path, binary: Path) -> None:
    root = repository(tmp_path, VARIANTS[0])
    settings = root / "archkeel.toml"
    argv = json.dumps([str(binary)])
    settings.write_text(settings.read_text() + f"collector_argv = {argv}\n")
    config = load_config(root)
    assert config.collector_argv == (str(binary),)
    observer = observer_for(
        config.language,
        collector_argv=config.collector_argv,
        tsconfig=config.tsconfig or "tsconfig.json",
    )

    result, artifact = run_report(root, config=config, analyzer=observer)

    # The legacy capability carries no symbols, so the rules of the fixture stay UNKNOWN.
    assert result.declared_rules == "UNKNOWN"
    assert artifact is not None
    errors = {kind.value for kind in CollectionErrorKind}
    assert not [item for item in result.diagnostics if item.kind in errors], result.diagnostics


@pytest.mark.parametrize("version", [ProtocolVersion.V3, ProtocolVersion.V8])
def test_reply_decodes_with_consistent_coverage(binary: Path, version: ProtocolVersion) -> None:
    pinned = version if version is ProtocolVersion.V8 else None
    response = ProcessCollector((str(binary),), protocol_version=pinned).collect_response(
        _request(ROOT / "fixtures/H-typescript", version)
    )

    assert isinstance(response, CollectionResponse), response
    assert response.protocol_version is ProtocolVersion.V8
    facts = response.facts
    coverage = facts.coverage
    assert facts.adapter.name == "archkeel-typescript-imports"
    assert facts.runtime.name == "rust"
    # The inner-UML capability (AD-340): every section is declared and every section is produced.
    assert {item.value for item in facts.capabilities.sections} == {
        "imports",
        "unknowns",
        "symbols",
        "calls",
        "references",
        "bindings",
        "constructs",
    }
    assert "inner-uml-v1" in facts.capabilities.resolution_features
    assert "script-globals-v1" not in facts.capabilities.resolution_features
    assert [(c.name.value, c.status.value) for c in facts.capabilities.constructs] == [
        ("string_literal_compare", "partial")
    ]
    assert len(coverage.selected_files) == coverage.files_read == coverage.files_parsed == 7
    assert len(facts.files) == 7
    # No global is examined, so the scan is not complete: one gap for each file (AD-320).
    assert not coverage.full_scope
    assert {gap.title for gap in coverage.gaps} == {
        "Script-global dependencies are not examined by the native collector"
    }
    assert len(coverage.gaps) == len(facts.files)
    sections = {section.name.value: section.records for section in facts.sections}
    assert len(sections["imports"]) == len(facts.imports) == 8
    assert sections["unknowns"] == coverage.gaps


@pytest.mark.parametrize("fixture", FIXTURES)
def test_files_evidence_and_inputs_match_the_python_collector(binary: Path, fixture: str) -> None:
    request = _request(ROOT / fixture)
    native = _facts(ProcessCollector((str(binary),)).collect(request))
    python = collect(request)

    assert native.coverage.selected_files == python.coverage.selected_files
    assert native.files == python.files
    assert native.source.scope == python.source.scope
    evidence = {item.id: item for item in python.evidence}
    assert [evidence.get(item.id) for item in native.evidence] == list(native.evidence)
    # The native resolver reads the same files as the Python resolver, so the inputs are equal.
    assert native.inputs == python.inputs


def test_a_bundled_binary_with_another_adapter_version_is_a_protocol_error(
    binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(ROOT / "fixtures/H-typescript", ProtocolVersion.V8)
    pinned = ProcessCollector((str(binary),), protocol_version=ProtocolVersion.V8)
    version = _facts(pinned.collect(request)).adapter.version
    bundled = replace(pinned, pin_adapter_version=True)

    monkeypatch.setattr(process_owner, "package_version", lambda: version)
    assert _facts(bundled.collect(request)).adapter.version == version
    monkeypatch.setattr(process_owner, "package_version", lambda: f"{version}.1")
    result = bundled.collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "does not match the host version" in result.message


def test_a_missing_binary_is_a_missing_tool(tmp_path: Path) -> None:
    result = ProcessCollector((str(tmp_path / "missing-collector"),)).collect(
        _request(ROOT / "fixtures/H-typescript")
    )
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.MISSING_TOOL


def test_a_refused_request_is_an_execution_error_with_the_stderr_tail(binary: Path) -> None:
    request = replace(_request(ROOT / "fixtures/H-typescript"), resolver=PythonSettings())
    result = ProcessCollector((str(binary),)).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.EXECUTION_ERROR
    assert "Collector exited 1" in result.message
    assert "requires the TypeScript resolver" in result.message


def test_the_host_bounds_time_and_output(tmp_path: Path, binary: Path) -> None:
    request = _request(ROOT / "fixtures/H-typescript")
    late = ProcessCollector((str(binary),), timeout_seconds=1e-6).collect(request)
    assert isinstance(late, CollectionError)
    assert late.kind is CollectionErrorKind.TIMEOUT
    # The reply of 2000 files is larger than a pipe buffer, so the collector still writes when
    # the host stops reading. A collector that is exiting at that moment still fails cleanup on
    # macOS after #883 (killpg gives EPERM before the exit can be reaped).
    (tmp_path / "tsconfig.json").write_text("{}")
    for index in range(2000):
        source = tmp_path / "src" / f"part{index // 100}" / f"module{index}.ts"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"export const value{index} = {index};\n")
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    large = ProcessCollector((str(binary),), output_limit_bytes=1024).collect(request)
    assert isinstance(large, CollectionError)
    assert large.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "1024 byte limit" in large.message


TEST_SOURCES = {
    "tsconfig.json": "{}",
    "src/app.ts": "export const value = 1;\n",
    "src/app.test.ts": "import { value } from './app';\n",
    "src/tests/helper.ts": "export const helper = 2;\n",
    "src/latest.ts": "import { helper } from './tests/helper';\n",
}


def _tree(root: Path) -> Path:
    for name, text in TEST_SOURCES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def test_protocol_9_request_excludes_test_sources(tmp_path: Path, binary: Path) -> None:
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(_tree(tmp_path)), "git_head": "a" * 40, "dirty": False},
        "scope": {"roots": ["src"], "namespace": "shop", "exclude_test_sources": True},
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    }
    reply = subprocess.run(
        [str(binary)], input=json.dumps(request).encode(), capture_output=True, check=True
    ).stdout
    decoded = json.loads(zlib.decompress(reply))

    assert decoded["protocol_version"] == "9.0.0"
    assert decoded["facts"]["coverage"]["selected_files"] == ["src/app.ts", "src/latest.ts"]


@pytest.mark.parametrize(
    "drop",
    [(), ("src/app.ts", "src/latest.ts")],
    ids=["production-and-tests", "only-tests"],
)
def test_v9_host_excludes_test_sources_like_python(
    tmp_path: Path, binary: Path, drop: tuple[str, ...]
) -> None:
    root = _tree(tmp_path)
    for name in drop:
        (root / name).unlink()
    request = CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "shop", exclude_test_sources=True),
        TypeScriptSettings(),
        ProtocolVersion.V9,
    )
    pinned = ProtocolVersion.V8
    native = _facts(ProcessCollector((str(binary),), protocol_version=pinned).collect(request))
    python = collect(request)

    assert native.coverage.selected_files == python.coverage.selected_files
    assert native.files == python.files
    # An import into an excluded test source, or a scope of tests only, is never complete.
    assert not native.coverage.full_scope and not python.coverage.full_scope
    if drop:
        assert native.coverage.selected_files == ()
        expected = {NO_PRODUCTION_SOURCE}
        assert {gap.title for gap in native.coverage.gaps} == expected
        assert expected <= {gap.title for gap in python.coverage.gaps}


def test_the_collector_refuses_a_protocol_version_it_does_not_know(binary: Path) -> None:
    """An old host with this collector, or a new host with an old one, fails closed (AD-340).

    The request names the protocol version, and the reply carries it. A collector that does not
    know the version exits with an error and writes no reply, so the host reads no facts.
    """
    request = json.loads(
        encode_request(_request(ROOT / "fixtures/H-typescript", ProtocolVersion.V8))
    )
    for unknown in ("99.0.0", "7.0.0", "8", ""):
        payload = json.dumps({**request, "protocol_version": unknown}).encode()
        done = subprocess.run([str(binary)], input=payload, capture_output=True, check=False)
        assert done.returncode != 0, unknown
        assert done.stdout == b"", unknown
        assert b"protocol" in done.stderr, unknown


def test_the_host_refuses_a_reply_of_another_protocol_version(binary: Path) -> None:
    replay = Path(__file__).with_name("replay_collector.py")
    argv = (sys.executable, "-I", "-B", str(replay), str(binary), "version")
    request = _request(ROOT / "fixtures/H-typescript", ProtocolVersion.V8)
    result = ProcessCollector(argv, protocol_version=ProtocolVersion.V8).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
