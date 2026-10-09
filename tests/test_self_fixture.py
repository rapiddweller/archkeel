# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shared self-run publishes only complete evidence and starts fresh each session."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import conftest
import pytest
from test_codec import raw_observation

from archkeel.ir.codec import canonical_report_bytes, parse_observation


@pytest.fixture
def observation():
    model = parse_observation(raw_observation())
    return replace(
        model,
        source=replace(model.source, git_head="a" * 40, dirty=False, source_digest="b" * 64),
        analyzer=replace(model.analyzer, code_digest="c" * 64),
        contract=replace(model.contract, digest="d" * 64),
        coverage=replace(model.coverage, rules="PASS"),
        python_version="3.11.12",
    )


def test_shared_run_generates_once_and_reuses_complete_output(tmp_path, monkeypatch, observation):
    calls = []

    def report(args, **kwargs):
        calls.append(args)
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(canonical_report_bytes(observation))
        output.with_name("architecture.report.html").write_text("report")
        result = {
            "diagnostics": [],
            "observation_complete": "PASS",
            "declared_rules": "UNKNOWN",
            "expectation_fulfilled": "n/a",
        }
        return subprocess.CompletedProcess(args, 0, json.dumps(result), "")

    monkeypatch.setattr(conftest.subprocess, "run", report)
    with ThreadPoolExecutor(max_workers=2) as workers:
        runs = list(workers.map(conftest._load_self_run, [tmp_path, tmp_path]))
    assert len(calls) == 1
    assert runs[0] == runs[1]
    assert (tmp_path / "result.json").is_file()


def test_failed_generator_does_not_publish_a_cached_result(tmp_path, monkeypatch):
    def report(args, **kwargs):
        Path(args[args.index("--output") + 1]).write_text("partial")
        return subprocess.CompletedProcess(args, 2, "", "failed")

    monkeypatch.setattr(conftest.subprocess, "run", report)
    with pytest.raises(AssertionError):
        conftest._load_self_run(tmp_path)
    assert not (tmp_path / "result.json").exists()


def test_invalid_successful_output_does_not_publish_a_cached_result(tmp_path, monkeypatch):
    def report(args, **kwargs):
        output = Path(args[args.index("--output") + 1])
        output.write_text("partial")
        output.with_name("architecture.report.html").write_text("report")
        return subprocess.CompletedProcess(args, 0, "{}", "")

    monkeypatch.setattr(conftest.subprocess, "run", report)
    with pytest.raises((AssertionError, ValueError, KeyError)):
        conftest._load_self_run(tmp_path)
    assert not (tmp_path / "result.json").exists()


@pytest.mark.parametrize("workers", [0, 2])
def test_fixture_generates_once_per_serial_or_parallel_session(tmp_path, observation, workers):
    root = tmp_path / "project"
    tests = root / "tests"
    tests.mkdir(parents=True)
    (root / "seed.json").write_bytes(canonical_report_bytes(observation))
    fixture_code = Path(conftest.__file__).read_text()
    fixture_code += """
from types import SimpleNamespace
import subprocess as real_subprocess

def _report(args, **kwargs):
    counter = ROOT / "generations.txt"
    with counter.open("a") as stream:
        stream.write("generated\\n")
    output = Path(args[args.index("--output") + 1])
    output.write_bytes((ROOT / "seed.json").read_bytes())
    output.with_name("architecture.report.html").write_text("report")
    return real_subprocess.CompletedProcess(args, 0, json.dumps({
        "diagnostics": [], "observation_complete": "PASS",
        "declared_rules": "UNKNOWN", "expectation_fulfilled": "n/a",
    }), "")

subprocess = SimpleNamespace(run=_report)
"""
    (tests / "conftest.py").write_text(fixture_code)
    for name in ("first", "second"):
        (tests / f"test_{name}.py").write_text(
            "def test_report(self_run):\n    assert self_run.artifact\n"
        )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-n",
        str(workers),
        "--dist=loadfile",
        "--max-worker-restart=0",
        "--basetemp=" + str(root / "run"),
        str(tests),
    ]
    for expected in (1, 2):
        run = subprocess.run(command, cwd=root, capture_output=True, text=True)
        assert run.returncode == 0, (run.stdout, run.stderr)
        assert (root / "generations.txt").read_text().splitlines() == ["generated"] * expected
