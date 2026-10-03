# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical analyzer identity tracks source bytes, independently of version labels."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect as collect_python
from archkeel.check.observe import Observer
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import decode_response
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

_FIXTURES = Path(__file__).parent / "fixtures/collection-protocol"


@dataclass(frozen=True, slots=True)
class _FixedCollector:
    facts: SourceFacts

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        return self.facts


def _facts(language: str, root: Path) -> SourceFacts:
    if language == "python":
        package = root / "src" / "project"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "app.py").write_text("value = 1\n")
        (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
        request = CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope(("src",), "project"),
            PythonSettings(),
        )
        return collect_python(request)
    response = (_FIXTURES / f"response-{language}.json").read_bytes()
    return decode_response(response).facts


def _canonical(tmp_path: Path, facts: SourceFacts, language: str) -> dict[str, object]:
    root = tmp_path / "repo"
    for selected in facts.coverage.selected_files:
        source = root / selected
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("value = 1\n")
    if language == "python":
        (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "contract.json").write_text('{"schema_version":"2.1.0","components":[],"rules":[]}\n')

    observer = Observer(_FixedCollector(facts))
    result = observer(
        root,
        roots=("src",),
        namespace="project",
        contract="contract.json",
        git_head=facts.source.git_head,
        dirty=facts.source.dirty is True,
        contract_root=root,
        language=language,
    )
    assert result.observation is not None, result.diagnostics
    encoded = canonical_report_bytes(result.observation)
    return decode_canonical_model(json.loads(encoded))


def test_distribution_version_is_retained_but_not_part_of_code_identity(tmp_path: Path) -> None:
    facts = _facts("python", tmp_path / "fixture")
    first_facts = replace(facts, adapter=replace(facts.adapter, version="1.0.0+build.1"))
    second_facts = replace(facts, adapter=replace(facts.adapter, version="1.0.0+build.2"))

    first = _canonical(tmp_path / "first", first_facts, "python")
    second = _canonical(tmp_path / "second", second_facts, "python")

    assert first["analyzer"]["code_digest"] == second["analyzer"]["code_digest"]
    assert first["producer"]["version"] == "1.0.0+build.1"
    assert second["producer"]["version"] == "1.0.0+build.2"


def test_collector_source_digest_changes_canonical_code_identity(tmp_path: Path) -> None:
    facts = _facts("python", tmp_path / "fixture")
    changed = replace(facts, adapter=replace(facts.adapter, code_digest="c" * 64))

    original = _canonical(tmp_path / "original", facts, "python")
    updated = _canonical(tmp_path / "updated", changed, "python")

    assert original["analyzer"]["code_digest"] != updated["analyzer"]["code_digest"]
    assert updated["producer"]["code_digest"] == "c" * 64


def test_core_source_digest_changes_canonical_code_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from archkeel.check import observation

    facts = _facts("python", tmp_path / "fixture")
    with monkeypatch.context() as patcher:
        patcher.setattr(observation, "package_digest", lambda: "1" * 64)
        original = _canonical(tmp_path / "original", facts, "python")
    with monkeypatch.context() as patcher:
        patcher.setattr(observation, "package_digest", lambda: "2" * 64)
        updated = _canonical(tmp_path / "updated", facts, "python")

    assert original["analyzer"]["code_digest"] != updated["analyzer"]["code_digest"]


def test_typescript_runtime_and_producer_versions_survive_canonical_report(
    tmp_path: Path,
) -> None:
    report = _canonical(tmp_path, _facts("typescript", tmp_path / "fixture"), "typescript")

    assert report["runtime"] == {"name": "node", "version": "26.3.1"}
    assert report["producer"]["name"] == "@archkeel/typescript-adapter"
    assert report["producer"]["version"] == "0.1.0+typescript.5.9.3"


def test_python_runtime_version_survives_canonical_report(tmp_path: Path) -> None:
    facts = _facts("python", tmp_path / "fixture")

    report = _canonical(tmp_path, facts, "python")

    assert report["python_version"] == facts.runtime.version
