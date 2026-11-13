# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A runtime-name claim gives no native-language receipt trust, live or from saved JSON."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from collector_pin import pin_of
from test_collector_native_receipts import _proof
from test_collector_native_receipts import native_receipt as native_receipt
from test_scoped_dependency_proof import _project, _rows

from archkeel.check.report import run_report_with_observation
from archkeel.cli import observe as shell
from archkeel.ir.codec import observation_payload, parse_observation
from archkeel.ir.dependency_binding import dependency_runtime_rejection
from archkeel.ir.state_facts import ProducerKind

KINDS = (ProducerKind.PINNED, ProducerKind.EXTERNAL, ProducerKind.PYTHON)
ANALYZERS = {
    "python": "archkeel-python-analyzer",
    "typescript": "archkeel-typescript-imports",
    "dart": "archkeel-dart-analyzer",
    "rust": "archkeel-rust-imports",
}


def _claim(model, kind, language="typescript"):
    model = replace(
        model,
        verified_binary=None,
        producer_kind=kind,
        analyzer=replace(model.analyzer, name=ANALYZERS[language]),
        runtime=replace(model.runtime, name="python", version="3.11.12", required=">=3.11"),
    )
    return _proof(model, name="python", version="3.11.12", required=">=3.11", code_digest=None)


@pytest.mark.parametrize("kind", KINDS)
def test_a_typescript_name_claim_never_proves_a_scope(native_receipt, kind):
    model = _claim(native_receipt[0], kind)
    for candidate in (model, parse_observation(observation_payload(model))):
        row = _rows(candidate)["a:requires"]
        assert row.status == "UNKNOWN", row.reason
        assert "dependency_scope_runtime_unverified" in row.reason


@pytest.mark.parametrize("language", ANALYZERS)
@pytest.mark.parametrize("kind", KINDS)
def test_only_the_python_analyzer_keeps_the_python_lower_bound(native_receipt, language, kind):
    model = _claim(native_receipt[0], kind, language)
    proof = next(
        record.data.get("dependency_scope_proof")
        for record in model.records("scope_observations")
        if record.data.get("dependency_scope_proof")
    )
    assert dependency_runtime_rejection(model, proof) == (
        None if language == "python" else "dependency_scope_runtime_unverified"
    )
    assert _rows(model)["a:requires"].status == ("PASS" if language == "python" else "UNKNOWN")


@pytest.mark.parametrize("version", ["3.10.9", "0.0.0", "٣.١١.١٢"])
def test_the_python_lower_bound_still_rejects_invalid_matching_versions(native_receipt, version):
    model = _claim(native_receipt[0], ProducerKind.PYTHON, "python")
    assert _rows(model)["a:requires"].status == "PASS"
    changed = replace(model, runtime=replace(model.runtime, version=version))
    assert _rows(_proof(changed, version=version))["a:requires"].status == "UNKNOWN"


def _configured(root, native_binary):
    config = _project(root)
    wrapper = root.parent / "claimed_runtime.py"
    wrapper.write_text(
        "import json, subprocess, sys, zlib\n"
        "reply = subprocess.run([sys.argv[1]], input=sys.stdin.buffer.read(), "
        "capture_output=True, check=True).stdout\n"
        "value = json.loads(zlib.decompress(reply) if reply[:1] == b'x' else reply)\n"
        "value['facts']['runtime'] = dict(name='python', version='3.11.12', "
        "required='>=3.11', requirement_state='declared')\n"
        "sys.stdout.buffer.write(zlib.compress(json.dumps(value).encode()))\n"
    )
    argv = (sys.executable, "-I", "-B", str(wrapper), str(native_binary))
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["src"]\nnamespace = "demo"\nlanguage = "typescript"\n'
        'contract = "architecture-contract.json"\ncollector_argv = ' + json.dumps(argv) + "\n"
    )
    return config, argv


@pytest.mark.parametrize("kind", KINDS)
def test_configured_name_claims_are_unknown_in_process(tmp_path, native_binary, kind):
    root = tmp_path / "project"
    config, argv = _configured(root, native_binary)
    observer = shell.observer_for(
        "typescript",
        collector_argv=argv,
        pinned_digest=pin_of(argv[0]) if kind is ProducerKind.PINNED else None,
    )
    observer = replace(observer, producer=kind)
    result, artifact, model = run_report_with_observation(root, config=config, analyzer=observer)
    assert artifact is not None and model is not None, result.diagnostics
    for candidate in (model, parse_observation(observation_payload(model))):
        row = _rows(candidate)["a:requires"]
        assert row.status == "UNKNOWN", row.reason
        assert "dependency_scope_runtime_unverified" in row.reason


def _cli(arguments, root, environment):
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", *arguments, "--json"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    rows = {row["id"]: row for row in payload["rule_assessments"] or ()}
    assert result.returncode == 2, payload
    assert "a:requires" in rows, payload
    assert rows["a:requires"]["status"] == "UNKNOWN", rows["a:requires"]
    assert "dependency_scope_runtime_unverified" in rows["a:requires"]["reason"]


@pytest.mark.parametrize("binary_present", [False, True])
@pytest.mark.parametrize("kind", KINDS)
def test_real_cli_configured_and_saved_claims_get_no_trust(
    tmp_path, native_binary, kind, binary_present
):
    root = tmp_path / "project"
    _configured(root, native_binary)
    install = tmp_path / "install"
    source = Path(shell.__file__).resolve().parents[1]
    shutil.copytree(
        source, install / "archkeel", ignore=shutil.ignore_patterns("__pycache__", "_native")
    )
    if binary_present:
        from test_collector_bundled_launcher import _install

        _install(install / "archkeel/_native", native_binary)
    environment = {**os.environ, "PYTHONPATH": str(install)}
    artifact = tmp_path / "out/architecture.json"
    _cli(["--root", str(root), "--output", str(artifact)], root, environment)
    saved = json.loads(artifact.read_bytes())
    saved["producer_kind"] = kind.value
    artifact.write_text(json.dumps(saved))
    _cli(["--input", str(artifact)], root, environment)
