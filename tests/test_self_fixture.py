# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shared self-run publishes only complete evidence and retains independent freshness."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import conftest
import pytest
import test_self
from test_codec import raw_observation
from test_self import STALE

from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.digest import package_digest
from fixtures import reproduce_self


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


def _provenance(observation):
    normalized = replace(
        observation, source=replace(observation.source, git_head=None, dirty=False)
    )
    return {
        "checker_digest": package_digest(),
        "observation_digest": sha256(canonical_report_bytes(normalized)).hexdigest(),
    }


def test_generator_saves_only_checker_and_normalized_observation_digests(
    tmp_path, monkeypatch, observation
):
    fixture = tmp_path / "fixtures/D-self"
    fixture.mkdir(parents=True)
    monkeypatch.setattr(reproduce_self, "ROOT", tmp_path)
    monkeypatch.setattr(reproduce_self, "FIXTURE", fixture)

    def report(args, **kwargs):
        output = tmp_path / args[args.index("--output") + 1]
        output.write_bytes(canonical_report_bytes(observation))
        return subprocess.CompletedProcess(args, 0, "{}", "")

    monkeypatch.setattr(reproduce_self.subprocess, "run", report)
    assert reproduce_self.main() == 0
    assert json.loads((fixture / "provenance.json").read_text()) == _provenance(observation)


def test_git_metadata_changes_preserve_saved_observation_proof(observation):
    changed = replace(
        observation, source=replace(observation.source, git_head="e" * 40, dirty=True)
    )
    test_self._assert_self_provenance(changed, _provenance(observation))


@pytest.mark.parametrize(
    "field",
    ["checker_digest", "observation_digest"],
)
def test_stale_provenance_is_rejected(observation, field):
    provenance = _provenance(observation)
    provenance[field] = "stale"
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(observation, provenance)


@pytest.mark.parametrize("field", ["checker_digest", "observation_digest"])
def test_missing_provenance_is_rejected(observation, field):
    provenance = _provenance(observation)
    del provenance[field]
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(observation, provenance)


def test_changed_coverage_is_rejected_even_when_top_level_digests_match(observation):
    changed = replace(observation, coverage=replace(observation.coverage, files_read=0))
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(changed, _provenance(observation))


def test_added_valid_unknown_record_is_rejected(observation):
    raw = decode_canonical_model(json.loads(canonical_report_bytes(observation)))
    raw["unknowns"] = [
        {**raw["modules"][0], "id": "unknown1", "evidence_class": "UNKNOWN", "kind": "unresolved"}
    ]
    changed = parse_observation(raw)
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(changed, _provenance(observation))


def test_changed_record_content_is_rejected_even_when_digests_match(observation):
    changed = replace(
        observation,
        sections=tuple(
            replace(
                section,
                records=tuple(replace(record, title="Changed") for record in section.records),
            )
            if section.name == "modules"
            else section
            for section in observation.sections
        ),
    )
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(changed, _provenance(observation))


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


@pytest.mark.parametrize("part", ["source", "analyzer", "contract", "python_version"])
def test_changed_actual_digest_is_rejected(observation, part):
    if part == "source":
        changed = replace(observation, source=replace(observation.source, source_digest="f" * 64))
    elif part == "analyzer":
        changed = replace(observation, analyzer=replace(observation.analyzer, code_digest="f" * 64))
    elif part == "contract":
        changed = replace(observation, contract=replace(observation.contract, digest="f" * 64))
    else:
        changed = replace(observation, python_version="3.12.0")
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(changed, _provenance(observation))


@pytest.mark.parametrize("field", ["git_head", "dirty", "artifact_digest", "extra"])
def test_unknown_provenance_key_is_rejected(observation, field):
    provenance = _provenance(observation)
    provenance[field] = "unused"
    with pytest.raises(AssertionError, match=STALE):
        test_self._assert_self_provenance(observation, provenance)


def test_stale_saved_result_is_rejected(tmp_path, monkeypatch, observation):
    result = {"artifact": "fixtures/D-self/architecture.json", "declared_rules": "UNKNOWN"}
    (tmp_path / "result.json").write_text(json.dumps(result))
    monkeypatch.setattr(test_self, "FIXTURE", tmp_path)
    changed = {**result, "declared_rules": "PASS"}
    run = conftest.SelfRun(observation, json.dumps(changed), canonical_report_bytes(observation))
    with pytest.raises(AssertionError, match=STALE):
        test_self.test_self_result_matches_the_saved_run(run)


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
