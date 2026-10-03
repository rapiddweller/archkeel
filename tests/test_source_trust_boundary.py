# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent acceptance of collector claims before Core grants proof."""

import copy
import json
import os
import signal
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_collection_protocol import _request
from test_source_evaluation import _facts

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.observation import assemble_observation
from archkeel.check.ratchets import RatchetError, measure_python_ratchets
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import (
    ProtocolError,
    decode_request,
    decode_response,
    encode_response,
)
from archkeel.ir.protocol import CollectionError, CollectionResponse
from archkeel.ir.trace import trace_valid_violations


def _payload():
    return json.loads(encode_response(CollectionResponse(_facts())))


def _decode(payload):
    return decode_response(json.dumps(payload).encode()).facts


def _contract():
    return {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [
            {
                "id": "NO-STORE",
                "kind": "forbidden_dependency",
                "source": "project.app",
                "target": "project.store",
                "include_type_checking": True,
                "rationale": "Only resolved source evidence proves this direction.",
                "provenance": ["architecture.md"],
                "decided_by": "architect",
            }
        ],
    }


def _observation(tmp_path: Path, facts):
    (tmp_path / "architecture-contract.json").write_text(json.dumps(_contract()))
    return assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "architecture-contract.json",
        roots=("src",),
        namespace="project",
    )[0]


def _unresolved(payload, *, import_id="IMP-1", specifier="project.store"):
    payload["facts"]["imports"] = [
        {
            "kind": "unresolved",
            "import_id": import_id,
            "specifier": specifier,
            "reason": "Resolver cannot prove the target.",
        }
    ]


def test_resolved_negative_control_still_proves_dependency() -> None:
    facts = _decode(_payload())
    scan = evaluate_source(facts, parse_contract(_contract()), roots=("src",), namespace="project")
    assert [record["rule_ids"] for record in scan.violations] == [["NO-STORE"]]


def test_typed_unresolved_target_cannot_prove_forbidden_dependency() -> None:
    payload = _payload()
    _unresolved(payload)
    try:
        facts = _decode(payload)
    except ProtocolError:
        return
    scan = evaluate_source(facts, parse_contract(_contract()), roots=("src",), namespace="project")
    assert not scan.violations
    assert not scan.dependency_edges


def test_unresolved_target_cannot_prove_complete_absence(tmp_path: Path) -> None:
    payload = _payload()
    _unresolved(payload, specifier="unknown-package")
    payload["facts"]["sections"][0]["records"][0]["data"].update(
        target_module="unknown-package", target_package="unknown-package"
    )
    try:
        facts = _decode(payload)
    except ProtocolError:
        return
    observation = _observation(tmp_path, facts)
    assert observation.coverage.status != "PASS"
    assert all(
        assessment.status != "PASS"
        for assessment in rule_assessments(
            observation,
            undecided_by_rule={},
            complete=observation.coverage.status == "PASS",
        )
    )
    with pytest.raises(RatchetError):
        measure_python_ratchets(observation)


@pytest.mark.parametrize("source_module", ["project.ghost", "project.store"])
def test_import_source_module_must_match_observed_source_evidence(source_module: str) -> None:
    payload = _payload()
    record = payload["facts"]["sections"][0]["records"][0]
    record["data"]["source_module"] = source_module
    record["subjects"][0] = source_module
    with pytest.raises(ProtocolError):
        _decode(payload)


@pytest.mark.parametrize("evidence_ids", [[], ["E-store"]])
def test_import_evidence_must_name_its_actual_source_file(evidence_ids: list[str]) -> None:
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["evidence_ids"] = evidence_ids
    with pytest.raises(ProtocolError):
        _decode(payload)


def test_partial_scope_cannot_certify_complete_measurements(tmp_path: Path) -> None:
    payload = _payload()
    payload["facts"]["coverage"]["full_scope"] = False
    try:
        facts = _decode(payload)
    except ProtocolError:
        return
    observation = _observation(tmp_path, facts)
    assert observation.coverage.status != "PASS"
    with pytest.raises(RatchetError):
        measure_python_ratchets(observation)
    assert {rule for record in trace_valid_violations(observation) for rule in record.rule_ids} == {
        "NO-STORE"
    }


def test_resolved_violation_survives_unrelated_unresolved_target(tmp_path: Path) -> None:
    payload = _payload()
    facts = payload["facts"]
    unknown = copy.deepcopy(facts["sections"][0]["records"][0])
    unknown["id"] = "IMP-unknown"
    unknown["subjects"] = ["project.app", "project.missing"]
    unknown["data"].update(target_module="project.missing", target_package="project")
    facts["sections"][0]["records"].append(unknown)
    facts["imports"].append(
        {
            "kind": "unresolved",
            "import_id": "IMP-unknown",
            "specifier": "project.missing",
            "reason": "Dependency is unavailable in this snapshot.",
        }
    )
    gap = copy.deepcopy(unknown)
    gap.update(
        id="GAP-unresolved",
        evidence_class="UNKNOWN",
        area="coverage",
        kind="unresolved_import",
        data={"file": "src/app.py", "line": 1},
    )
    facts["coverage"]["gaps"].append(gap)
    facts["coverage"]["full_scope"] = False
    next(section for section in facts["sections"] if section["name"] == "unknowns")[
        "records"
    ].append(gap)
    observation = _observation(tmp_path, _decode(payload))
    assert {rule for record in trace_valid_violations(observation) for rule in record.rule_ids} == {
        "NO-STORE"
    }
    assert observation.coverage.status != "PASS"
    assert observation.records("unknowns")
    with pytest.raises(RatchetError):
        measure_python_ratchets(observation)


@pytest.mark.parametrize("limit", ["timeout", "output"])
def test_process_limit_stops_spawned_worker(tmp_path: Path, limit: str) -> None:
    """Heartbeats prove execution stopped, including when an orphan is a zombie."""
    pid_path = tmp_path / "worker.pid"
    heartbeat = tmp_path / "heartbeat"
    worker = (
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        "for count in range(200):\n"
        f"    Path({str(heartbeat)!r}).write_text(str(count))\n"
        "    time.sleep(0.025)\n"
    )
    collector = (
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable, '-c', {worker!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"while not Path({str(heartbeat)!r}).exists(): time.sleep(0.005)\n"
        + ("sys.stdout.write('x'*1000000); sys.stdout.flush()\n" if limit == "output" else "")
        + "time.sleep(10)\n"
    )
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    started = time.monotonic()
    try:
        result = ProcessCollector(
            (sys.executable, "-B", "-c", collector),
            timeout_seconds=0.5 if limit == "timeout" else 2,
            output_limit_bytes=1000,
        ).collect(request)
        assert isinstance(result, CollectionError)
        assert result.kind == ("timeout" if limit == "timeout" else "protocol_error")
        assert time.monotonic() - started < 4
        assert pid_path.exists(), "The worker must start before the host limit is exercised."
        time.sleep(0.1)
        stopped = heartbeat.read_text()
        time.sleep(0.15)
        assert heartbeat.read_text() == stopped, "Collector limit left a worker executing."
    finally:
        if pid_path.exists():
            try:
                os.kill(int(pid_path.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as error:
                # Windows may report an already-terminated PID as an invalid parameter.
                if os.name != "nt" or error.winerror != 87:
                    raise


@pytest.mark.parametrize("exit_kind", ["success", "invalid_json", "nonzero", "snapshot_error"])
def test_completed_exchange_stops_detached_stdio_worker(tmp_path: Path, exit_kind: str) -> None:
    pid_path = tmp_path / "worker.pid"
    heartbeat = tmp_path / "heartbeat"
    worker = (
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        "for count in range(200):\n"
        f"    Path({str(heartbeat)!r}).write_text(str(count))\n"
        "    time.sleep(0.025)\n"
    )
    payload = _payload()
    if exit_kind == "snapshot_error":
        payload["facts"]["source"]["git_head"] = "b" * 40
    output = "invalid JSON" if exit_kind == "invalid_json" else json.dumps(payload)
    collector = (
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable, '-c', {worker!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"while not Path({str(heartbeat)!r}).exists(): time.sleep(0.005)\n"
        f"print({output!r})\n"
        f"sys.exit({1 if exit_kind == 'nonzero' else 0})\n"
    )
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    try:
        result = ProcessCollector((sys.executable, "-B", "-c", collector)).collect(request)
        assert isinstance(result, CollectionError) == (exit_kind != "success")
        assert pid_path.exists()
        stopped = heartbeat.read_text()
        time.sleep(0.15)
        assert heartbeat.read_text() == stopped, "Completed collector left a worker executing."
    finally:
        if pid_path.exists():
            try:
                os.kill(int(pid_path.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as error:
                # Windows may report an already-terminated PID as an invalid parameter.
                if os.name != "nt" or error.winerror != 87:
                    raise
