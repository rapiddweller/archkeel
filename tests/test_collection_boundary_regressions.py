# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collector ownership, package compatibility and reproducible code identity."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.observation import assemble_observation
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _facts(root: Path, namespace: str = "sample"):
    package = root / "src" / Path(*namespace.split("."))
    package.mkdir(parents=True)
    (package / "app.py").write_text("def run(value: object):\n    assert value\n")
    (package / "other.py").write_text("value = 1\n")
    return collect(
        CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope(("src",), namespace),
            PythonSettings(),
        )
    )


def _contract():
    return parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})


@pytest.mark.parametrize("section", ["constructs", "typing_signals"])
@pytest.mark.parametrize(
    "owner", [None, "", 3, "outside.app.run", "sample.ghost.run", "sample.other.run"]
)
def test_owner_must_match_observed_module_and_cited_file(
    tmp_path: Path, section: str, owner: object
) -> None:
    payload = json.loads(encode_response(CollectionResponse(_facts(tmp_path))))
    record = next(item for item in payload["facts"]["sections"] if item["name"] == section)[
        "records"
    ][0]
    record["data"]["owner"] = owner
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("section", ["constructs", "typing_signals"])
def test_owner_needs_cited_source_evidence(tmp_path: Path, section: str) -> None:
    payload = json.loads(encode_response(CollectionResponse(_facts(tmp_path))))
    next(item for item in payload["facts"]["sections"] if item["name"] == section)["records"][0][
        "evidence_ids"
    ] = []
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_core_revalidates_facts_before_evaluating_policy(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    record,
                    data=replace(
                        record.data,
                        entries=tuple(
                            (name, "outside.app" if name == "owner" else value)
                            for name, value in record.data.entries
                        ),
                    ),
                )
                for record in section.records
            ),
        )
        if section.name == "constructs"
        else section
        for section in facts.sections
    )
    with pytest.raises(ProtocolError):
        evaluate_source(
            replace(facts, sections=sections), _contract(), roots=("src",), namespace="sample"
        )


@pytest.mark.parametrize("namespace", ["acme", "acme.product", "acme.product.service"])
def test_python_package_rollup_accepts_dotted_namespace(tmp_path: Path, namespace: str) -> None:
    facts = _facts(tmp_path, namespace)
    scan = evaluate_source(facts, _contract(), roots=("src",), namespace=namespace)
    assert scan.coverage["status"] == "PASS"
    assert len(scan.modules) == 2


def test_in_namespace_package_must_still_contain_its_module(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    files = (replace(facts.files[0], package="sample.foreign"), *facts.files[1:])
    with pytest.raises(ProtocolError):
        evaluate_source(
            replace(facts, files=files), _contract(), roots=("src",), namespace="sample"
        )


def test_metadata_only_version_does_not_change_analyzer_code_identity(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    contract = tmp_path / "contract.json"
    contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')

    def observe(value):
        return assemble_observation(
            value,
            contract_root=tmp_path,
            contract_path=contract,
            roots=("src",),
            namespace="sample",
        )[0]

    first = observe(facts)
    metadata = observe(replace(facts, adapter=replace(facts.adapter, version="9.9.dev42+metadata")))
    code = observe(replace(facts, adapter=replace(facts.adapter, code_digest="f" * 64)))
    assert metadata.analyzer.code_digest == first.analyzer.code_digest
    assert code.analyzer.code_digest != first.analyzer.code_digest


def test_owner_evidence_disambiguates_a_function_and_module_with_same_name(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    nested = tmp_path / "src/sample/app"
    nested.mkdir()
    (nested / "run.py").write_text("value = 1\n")
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("src",), "sample"),
        PythonSettings(),
    )
    facts = collect(request)
    response = decode_response(encode_response(CollectionResponse(facts)))
    assert len(response.facts.files) == 3
    scan = evaluate_source(response.facts, _contract(), roots=("src",), namespace="sample")
    assert scan.coverage["status"] == "PASS"
