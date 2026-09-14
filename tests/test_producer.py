# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from test_delta import _model, _record

from codekeel.ir.model import Coverage, Diagnostic, Observation
from codekeel.producer import observe


def _prepare_source(tmp_path: Path) -> None:
    metadata = tmp_path / "pyproject.toml"
    if not metadata.exists():
        metadata.write_text('[project]\nrequires-python = ">=3.11"\n')


def _observe(source: Path):
    _prepare_source(source)
    return observe(
        source,
        roots=(".",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=source,
    )


@pytest.mark.parametrize("exit_code", [2, True])
def test_producer_failure_cannot_become_complete(tmp_path: Path, exit_code: object) -> None:
    response = subprocess.CompletedProcess(
        [], 0, json.dumps({"model": {}, "exit_code": exit_code}), ""
    )
    with patch("codekeel.producer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.diagnostics[0].kind == "parse_error"


def test_source_symlink_escape_is_rejected_before_producer(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 1\n")
    (source / "linked.py").symlink_to(outside)
    with patch("codekeel.producer.subprocess.run") as producer:
        result = _observe(source)
        producer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].subject == str(source / "linked.py")
    assert "Source path escapes" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize("cause", ["missing_tool", "timeout", "parse_error"])
def test_execution_failure_has_structured_diagnostic(tmp_path: Path, cause: str) -> None:
    if cause == "missing_tool":
        error: Exception = OSError("missing Python executable")
    elif cause == "timeout":
        error = subprocess.TimeoutExpired("producer", 60)
    else:
        error = ValueError("unused")
    if cause in {"missing_tool", "timeout"}:
        with patch("codekeel.producer.subprocess.run", side_effect=error):
            result = _observe(tmp_path)
    else:
        with patch(
            "codekeel.producer.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "not JSON", ""),
        ):
            result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.observation is None
    assert result.coverage is None
    assert result.diagnostics[0].kind == cause
    assert all(isinstance(item, Diagnostic) for item in result.diagnostics)


@pytest.mark.parametrize("cause", ["scope_empty", "rule_without_subjects"])
def test_partial_observation_and_coverage_survive_exit_two(tmp_path: Path, cause: str) -> None:
    raw = _model(git_head="a" * 40)
    coverage = raw["coverage"]
    coverage["status"] = "FAIL"
    if cause == "scope_empty":
        coverage.update(files_discovered=0, files_read=0, files_parsed=0)
    else:
        failure = _record("unknown-rule", kind="rule-without-subjects", evidence_class="UNKNOWN")
        failure["rule_ids"] = ["rule-zero"]
        raw["unknowns"] = [failure]
        coverage.update(rules="FAIL", failures=[failure])
    response = subprocess.CompletedProcess([], 0, json.dumps({"model": raw, "exit_code": 2}), "")
    with patch("codekeel.producer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert isinstance(result.observation, Observation)
    assert isinstance(result.coverage, Coverage)
    assert result.coverage is result.observation.coverage
    assert result.diagnostics[0].kind == cause
    if cause == "rule_without_subjects":
        assert result.diagnostics[0].subject == "rule-zero"
        assert result.observation.records("unknowns")[0].id == "unknown-rule"


def test_every_source_failure_uses_runtime_mismatch_with_an_older_parser(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    raw = _model(git_head="a" * 40)
    failures = [
        _record(str(index), kind=kind, evidence_class="UNKNOWN")
        for index, kind in enumerate(("SyntaxError", "IndentationError", "TabError"))
    ]
    raw["coverage"].update(status="FAIL", files_parsed=0, failures=failures)
    response = subprocess.CompletedProcess([], 0, json.dumps({"model": raw, "exit_code": 2}), "")
    with patch("codekeel.producer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.observation.coverage.failures
    assert len(result.diagnostics) == len(failures)
    assert {item.kind for item in result.diagnostics} == {"runtime_mismatch"}
