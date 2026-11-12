# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-394: only this run's verified bundled binary can replay a native scope receipt."""

from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest
from collector_pin import pin_of
from test_collector_bundled_launcher import _install
from test_scoped_dependency_proof import _project, _rows

from archkeel.analyzer import process
from archkeel.cli import observe as shell
from archkeel.ir.codec import observation_payload, parse_observation
from archkeel.ir.model import RecordData


@pytest.fixture(scope="module")
def native_receipt(native_binary: Path, tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("native-receipt") / "repo"
    config = _project(root)
    directory = _install(root.parent / "_native", native_binary)
    observer = shell.observer_for(config.language, native_directory=directory)
    with mock.patch.object(process, "package_version", lambda: "0+unknown"):
        result = observer(
            root,
            roots=config.roots,
            namespace=config.namespace,
            contract=config.contract,
            git_head="receipt-test",
            dirty=False,
            contract_root=root,
            language=config.language,
        )
    assert result.observation is not None, result.diagnostics
    return result.observation, pin_of(str(shell.executable(shell.TYPESCRIPT_COLLECTOR, directory)))


def _proof(model, **changes):
    sections = []
    for section in model.sections:
        records = []
        for record in section.records:
            data = dict(record.data.entries)
            proof = data.get("dependency_scope_proof")
            if isinstance(proof, RecordData):
                values = dict(proof.entries)
                runtime = dict(values["runtime"].entries)
                runtime.update(changes)
                if runtime.get("code_digest") is None:
                    runtime.pop("code_digest", None)
                values["runtime"] = RecordData(tuple(runtime.items()))
                data["dependency_scope_proof"] = RecordData(tuple(values.items()))
                record = replace(record, data=RecordData(tuple(data.items())))
            records.append(record)
        sections.append(replace(section, records=tuple(records)))
    return replace(model, sections=tuple(sections))


def test_bundled_receipt_uses_the_verified_executable_digest(native_receipt):
    model, digest = native_receipt
    row = _rows(model)["a:requires"]
    assert row.status == "PASS", row.reason
    assert model.verified_binary.digest == digest
    proofs = [
        record.data.get("dependency_scope_proof")
        for record in model.records("scope_observations")
        if record.data.get("dependency_scope_proof")
    ]
    assert proofs
    assert all(proof.get("runtime").get("code_digest") == digest for proof in proofs)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("unverified", "dependency_scope_runtime_unverified"),
        ("configured", "dependency_scope_runtime_unverified"),
        ("wrong_digest", "dependency_scope_runtime_digest_mismatch"),
        ("missing_digest", "dependency_scope_runtime_digest_missing"),
        ("saved", "dependency_scope_runtime_unverified"),
    ],
)
def test_native_receipt_rejects_unverified_or_other_binary(native_receipt, mutation, reason):
    model, _ = native_receipt
    if mutation == "unverified":
        model = replace(model, verified_binary=None)
    elif mutation == "configured":
        model = replace(model, producer_kind=type(model.producer_kind).PINNED)
    elif mutation == "wrong_digest":
        model = _proof(model, code_digest="sha256:" + "0" * 64)
    elif mutation == "missing_digest":
        model = _proof(model, code_digest=None)
    else:
        model = parse_observation(observation_payload(model))
    row = _rows(model)["a:requires"]
    assert row.status == "UNKNOWN", row.reason
    assert reason in row.reason


def test_configured_collector_never_gets_verification(native_binary: Path, tmp_path: Path):
    observer = shell.observer_for(
        "typescript", collector_argv=(str(native_binary),), pinned_digest=pin_of(str(native_binary))
    )
    assert type(observer.collector) is process.ProcessCollector


def test_verification_checks_binary_bytes_not_only_the_digest_file(tmp_path: Path):
    binary = tmp_path / "collector"
    binary.write_bytes(b"one executable")
    expected = pin_of(str(binary))
    Path(str(binary) + shell.DIGEST_SUFFIX).write_text(expected.removeprefix("sha256:"))
    binary.write_bytes(b"another executable")
    with pytest.raises(ValueError, match="records"):
        shell.verified_binary(binary.name, tmp_path)
