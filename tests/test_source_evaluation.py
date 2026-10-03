# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One immutable collection can be evaluated under different architecture decisions."""

import copy
import json
from pathlib import Path

import pytest

from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
from archkeel.ir.protocol import CollectionResponse


def _facts():
    payload = json.loads(
        (Path(__file__).parent / "fixtures/collection-protocol/response-python.json").read_bytes()
    )
    facts = payload["facts"]
    other = copy.deepcopy(facts["files"][0])
    other.update(
        id="FILE-store", rel_path="src/store.py", module="project.store", evidence_id="E-store"
    )
    facts["files"].append(other)
    facts["inputs"].append({"path": "src/store.py", "digest": "e" * 64, "role": "selected"})
    facts["evidence"].append(
        {
            "id": "E-store",
            "file": "src/store.py",
            "line": 1,
            "end_line": 1,
            "column": 0,
            "excerpt": "",
        }
    )
    facts["coverage"].update(
        selected_files=["src/app.py", "src/store.py"], files_read=2, files_parsed=2
    )
    record = facts["sections"][0]["records"][0]
    record["data"].update(target_module="project.store", target_package="project", symbol=None)
    record["subjects"] = ["project.app", "project.store"]
    facts["imports"] = [
        {
            "kind": "local",
            "import_id": "IMP-1",
            "module": "project.store",
            "file": "src/store.py",
            "runtime_file": "src/store.py",
            "declaration_file": None,
        }
    ]
    for name in (
        "symbols",
        "calls",
        "references",
        "bindings",
        "typing_signals",
        "constructs",
        "unknowns",
    ):
        facts["sections"].append({"name": name, "records": []})
    facts["capabilities"]["sections"] = [entry["name"] for entry in facts["sections"]]
    return decode_response(json.dumps(payload).encode()).facts


def test_contracts_evaluate_same_facts_without_changing_them() -> None:
    from archkeel.check.evaluation.evaluate import evaluate_source

    facts = _facts()
    before = encode_response(CollectionResponse(facts))
    empty = {"schema_version": "2.1.0", "components": [], "rules": []}
    forbidden = copy.deepcopy(empty)
    forbidden["rules"] = [
        {
            "id": "NO-STORE",
            "kind": "forbidden_dependency",
            "source": "project.app",
            "target": "project.store",
            "include_type_checking": True,
            "rationale": "Application must use the service.",
            "provenance": ["architecture.md"],
            "decided_by": "architect",
        }
    ]
    allowed = evaluate_source(facts, parse_contract(empty), roots=("src",), namespace="project")
    rejected = evaluate_source(
        facts, parse_contract(forbidden), roots=("src",), namespace="project"
    )
    assert allowed.violations == []
    assert [item["rule_ids"] for item in rejected.violations] == [["NO-STORE"]]
    assert allowed.imports == rejected.imports
    assert encode_response(CollectionResponse(facts)) == before


def test_partial_python_capabilities_cannot_be_evaluated_as_full_profile() -> None:
    from archkeel.check.evaluation.evaluate import evaluate_source

    payload = (
        Path(__file__).parent / "fixtures/collection-protocol/response-python.json"
    ).read_bytes()
    facts = decode_response(payload).facts
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    with pytest.raises(ProtocolError, match="sections"):
        evaluate_source(facts, contract, roots=("src",), namespace="project")


@pytest.mark.parametrize("target_kind", ["local-package", "external", "builtin"])
def test_import_target_cannot_reclassify_an_observed_local_module(target_kind: str) -> None:
    payload = json.loads(encode_response(CollectionResponse(_facts())))
    facts = payload["facts"]
    if target_kind == "local-package":
        facts["sections"][0]["records"][0]["data"]["target_package"] = "project.ghost"
    elif target_kind == "external":
        facts["imports"] = [{"kind": "external", "import_id": "IMP-1", "package": "project"}]
    else:
        facts["imports"] = [{"kind": "builtin", "import_id": "IMP-1", "name": "project.store"}]
    with pytest.raises(ProtocolError, match="(local import package|observed local module)"):
        decode_response(json.dumps(payload).encode())
