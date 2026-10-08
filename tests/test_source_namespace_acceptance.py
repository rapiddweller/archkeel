# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Core rejects replaceable collectors that move selected files outside namespace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from dart_native_helpers import collect_native_dart, require_native_dart

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import collect as collect_python
from archkeel.check.observe import Observer
from archkeel.ir.codec import decode_canonical_model
from archkeel.ir.facts_codec import encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    DartSettings,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

_FIXTURES = Path(__file__).parent / "fixtures/collection-protocol"
_GIT_HEAD = "a" * 40
_SOURCE_SUFFIX = {"python": "py", "dart": "dart", "typescript": "ts"}


def _response(language: str, root: Path) -> dict[str, object]:
    if language == "typescript":
        response = json.loads((_FIXTURES / f"response-{language}.json").read_bytes())
        response["facts"]["source"]["git_head"] = _GIT_HEAD
        response["facts"]["source"]["dirty"] = False
        return response

    settings = PythonSettings() if language == "python" else DartSettings()
    request = CollectionRequest(
        SnapshotInput(str(root), _GIT_HEAD, False),
        SourceScope(("src",), "project"),
        settings,
    )
    if language == "python":
        facts = collect_python(request)
    else:
        facts = require_native_dart(collect_native_dart(request))
    return json.loads(encode_response(CollectionResponse(facts)))


def _run_report(
    tmp_path: Path,
    language: str,
    *,
    escaped_field: str | None = None,
    module_identity: str = "project.collector_defined_identity",
    package_identity: str = "project",
) -> tuple[object, bytes | None]:
    root = tmp_path / "repo"
    source_dir = root / "src" / "project" if language == "python" else root / "src"
    source = source_dir / f"app.{_SOURCE_SUFFIX[language]}"
    source.parent.mkdir(parents=True)
    source.write_text("void main() {}\n" if language == "dart" else "value = 1\n")
    if language == "python":
        (source_dir / "__init__.py").write_text("")
    if language == "dart":
        (root / "pubspec.yaml").write_text("name: project\n")

    response = _response(language, root)
    facts = response["facts"]
    file_fact = response["facts"]["files"][0]
    previous_module = file_fact["module"]
    previous_package = file_fact["package"]
    if escaped_field == "module":
        file_fact["module"] = "outside.app"
        _replace_fact_value(facts, previous_module, "outside.app")
    elif escaped_field == "package":
        file_fact["package"] = "outside"
        _replace_fact_value(facts, previous_package, "outside")
    elif escaped_field is None and language != "dart":
        # A collector may define an identity unrelated to the selected file's spelling.
        file_fact["module"] = module_identity
        file_fact["package"] = package_identity
        _replace_fact_value(facts, previous_module, file_fact["module"])
        _replace_fact_value(facts, previous_package, file_fact["package"])

    encoded = json.dumps(response)
    collector = ProcessCollector((sys.executable, "-B", "-c", f"print({encoded!r})"))
    contract = root / "contract.json"
    contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}\n')
    observer = Observer(collector)
    result = observer(
        root,
        roots=("src",),
        namespace="project",
        contract="contract.json",
        git_head=_GIT_HEAD,
        dirty=False,
        contract_root=root,
        language=language,
    )
    if result.observation is None:
        return result, None
    from archkeel.ir.codec import canonical_report_bytes

    return result, canonical_report_bytes(result.observation)


def _replace_fact_value(value: object, previous: str, replacement: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if item == previous:
                value[key] = replacement
            else:
                _replace_fact_value(item, previous, replacement)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if item == previous:
                value[index] = replacement
            else:
                _replace_fact_value(item, previous, replacement)


@pytest.mark.parametrize("language", ["python", "typescript"])
@pytest.mark.parametrize(
    ("module_identity", "package_identity"),
    [
        ("project", "project"),
        ("project.collector_defined_identity", "project"),
        ("project.collector_defined_package.module", "project.collector_defined_package"),
    ],
)
def test_process_observer_accepts_in_namespace_collector_identity(
    tmp_path: Path, language: str, module_identity: str, package_identity: str
) -> None:
    result, report = _run_report(
        tmp_path,
        language,
        module_identity=module_identity,
        package_identity=package_identity,
    )

    assert result.observation is not None
    assert report is not None
    canonical = decode_canonical_model(json.loads(report))
    assert canonical["coverage"]["status"] == "PASS"


def test_process_observer_accepts_native_dart_collector_facts(tmp_path: Path) -> None:
    result, report = _run_report(tmp_path, "dart")

    assert result.observation is not None
    assert report is not None
    canonical = decode_canonical_model(json.loads(report))
    assert canonical["coverage"]["status"] == "PASS"


@pytest.mark.parametrize(
    ("language", "escaped_field"),
    [
        ("python", "module"),
        ("dart", "module"),
        ("typescript", "module"),
        ("python", "package"),
        ("dart", "package"),
        ("typescript", "package"),
    ],
)
def test_process_observer_rejects_selected_fact_outside_namespace(
    tmp_path: Path, language: str, escaped_field: str
) -> None:
    result, report = _run_report(tmp_path, language, escaped_field=escaped_field)

    assert result.observation is None
    assert result.diagnostics
    if language != "dart":
        assert any("namespace" in item.unknown_claim.lower() for item in result.diagnostics)
    assert report is None
