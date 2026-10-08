# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One immutable collection can be evaluated under different architecture decisions."""

import copy
import json
from pathlib import Path

import pytest

from archkeel.ir.codec import parse_contract
from archkeel.ir.facts import ForbiddenConstructKind
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
    facts["capabilities"]["constructs"] = [
        {"name": kind.value, "status": "decided"} for kind in ForbiddenConstructKind
    ]
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


def _typescript_facts(*, inner_uml: bool):
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/collection-protocol/response-typescript.json"
        ).read_bytes()
    )
    facts = payload["facts"]
    if inner_uml:
        facts["capabilities"]["sections"] = [
            "imports",
            "unknowns",
            "symbols",
            "calls",
            "references",
            "bindings",
        ]
        facts["capabilities"]["resolution_features"] = [
            "literal-imports",
            "relative-specifiers",
            "node-builtins",
            "local-runtime-closure",
            "inner-uml-v1",
        ]
        facts["sections"].extend(
            {"name": name, "records": []} for name in ("symbols", "calls", "references", "bindings")
        )
    return decode_response(json.dumps(payload).encode()).facts


def test_typescript_inner_uml_receipt_measures_only_published_facts() -> None:
    from archkeel.check.evaluation.evaluate import evaluate_source

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    legacy = evaluate_source(
        _typescript_facts(inner_uml=False), contract, roots=("src",), namespace="project"
    )
    measured = evaluate_source(
        _typescript_facts(inner_uml=True), contract, roots=("src",), namespace="project"
    )

    assert "calls" not in legacy.observed_sections
    assert legacy.coverage["calls_analyzed"] is None
    assert measured.observed_sections == frozenset(
        {"imports", "unknowns", "symbols", "calls", "references", "bindings"}
    )
    assert measured.coverage["calls_analyzed"] == 0
    assert measured.contexts == []
    assert all(
        item["id"] not in {"UNKNOWN-PYTHON-DYNAMIC-CALLS", "UNKNOWN-CONTEXT-DATAFLOW"}
        for item in measured.unknowns
    )


def _dart_inner_facts(*, sections: list[str] | None = None, features: list[str] | None = None):
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/collection-protocol/response-typescript.json"
        ).read_bytes()
    )
    facts = payload["facts"]
    registered_sections = sections or [
        "imports",
        "unknowns",
        "symbols",
        "calls",
        "references",
        "bindings",
    ]
    facts["profile"] = "archkeel-dart-analyzer"
    facts["capabilities"]["sections"] = registered_sections
    facts["capabilities"]["resolution_features"] = (
        ["inner-uml-v1"] if features is None else features
    )
    facts["sections"].extend(
        {"name": name, "records": []}
        for name in registered_sections
        if name not in {section["name"] for section in facts["sections"]}
    )
    return decode_response(json.dumps(payload).encode()).facts


def test_dart_inner_uml_requires_and_accepts_the_exact_native_receipt() -> None:
    from jsonschema import Draft202012Validator

    from archkeel.check.evaluation.evaluate import evaluate_source

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    facts = _dart_inner_facts()
    Draft202012Validator(
        json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes())
    ).validate(json.loads(encode_response(CollectionResponse(facts))))
    measured = evaluate_source(facts, contract, roots=("src",), namespace="project")

    assert measured.observed_sections == frozenset(
        {"imports", "unknowns", "symbols", "calls", "references", "bindings"}
    )
    assert measured.coverage["calls_analyzed"] == 0


@pytest.mark.parametrize(
    ("sections", "features"),
    [
        (["imports", "unknowns"], ["inner-uml-v1"]),
        (["imports", "unknowns", "symbols", "calls", "references", "bindings"], []),
        (
            ["imports", "unknowns", "symbols", "calls", "references", "bindings"],
            ["inner-uml-v1", "unsupported-extra"],
        ),
    ],
)
def test_dart_rejects_unregistered_inner_uml_receipts(
    sections: list[str], features: list[str]
) -> None:
    from archkeel.check.evaluation.evaluate import evaluate_source

    facts = _dart_inner_facts(sections=sections, features=features)
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    with pytest.raises(ProtocolError, match="registered"):
        evaluate_source(facts, contract, roots=("src",), namespace="project")


def test_removed_dart_profile_identity_is_rejected() -> None:
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/collection-protocol/response-typescript.json"
        ).read_bytes()
    )
    payload["facts"]["profile"] = "archkeel-dart-directives"

    with pytest.raises(ProtocolError, match="profile"):
        decode_response(json.dumps(payload).encode())


def test_dart_profile_cannot_answer_a_typescript_request() -> None:
    from archkeel.analyzer.process import _requested_facts
    from archkeel.ir.protocol import (
        CollectionRequest,
        SnapshotInput,
        SourceScope,
        TypeScriptSettings,
    )

    request = CollectionRequest(
        SnapshotInput("/source", "a" * 40, False),
        SourceScope(("src",), "project"),
        TypeScriptSettings(),
    )

    with pytest.raises(ProtocolError, match="requested language"):
        _requested_facts(_dart_inner_facts(), request)


@pytest.mark.parametrize(
    ("sections", "features"),
    [
        (["imports", "unknowns", "symbols"], ["static-imports"]),
        (["imports", "unknowns", "symbols", "calls", "references", "bindings"], ["static-imports"]),
        (
            ["imports", "unknowns", "symbols", "calls", "references", "bindings"],
            ["static-imports", "inner-uml-v1", "extra"],
        ),
    ],
)
def test_typescript_rejects_unregistered_section_or_feature_receipt(
    sections: list[str], features: list[str]
) -> None:
    from archkeel.check.evaluation.evaluate import evaluate_source

    facts = json.loads(
        (
            Path(__file__).parent / "fixtures/collection-protocol/response-typescript.json"
        ).read_bytes()
    )["facts"]
    facts["capabilities"]["sections"] = sections
    facts["capabilities"]["resolution_features"] = features
    facts["sections"] = [section for section in facts["sections"] if section["name"] in sections]
    for name in set(sections) - {section["name"] for section in facts["sections"]}:
        facts["sections"].append({"name": name, "records": []})
    decoded = decode_response(json.dumps({"protocol_version": "1.0.0", "facts": facts}).encode())
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    with pytest.raises(ProtocolError, match="not registered"):
        evaluate_source(decoded.facts, contract, roots=("src",), namespace="project")
