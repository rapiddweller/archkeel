# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Pledge with the pinned external producer; verify the saved D-self evidence."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pledge.ir.codec import decode_canonical_model, parse_observation
from pledge.ir.model import Observation

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"


@pytest.fixture(scope="module")
def self_observation(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    producer = Path(
        os.environ.get("PLEDGE_PRODUCER_ROOT", str(ROOT.parent / "datamimic-ee"))
    ).resolve()
    manifest = json.loads((FIXTURE / "provenance.json").read_bytes())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=producer, text=True).strip()
    assert head == manifest["producer_head"], "D-self requires the pinned producer commit"
    output = tmp_path_factory.mktemp("self-report") / "architecture.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pledge.cli",
            "report",
            "--root",
            str(ROOT),
            "--producer-root",
            str(producer),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    result = json.loads(run.stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == result["declared_rules"] == "PASS"
    assert result["expectation_fulfilled"] == "n/a"
    return parse_observation(decode_canonical_model(json.loads(output.read_bytes())))


def test_self_report_is_complete_and_matches_saved_evidence(self_observation: Observation) -> None:
    observed = self_observation
    saved = parse_observation(
        decode_canonical_model(json.loads((FIXTURE / "architecture.json").read_bytes()))
    )
    assert observed.records("violations") == ()
    assert all(record.kind != "rule-without-subjects" for record in observed.records("unknowns"))
    coverage = observed.coverage
    assert coverage.status == coverage.rules == "PASS"
    assert coverage.files_discovered == coverage.files_read == coverage.files_parsed > 0
    assert coverage.failures == ()
    assert observed.python_version == saved.python_version
    assert observed.source.source_digest == saved.source.source_digest
    assert observed.contract.digest == saved.contract.digest
    assert observed.analyzer.code_digest == saved.analyzer.code_digest
    assert coverage == saved.coverage


def test_self_contract_covers_modules_and_producer_interface(self_observation: Observation) -> None:
    contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    packages = {
        package for component in contract["components"] for package in component["packages"]
    }
    public_api = set(contract["public_api"])
    forbidden_ir = {
        rule["target"] for rule in contract["rules"] if rule["source"] == "pledge.producer"
    }
    for module in self_observation.records("modules"):
        name = module.data.get("qualified_name")
        assert isinstance(name, str)
        if name != "pledge":
            assert any(name == package or name.startswith(package + ".") for package in packages), (
                name
            )
        if name.startswith("pledge.ir.") and name not in public_api:
            assert any(
                name == prefix or name.startswith(prefix + ".") for prefix in forbidden_ir
            ), name
    for record in self_observation.records("imports"):
        source = record.data.get("source_module")
        target = record.data.get("target_module")
        assert isinstance(source, str) and isinstance(target, str)
        if (source == "pledge.producer" or source.startswith("pledge.producer.")) and (
            target == "pledge.ir" or target.startswith("pledge.ir.")
        ):
            assert target in public_api, (source, target)
