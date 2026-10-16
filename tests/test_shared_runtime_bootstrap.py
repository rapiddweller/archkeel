# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The actual language entries share one typed direct-start decision."""

import importlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    DartSettings,
    PythonSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)
from archkeel.check.ports import ScanConfig
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
LANGUAGES = ("python", "dart", "typescript")
BOOTSTRAP = "archkeel.analyzer.bootstrap"
DOC = "docs/architecture/shared-runtime-bootstrap.md"


def _owner():
    assert importlib.util.find_spec(BOOTSTRAP) is not None, "shared bootstrap owner is absent"
    return importlib.import_module(BOOTSTRAP)


@pytest.mark.parametrize("name", ["", "module", "archkeel.__main__", "__MAIN__", "δοκιμή"])
def test_shared_bootstrap_keeps_arbitrary_import_names_passive(name):
    assert _owner().is_direct_entrypoint(name) is False


def test_shared_bootstrap_recognizes_only_the_direct_protocol_marker():
    assert _owner().is_direct_entrypoint("__main__") is True


class _UntouchedStream:
    @property
    def buffer(self):
        raise AssertionError("an imported collector accessed a standard stream")


@pytest.mark.parametrize("language", LANGUAGES)
def test_real_language_imports_do_not_read_or_write_standard_streams(monkeypatch, language):
    name = f"archkeel.analyzer.{language}.entry"
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "stdin", _UntouchedStream())
    monkeypatch.setattr(sys, "stdout", _UntouchedStream())
    module = importlib.import_module(name)
    assert callable(module.main)


def _request(tmp_path, language):
    project = tmp_path / "source"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (project / "tsconfig.json").write_text('{"include": ["src/**/*.ts"]}\n')
    (project / "src").mkdir()
    suffix = {"python": "py", "dart": "dart", "typescript": "ts"}[language]
    body = {
        "python": "VALUE = 1\n",
        "dart": "final value = 1;\n",
        "typescript": "export const value = 1;\n",
    }[language]
    (project / "src" / f"probe.{suffix}").write_text(body)
    settings = {
        "python": PythonSettings(),
        "dart": DartSettings(),
        "typescript": TypeScriptSettings(),
    }[language]
    return encode_request(
        CollectionRequest(
            SnapshotInput(str(project), "0" * 40, False),
            SourceScope(("src",), "sample"),
            settings,
        )
    )


def _main_bytes(monkeypatch, language, payload):
    module = importlib.import_module(f"archkeel.analyzer.{language}.entry")
    incoming = io.TextIOWrapper(io.BytesIO(payload))
    outgoing = io.TextIOWrapper(io.BytesIO())
    with monkeypatch.context() as context:
        context.setattr(sys, "stdin", incoming)
        context.setattr(sys, "stdout", outgoing)
        code = module.main()
        outgoing.flush()
        return code, outgoing.buffer.getvalue()


@pytest.mark.parametrize("language", LANGUAGES)
def test_actual_module_start_preserves_direct_main_wire_bytes(tmp_path, monkeypatch, language):
    payload = _request(tmp_path, language)
    expected_code, expected = _main_bytes(monkeypatch, language, payload)
    actual = subprocess.run(
        [sys.executable, "-m", f"archkeel.analyzer.{language}.entry"],
        input=payload,
        capture_output=True,
        check=False,
    )
    assert actual.returncode == expected_code == 0, actual.stderr
    assert actual.stderr == b""
    assert actual.stdout == expected


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("payload", [b"not-json", b"{}"])
def test_actual_module_start_keeps_request_error_exit(tmp_path, monkeypatch, language, payload):
    with pytest.raises(ValueError):
        _main_bytes(monkeypatch, language, payload)
    actual = subprocess.run(
        [sys.executable, "-m", f"archkeel.analyzer.{language}.entry"],
        input=payload,
        capture_output=True,
        check=False,
    )
    assert actual.returncode == 1 and actual.stdout == b""
    assert b"Traceback" in actual.stderr


@pytest.mark.parametrize("language", LANGUAGES)
def test_actual_module_start_keeps_wrong_resolver_error(tmp_path, monkeypatch, language):
    other = "dart" if language == "python" else "python"
    payload = _request(tmp_path, other)
    with pytest.raises(ValueError, match="requires the"):
        _main_bytes(monkeypatch, language, payload)
    actual = subprocess.run(
        [sys.executable, "-m", f"archkeel.analyzer.{language}.entry"],
        input=payload,
        capture_output=True,
        check=False,
    )
    assert actual.returncode == 1 and actual.stdout == b""
    assert b"requires the" in actual.stderr


def _repository(tmp_path, *, module=BOOTSTRAP, probe="", weaken=False, marker=False):
    authored = json.loads((ROOT / "docs/architecture/contracts/analyzer.json").read_text())
    rules = json.loads((ROOT / "architecture-contract.json").read_text())["rules"]
    contract = {
        "schema_version": "2.2.0",
        "components": [{
            "id": "TARGET-PROCESS", "label": "process", "role": "component",
            "packages": ["archkeel"], "responsibilities": ["Own shared collector startup."],
            "forbidden_responsibilities": [], "provenance": [DOC],
        }],
        "rules": [
            rule for rule in rules
            if rule["id"].startswith("BOOTSTRAP-TYPED-") and rule["source"] == module
        ],
        "declarations": {"uml": {
            "schema_version": "1.0.0",
            "entities": [
                item for item in authored["declarations"]["uml"]["entities"]
                if item["id"].startswith("BOOTSTRAP-")
            ],
            "relationships": [], "scopes": [],
        }},
    }
    files = {
        "archkeel/__init__.py": "", "archkeel/analyzer/__init__.py": "",
        "contract.json": json.dumps(contract), DOC: "Owned direct collector start.\n",
    }
    for name in (BOOTSTRAP, *(f"archkeel.analyzer.{item}.entry" for item in LANGUAGES)):
        path = "src/" + name.replace(".", "/") + ".py"
        source_path = ROOT / path
        source = source_path.read_text() if source_path.exists() else ""
        if name == BOOTSTRAP and weaken:
            source = source.replace("-> bool:", "-> str:", 1)
        if name == BOOTSTRAP and marker:
            source = source.replace("class _EntryMode(Enum):", "class _EntryMode:", 1)
        if name == module:
            source += "\n" + probe
        files[path.removeprefix("src/")] = source
        files[path.removeprefix("src/").rsplit("/", 1)[0] + "/__init__.py"] = ""
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


@pytest.mark.parametrize("module", (BOOTSTRAP, *(f"archkeel.analyzer.{item}.entry" for item in LANGUAGES)))
def test_actual_bootstrap_and_entries_fulfil_owned_target_and_guard(tmp_path, module):
    root, config = _repository(tmp_path, module=module)
    model = _model(root, config)
    assessments = rule_assessments(model, undecided_by_rule={})
    assert assessments and all(row.status == "PASS" and row.evaluation_proven for row in assessments)
    assert not trace_valid_violations(model)


@pytest.mark.parametrize("weaken,marker", [(True, False), (False, True)])
def test_actual_bootstrap_api_weakening_fails_unchanged_authored_target(tmp_path, weaken, marker):
    root, config = _repository(tmp_path, weaken=weaken, marker=marker)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(row.kind == "uml_conformance" for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize("probe", [
    'def _probe(value):\n    return value == "__main__"\n',
    'def _probe(value):\n    return value in ("__main__", "module")\n',
    'def _probe(value):\n    match value:\n        case "__main__":\n            return True\n',
    'from typing import Final\nMAIN: Final[str] = "__main__"\n'
    'def _probe(value):\n    return value == MAIN\n',
    'def _probe(value):\n    return value == _EntryMode.MAIN.value\n',
])
def test_actual_bootstrap_rejects_raw_protocol_dispatch_mutations(tmp_path, probe):
    root, config = _repository(tmp_path, probe=probe)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(
        any(identifier.startswith("BOOTSTRAP-TYPED-") for identifier in row.rule_ids)
        for row in trace_valid_violations(model)
    )
    assert (root / "contract.json").read_bytes() == before
